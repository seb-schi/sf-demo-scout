// `sf mp retrieve`: named components from the common org into a fresh folder, then into the
// working tree only where that can't lose local work, with baselines recorded only as the
// contract allows (CONTRACT.md §4 rule 3). It holds the org's slot while it works, so no deploy or
// reconcile changes the baselines under it.
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, sep } from 'node:path';
import { readBaselines, recordBaselines } from './baselines.mjs';
import { readJson } from './fsx.mjs';
import { dirtyPaths, head, repoPath } from './git.mjs';
import { hashFiles } from './hash.mjs';
import { newOpId, readSlot, releaseSlot, takeSlot, thisHolder } from './journal.mjs';
import { comparisonContext, filesAtCommit, laneContext, layoutOf, mergeCopyDir, mergeFolder, Refusal, saveCopy, sourceApiVersionOf, takeLaneSlot, TOOL, verifiedRevision } from './lane.mjs';
import { parseEntries } from './types.mjs';

/** Where a retrieved file goes in the project: the default package folder, main/default, then its type folder. */
function targetPath(defaultDir, retrievedXml, fileKey) {
  const parts = retrievedXml.split(sep);
  const at = parts.lastIndexOf('default');
  const inside = at > 0 && parts[at - 1] === 'main' ? parts.slice(at + 1, -1) : [];
  if (!inside.length) throw new Error(`can't place ${retrievedXml} in the project`);
  return join(defaultDir, 'main', 'default', ...inside, ...fileKey.split('/'));
}

const keysOf = (files) => files.map((file) => file.key);

