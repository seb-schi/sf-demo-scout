// `sf mp deploy`: the guarded sequence (CONTRACT.md §4) for
// named components, taken from HEAD's committed content.
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir, userInfo } from 'node:os';
import { join } from 'node:path';
import { readBaselines, recordBaselines } from './baselines.mjs';
import { setKeys } from './guard.mjs';
import { exportCandidate } from './candidate.mjs';
import { dirtyPaths, listFiles, showFile, userName } from './git.mjs';
import { hashFiles, normalizeBytes } from './hash.mjs';
import { readSlot, settle, takeSlot, thisHolder, newOpId, transition, updateSlot } from './journal.mjs';
import { comparisonContext, laneContext, layoutOf, mergeFolder, Refusal, saveCopy, sameContext, sourceAncestor, sourceApiVersionOf, takeLaneSlot, TOOL } from './lane.mjs';
import { ownerOf, readOwners } from './owners.mjs';
import { candidateProblems, compareWithOrg, parseEntries } from './types.mjs';

// Local tooling that never deploys may sit in a bundle folder; anything else hidden by
// .forceignore would silently drop out of the deploy.
const isLocalOnly = (path) => /(^|\/)(__tests__|__mocks__)\//.test(path) || /(^|\/)(jsconfig\.json|tsconfig\.json|\.eslintrc(\.json)?|\.prettierrc)$/.test(path);

/** Exports the selected components, the project config and .forceignore from HEAD into staging. */
async function freeze({ ctx, entries, runtime, sourceApiVersion }) {
  const { kit, root, rev, at, packageDirs } = ctx;
  const local = await runtime.resolveSource(kit.root, packageDirs, entries, sourceApiVersion);
  const missing = entries.filter((entry) => !local.found.has(entry.key)).map((entry) => entry.key);
  if (missing.length) throw new Refusal(`not found in the project: ${missing.join(', ')}`);

  const layouts = new Map(entries.map((entry) => [entry.key, layoutOf(root, local.found.get(entry.key).component)]));
  const watched = [at('sfdx-project.json'), at('.forceignore'), ...[...layouts.values()].flatMap((l) => (l.bundleDir ? [l.bundleDir] : l.files))];
  const dirty = dirtyPaths(root, watched);
  if (dirty.length) throw new Refusal(`commit these first; the lane deploys committed work only: ${dirty.join(', ')}`);

  const paths = new Map([...layouts].map(([key, layout]) => [key, layout.bundleDir ? listFiles(root, rev, [layout.bundleDir]) : layout.files]));
  const { staging, staged } = await exportCandidate({ ctx, revision: rev, entries, paths, runtime, sourceApiVersion });

  // A bundle file hidden by .forceignore would be missing from the deploy without a word.
  const problems = [];
  for (const entry of entries) {
    const layout = layouts.get(entry.key);
    if (!layout.bundleDir) continue;
    const keys = new Set(staged.found.get(entry.key).files.map((file) => file.key));
    const hidden = paths.get(entry.key).filter((path) => !isLocalOnly(path) && !keys.has(path.slice(layout.base.length + 1)));
    if (hidden.length) problems.push(`${entry.key}: .forceignore hides ${hidden.join(', ')}, which the deploy would leave out`);
  }
  if (problems.length) {
    rmSync(staging, { recursive: true, force: true });
    throw new Refusal(problems);
  }
  return { staging, staged, layouts, paths };
}

function scopeProblems(entries, componentSet) {
  const wanted = new Set(entries.map((entry) => entry.key));
  const parents = new Set(entries.filter((entry) => entry.type === 'CustomField').map((entry) => `CustomObject:${entry.name.split('.')[0]}`));
  const extra = setKeys(componentSet).filter((key) => !wanted.has(key) && !parents.has(key));
  return extra.length ? [`the deploy would also carry ${extra.join(', ')}; name only what you mean to deploy`] : [];
}

function describeChange(entry, baseline, fresh, candidate = []) {
  const who = fresh.lastModifiedBy ? ` by ${fresh.lastModifiedBy}` : '';
  const when = fresh.lastModifiedDate ? ` on ${fresh.lastModifiedDate}` : '';
  if (baseline.state === 'present' && fresh.state === 'present') {
    const differs = fresh.files
      .filter((file) => {
        const mine = candidate.find((c) => c.key === file.key);
        return !mine || !normalizeBytes(mine.bytes).equals(normalizeBytes(file.bytes));
      })
      .map((file) => file.key);
    const files = differs.length ? `; against your candidate it differs in ${differs.join(', ')}` : '';
    return `${entry.key} changed in the org since your baseline${who}${when}${files}. The org's copy is saved under .mp/merge/ for you to merge`;
  }
  if (baseline.state === 'present' && fresh.state === 'confirmed-absent') return `${entry.key} was deleted in the org since your baseline`;
  if (baseline.state === 'confirmed-absent' && fresh.state === 'present') return `${entry.key} was created in the org since your baseline${who}${when}`;
  return `${entry.key}: the org's copy can't be read (${fresh.problem ?? fresh.state})`;
}

/** Runs the sequence. Returns the operation's outcome; throws Refusal when nothing was started. */
export async function guardedDeploy({ cwd, values, target, dryRun = false, steward = false, approvedBy = [], runtime, dataDir, log = () => {} }) {
  const { entries, problems } = parseEntries(values, { steward });
  if (problems.length) throw new Refusal(problems);
  if (!target) throw new Refusal('pass --target-org explicitly; sf mp never falls back to a default org');
  const ctx = laneContext({ cwd, dataDir });
  const { kit, root, rev, at } = ctx;

  const project = JSON.parse(showFile(root, rev, at('sfdx-project.json')).toString('utf8'));
  if (project.replacements) throw new Refusal('sfdx-project.json has "replacements", which v1 refuses: the deployed bytes must be the committed bytes');
  const sourceApiVersion = sourceApiVersionOf(project);
  const context = comparisonContext(sourceApiVersion);

  // 1. Bind.
  const conn = await runtime.connect(target);
  if (conn.orgId !== kit.orgId) throw new Refusal(`${target} is org ${conn.orgId}, not the common org ${kit.orgId}`);

  // 4 (early). Owners, so nobody waits through a freeze to hear no.
  const owners = readOwners(kit.root);
  const actor = userName(root) ?? userInfo().username;
  const approvals = [];
  const needOwner = [];
  for (const entry of entries) {
    const owner = ownerOf(owners, entry);
    if (!owner || owner === actor) continue;
    if (approvedBy.includes(owner)) approvals.push({ component: entry.key, owner, revision: rev });
    else needOwner.push(`${entry.key} is owned by ${owner}: get their yes, then add --approved-by "${owner}"`);
  }
  if (needOwner.length) throw new Refusal(needOwner);

  const baselines = readBaselines(kit.root, kit.orgId);
  const open = readSlot(kit.root, kit.orgId);
  if (open) {
    throw new Refusal(open.unreadable
      ? `the journal's slot for the common org is unreadable (${open.unreadable}); it blocks all writes until the steward settles it: run sf mp status`
      : `operation ${open.record.opId} (${open.record.state}) is still open on the common org; run sf mp reconcile`);
  }

  // 2–3. Freeze and scope.
  const { staging, staged, layouts, paths } = await freeze({ ctx, entries, runtime, sourceApiVersion });
  const cleanup = [staging];
  const done = () => cleanup.forEach((dir) => rmSync(dir, { recursive: true, force: true }));
  try {
    const scope = scopeProblems(entries, staged.componentSet);
    if (scope.length) throw new Refusal(scope);
    const hashes = Object.fromEntries(entries.map((entry) => [entry.key, hashFiles(staged.found.get(entry.key).files)]));
    const digest = hashFiles(entries.flatMap((entry) => staged.found.get(entry.key).files.map((file) => ({ ...file, key: `${entry.key}/${file.key}` }))));

    // 5–6. Slot and intent.
    const opId = newOpId();
    const apiOptions = { checkOnly: dryRun, testLevel: kit.config.testLevel, rollbackOnError: true, ignoreWarnings: false, rest: false, purgeOnDelete: false };
    let record = {
      schema: 1,
      opId,
      session: kit.config.session,
      actor,
      platformUser: conn.username,
      holder: thisHolder(),
      tool: TOOL,
      kind: 'deploy',
      checkOnly: dryRun,
      steward: entries.some((entry) => entry.steward),
      targetOrgId: kit.orgId,
      components: entries.map((entry) => entry.key),
      approvals,
      candidate: { revision: rev, digest, hashes, paths: Object.fromEntries(paths) },
      options: { ...context, apiVersion: conn.conn?.getApiVersion?.(), testLevel: apiOptions.testLevel, transport: 'SOAP', rollbackOnError: true },
      baselineRefs: Object.fromEntries(entries.map((entry) => [entry.key, baselines.components[entry.key]?.hash ?? baselines.components[entry.key]?.state ?? null])),
      backupRef: null,
      state: 'intent',
      transitions: [{ state: 'intent', at: new Date().toISOString() }],
      createdAt: new Date().toISOString(),
    };
    const taken = await takeLaneSlot({ dataDir, kit, record, takeSlot });
    if (!taken) throw new Refusal('another operation took the common org\'s slot just now; run sf mp status');

    const finish = (state, extra) => {
      const settled = transition(record, state, { ...extra, settledAt: new Date().toISOString() });
      try {
        settle(kit.root, kit.orgId, settled);
        record = settled;
      } catch (error) {
        // The slot still shows the last state that could be written; reconcile settles it.
        record = { ...settled, note: `${settled.note ?? ''} couldn't write the settled record (${error.message}); the slot stays open: run sf mp reconcile`.trim() };
      }
      return record;
    };
    const keepOpen = (extra) => {
      record = transition(record, 'unresolved', extra);
      try {
        updateSlot(kit.root, kit.orgId, record);
      } catch (error) {
        record.note = `${record.note ?? ''} (couldn't update the journal: ${error.message})`.trim();
      }
      return record;
    };

    // 7. Freshness: R against B, every component.
    const freshDir = mkdtempSync(join(tmpdir(), 'sf-mp-fresh-'));
    cleanup.push(freshDir);
    let fresh;
    try {
      fresh = await runtime.retrieve(conn, entries, freshDir, sourceApiVersion);
    } catch (error) {
      return { record: finish('settled-failed', { result: { phase: 'freshness', reasons: [`the fresh retrieve failed: ${error.message}`], sent: false } }), exitCode: 2 };
    }
    const stale = [];
    const anchors = {};
    for (const entry of entries) {
      const baseline = baselines.components[entry.key];
      const now = fresh.get(entry.key);
      const candidate = staged.found.get(entry.key).files;
      if (!baseline || baseline.state === 'unknown') {
        stale.push(`${entry.key} has no baseline; run sf mp retrieve --metadata ${entry.key} first`);
        continue;
      }
      if (!sameContext(baseline.context, context)) {
        stale.push(`${entry.key}'s baseline was taken under API ${baseline.context?.sourceApiVersion ?? '?'}; retrieve it again under ${sourceApiVersion}`);
        continue;
      }
      if (now.state === 'unknown' || now.state !== (baseline.state === 'present' ? 'present' : 'confirmed-absent') || (now.state === 'present' && now.hash !== baseline.hash)) {
        if (now.state === 'present' && !now.lastModifiedBy && runtime.lastModified) Object.assign(now, await runtime.lastModified(conn, entry));
        stale.push(describeChange(entry, baseline, now, candidate));
        if (now.state === 'present') saveCopy(mergeFolder(kit.root, kit.orgId), entry.key, now);
        continue;
      }
      if (baseline.state === 'present' && !baseline.source?.keys?.length) {
        stale.push(`${entry.key}'s baseline comes from an older sf mp; run sf mp retrieve --metadata ${entry.key} to take it again (with local changes, it saves the org's copy for --merged)`);
        continue;
      }
      if (baseline.state === 'present') {
        const anchor = sourceAncestor(root, rev, layouts.get(entry.key), baseline.source);
        if (!anchor) {
          stale.push(`${entry.key}: HEAD's history doesn't contain the version the org has. Merge it in and commit, then run sf mp retrieve --metadata ${entry.key} --merged`);
          continue;
        }
        anchors[entry.key] = anchor;
      }
      stale.push(...candidateProblems(entry, candidate, now.state === 'present' ? now.files : undefined));
    }
    if (stale.length) {
      return { record: finish('settled-failed', { result: { phase: 'freshness', reasons: stale, sent: false } }), exitCode: 2, mergeFolder: mergeFolder(kit.root, kit.orgId) };
    }

    // 8. Backup.
    const backupDir = join(kit.root, '.mp', 'backups', opId);
    for (const entry of entries) saveCopy(backupDir, entry.key, fresh.get(entry.key));
    record = { ...record, backupRef: `.mp/backups/${opId}`, anchors };
    updateSlot(kit.root, kit.orgId, record);

    // 9. Dispatch. `submitting` is flushed just before SDR sends the deploy; if it can't be
    // written, the listener's throw stops the deploy before anything leaves this machine.
    let submitted = false;
    const mark = {
      orgId: kit.orgId,
      keys: setKeys(staged.componentSet),
      onSubmitting: async () => {
        record = transition(record, 'submitting');
        updateSlot(kit.root, kit.orgId, record);
        submitted = true;
      },
    };
    let operation;
    try {
      operation = await runtime.deploy(conn, staged.componentSet, apiOptions, mark);
    } catch (error) {
      if (!submitted) return { record: finish('settled-failed', { result: { phase: 'dispatch', reasons: [error.message], sent: false } }), exitCode: 1 };
      return { record: keepOpen({ note: `the deploy call failed after submitting (${error.message}); run sf mp reconcile` }), exitCode: 1 };
    }
    if (!operation?.id) return { record: keepOpen({ note: 'the deploy started but returned no job ID; run sf mp reconcile' }), exitCode: 1 };
    record = transition(record, 'dispatched', { jobId: operation.id });
    try {
      updateSlot(kit.root, kit.orgId, record);
    } catch (error) {
      log(`warning: couldn't record job ID ${operation.id} in the journal (${error.message}); sf mp reconcile will look it up`);
    }

    // 10. Reconcile: wait for a final status.
    let outcome;
    try {
      outcome = await runtime.poll(operation);
    } catch (error) {
      return { record: keepOpen({ note: `lost the deploy's status (${error.message}); run sf mp reconcile` }), exitCode: 1 };
    }
    if (!outcome.done) return { record: keepOpen({ note: `the deploy hasn't finished (${outcome.status}); run sf mp reconcile` }), exitCode: 1 };
    if (!outcome.success) return { record: finish('settled-failed', { result: { phase: 'deploy', status: outcome.status, failures: outcome.failures, sent: true } }), exitCode: 1 };
    if (dryRun) return { record: finish('settled-success', { result: { status: outcome.status, checkOnly: true } }), exitCode: 0 };

    // 11–12. Read back, then record.
    return await finishRealSuccess({ ctx, record, entries, staged: staged.found, runtime, conn, sourceApiVersion, context, cleanup, finish, keepOpen, outcome });
  } finally {
    done();
  }
}