export async function guardedRetrieve({ cwd, values, target, merged = false, steward = false, runtime, dataDir }) {
  const { entries, problems } = parseEntries(values, { steward });
  if (problems.length) throw new Refusal(problems);
  if (!target) throw new Refusal('pass --target-org explicitly; sf mp never falls back to a default org');
  const ctx = laneContext({ cwd, dataDir, needsCommit: merged });
  const { kit, root, project, packageDirs } = ctx;
  const sourceApiVersion = sourceApiVersionOf(project);
  const context = comparisonContext(sourceApiVersion);

  const conn = await runtime.connect(target);
  if (conn.orgId !== kit.orgId) throw new Refusal(`${target} is org ${conn.orgId}, not the common org ${kit.orgId}`);
  const open = readSlot(kit.root, kit.orgId);
  if (open) throw new Refusal(`an operation is open on the common org (${open.record?.opId ?? 'unreadable slot'}); run sf mp reconcile before taking new baselines`);
  const opId = newOpId();
  const now = () => new Date().toISOString();
  const slot = { schema: 1, opId, session: kit.config.session, holder: thisHolder(), tool: TOOL, kind: 'retrieve', targetOrgId: kit.orgId, components: entries.map((entry) => entry.key), state: 'intent', transitions: [{ state: 'intent', at: now() }], createdAt: now() };
  const taken = await takeLaneSlot({ dataDir, kit, record: slot, takeSlot });
  if (!taken) throw new Refusal('another operation took the common org\'s slot just now; run sf mp status');

  const outDir = mkdtempSync(join(tmpdir(), 'sf-mp-retrieve-'));
  try {
    const baselines = readBaselines(kit.root, kit.orgId);
    const fresh = await runtime.retrieve(conn, entries, outDir, sourceApiVersion);
    const local = await runtime.resolveSource(kit.root, packageDirs, entries, sourceApiVersion);
    // HEAD as it is now, after the network waits; any revision recorded is checked against it.
    const rev = head(root);
    const defaultDir = packageDirs[Math.max(0, (project.packageDirectories ?? []).findIndex((dir) => dir.default))] ?? packageDirs[0];
    const updates = {};
    const acknowledged = [];
    const report = [];
    for (const entry of entries) {
      const org = fresh.get(entry.key);
      const mine = local.found.get(entry.key);
      const before = baselines.components[entry.key];
      const base = { lastModifiedBy: org.lastModifiedBy ?? null, lastModifiedDate: org.lastModifiedDate ?? null, recordedAt: now(), context };

      if (merged) {
        const copy = mergeCopyDir(kit.root, kit.orgId, entry.key);
        if (!existsSync(join(copy, 'meta.json'))) {
          report.push({ component: entry.key, outcome: 'refused', detail: 'there\'s no saved org copy to have merged; run sf mp retrieve without --merged first' });
          continue;
        }
        if (!mine) {
          report.push({ component: entry.key, outcome: 'refused', detail: 'it isn\'t in the project' });
          continue;
        }
        const layout = layoutOf(root, mine.component);
        const keys = keysOf(mine.files);
        const dirty = dirtyPaths(root, layout.bundleDir ? [layout.bundleDir] : layout.files);
        const committed = rev && filesAtCommit(root, rev, layout, keys);
        if (dirty.length || !committed) {
          report.push({ component: entry.key, outcome: 'refused', detail: `commit the merge first${dirty.length ? `: ${dirty.join(', ')}` : ''}` });
          continue;
        }
        const saved = readJson(join(copy, 'meta.json'));
        updates[entry.key] = { ...base, state: saved.state === 'present' ? 'present' : 'confirmed-absent', hash: saved.hash, lastModifiedBy: saved.lastModifiedBy, lastModifiedDate: saved.lastModifiedDate, source: { hash: hashFiles(committed), revision: rev, keys }, recordedBy: 'merged' };
        acknowledged.push(copy);
        const moved = org.state !== saved.state || org.hash !== saved.hash;
        report.push({ component: entry.key, outcome: 'merged', detail: moved ? 'recorded; but the org has changed again since that copy, so the next deploy will stop' : 'recorded the org version you merged onto' });
        continue;
      }

      if (org.state === 'unknown') {
        report.push({ component: entry.key, outcome: 'unknown', detail: org.problem });
        continue;
      }
      if (org.state === 'confirmed-absent') {
        if (before?.state === 'present') {
          report.push({ component: entry.key, outcome: 'deleted-in-org', detail: 'it was deleted in the org since your baseline; v1 doesn\'t handle deletes, so ask the steward' });
          continue;
        }
        updates[entry.key] = { ...base, state: 'confirmed-absent', hash: null, source: { hash: null, revision: null, keys: [] }, recordedBy: 'retrieve' };
        report.push({ component: entry.key, outcome: 'absent', detail: mine ? 'not in the org yet; your local copy will create it' : 'not in the org' });
        continue;
      }
      if (!mine) {
        // The project doesn't resolve it, but a file may still be there (hidden by .forceignore,
        // or half a component): never write over anything that exists.
        const targets = org.files.map((file) => ({ file, path: targetPath(defaultDir, org.xml, file.key) }));
        const existing = targets.filter(({ path }) => existsSync(path));
        if (existing.length) {
          const dir = saveCopy(mergeFolder(kit.root, kit.orgId), entry.key, org);
          report.push({ component: entry.key, outcome: 'conflict', files: existing.map(({ path }) => repoPath(root, path)), saved: dir, detail: `the project doesn't resolve it, but ${existing.map(({ path }) => repoPath(root, path)).join(', ')} already exist (hidden by .forceignore?). Nothing was written; the org's copy is in ${dir}/files` });
          continue;
        }
        for (const { file, path } of targets) {
          mkdirSync(dirname(path), { recursive: true });
          writeFileSync(path, file.bytes, { flag: 'wx' });
        }
        updates[entry.key] = { ...base, state: 'present', hash: org.hash, source: { hash: org.hash, revision: null, keys: keysOf(org.files) }, recordedBy: 'retrieve' };
        report.push({ component: entry.key, outcome: 'written', files: targets.map(({ path }) => repoPath(root, path)), detail: 'written into the project; commit it as it is before you change it' });
        continue;
      }
      if (hashFiles(mine.files) === org.hash) {
        const layout = layoutOf(root, mine.component);
        const keys = keysOf(org.files);
        updates[entry.key] = { ...base, state: 'present', hash: org.hash, source: { hash: org.hash, revision: verifiedRevision(root, rev, layout, keys, org.hash), keys }, recordedBy: 'retrieve' };
        report.push({ component: entry.key, outcome: 'matches', detail: 'your copy matches the org' });
        continue;
      }
      if (before?.state === 'present' && before.hash === org.hash && before.source?.keys?.length) {
        report.push({ component: entry.key, outcome: 'unchanged', detail: 'the org hasn\'t changed since your baseline; your local changes are your candidate' });
        continue;
      }
      const dir = saveCopy(mergeFolder(kit.root, kit.orgId), entry.key, org);
      report.push({
        component: entry.key,
        outcome: 'conflict',
        files: mine.files.map((file) => repoPath(root, file.path)),
        saved: dir,
        detail: `your copy differs from the org's${org.lastModifiedBy ? ` (last changed by ${org.lastModifiedBy}${org.lastModifiedDate ? ` on ${org.lastModifiedDate}` : ''})` : ''}. Merge ${dir}/files into your copy, commit, then run sf mp retrieve --metadata ${entry.key} --merged`,
      });
    }
    if (Object.keys(updates).length) {
      if (readSlot(kit.root, kit.orgId)?.record?.opId !== opId) throw new Refusal('the common org\'s slot changed hands during the retrieve; nothing was recorded');
      recordBaselines(kit.root, kit.orgId, updates);
    }
    // Only now, with the acknowledgement recorded, can the merge copies go.
    for (const copy of acknowledged) rmSync(copy, { recursive: true, force: true });
    return { orgId: kit.orgId, components: report };
  } finally {
    rmSync(outDir, { recursive: true, force: true });
    releaseSlot(kit.root, kit.orgId, opId);
  }
}