/**
 * After a real deploy succeeded: verify the read-back, then refresh the baselines, move the
 * last deploy's revision, write the settled record and free the slot, in that order. A
 * mismatch keeps the operation open. Shared with reconcile.
 */
export async function finishRealSuccess({ ctx, record, entries, staged, runtime, conn, sourceApiVersion, context, cleanup, finish, keepOpen, outcome, settledState = 'settled-success' }) {
  const { kit } = ctx;
  const readDir = mkdtempSync(join(tmpdir(), 'sf-mp-readback-'));
  cleanup.push(readDir);
  let readback;
  try {
    readback = await runtime.retrieve(conn, entries, readDir, sourceApiVersion);
  } catch (error) {
    return { record: keepOpen({ note: `the deploy succeeded but the read-back failed (${error.message}); run sf mp reconcile` }), exitCode: 1 };
  }
  const evidence = {};
  const mismatches = [];
  for (const entry of entries) {
    const now = readback.get(entry.key);
    if (now?.state !== 'present') {
      mismatches.push(`${entry.key} isn't in the org after the deploy (${now?.problem ?? now?.state})`);
      continue;
    }
    const verdict = compareWithOrg(staged.get(entry.key).files, now.files);
    evidence[entry.key] = { hash: now.hash, matches: verdict.matches, differences: verdict.differences };
    if (!verdict.matches) mismatches.push(`${entry.key}: ${verdict.differences.join('; ')}`);
  }
  if (mismatches.length) {
    return {
      record: keepOpen({ result: { status: outcome?.status ?? 'Succeeded' }, readback: evidence, note: `deployed, but the read-back doesn't match: ${mismatches.join(' | ')}. Check the org, then settle with sf mp reconcile --settle` }),
      exitCode: 1,
    };
  }
  const now = new Date().toISOString();
  const updates = Object.fromEntries(
    entries.map((entry) => {
      const got = readback.get(entry.key);
      return [entry.key, {
        state: 'present',
        hash: got.hash,
        lastModifiedBy: got.lastModifiedBy ?? null,
        lastModifiedDate: got.lastModifiedDate ?? null,
        source: { hash: record.candidate.hashes[entry.key], revision: record.candidate.revision, keys: staged.get(entry.key).files.map((file) => file.key) },
        recordedBy: 'deploy',
        opId: record.opId,
        recordedAt: now,
        context,
      }];
    })
  );
  recordBaselines(kit.root, kit.orgId, updates, { revision: record.candidate.revision, opId: record.opId, at: now });
  return { record: finish(settledState, { result: { status: outcome?.status ?? 'Succeeded' }, readback: evidence }), exitCode: 0 };
}
