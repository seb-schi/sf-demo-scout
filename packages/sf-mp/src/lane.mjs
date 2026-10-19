// What the lane commands share: the refusal type, the lane context (kit, registry, Git, project)
// and the helpers for component files in Git, merge copies and backups.
import { mkdirSync, readFileSync, realpathSync, writeFileSync } from 'node:fs';
import { dirname, join, posix, relative, sep } from 'node:path';
import { writeJsonAtomic } from './fsx.mjs';
import { fileExists, gitRoot, head, history, isAncestor, repoPath, showFile } from './git.mjs';
import { hashFiles } from './hash.mjs';
import { cliRoot } from './host.mjs';
import { findKit, readRegistry, readSfProject, withRegistryLock } from './kit.mjs';

export const TOOL = 'sf-mp 0.3.2';

/** A refusal: nothing was changed, in the org or locally. Commands exit 2. */
export class Refusal extends Error {
  constructor(reasons, data = {}) {
    const list = [].concat(reasons);
    super(list.length === 1 ? list[0] : list.map((reason) => `- ${reason}`).join('\n'));
    this.name = 'MpRefused';
    this.reasons = list;
    this.data = data;
  }
}

export function hostVersion(name) {
  try {
    return JSON.parse(readFileSync(join(cliRoot(), 'node_modules', name, 'package.json'), 'utf8')).version;
  } catch {
    return undefined;
  }
}

export const same = (a, b) => {
  try {
    return realpathSync(a) === realpathSync(b);
  } catch {
    return false;
  }
};

/**
 * The kit project and its lane checkout for cwd. With `needsCommit`, also HEAD and the project
 * config as committed there. Refuses outside the one lane checkout of the bound org.
 */
export function laneContext({ cwd, dataDir, needsCommit = true }) {
  let kit;
  try {
    kit = findKit(cwd);
  } catch (error) {
    throw new Refusal(error.message);
  }
  if (!kit) throw new Refusal('this folder isn\'t in a kit project; run `sf mp init --target-org <common org>` in the project first');
  if (kit.config.authority !== 'lane') throw new Refusal(`authority "${kit.config.authority}" isn't in this delivery; only "lane" is`);
  const registry = readRegistry(dataDir);
  if (registry.orgs[kit.orgId]?.role === 'guard') throw new Refusal('this machine guards the common org but isn\'t its lane: only the captain\'s machine writes to it, so hand your work over instead');
  const lane = registry.orgs[kit.orgId]?.lane;
  if (!lane) throw new Refusal('this machine has no lane for the common org yet; run `sf mp init --target-org <common org>` in this project first');
  if (!same(lane, kit.root)) throw new Refusal(`the common org's lane on this machine is ${lane}; run sf mp there, or move the lane with \`sf mp init --replace-lane\``);
  const root = gitRoot(kit.root);
  if (!root) throw new Refusal('the kit project isn\'t in a Git repository; the lane deploys committed work only');
  const rev = head(root);
  if (needsCommit && !rev) throw new Refusal('the repository has no commits yet');
  const kitRel = repoPath(root, kit.root);
  const at = (path) => (kitRel ? posix.join(kitRel, path) : path);
  const { project, packageDirs } = readSfProject(kit.root);
  return { kit, root, rev, kitRel, at, project, packageDirs, registry };
}

/**
 * Publishes the operation's slot only if this checkout is still the org's lane, both checked
 * under the registry lock, so a lane move (`init --replace-lane`) and a starting operation
 * can't both win. Returns false when another operation holds the slot.
 */
export async function takeLaneSlot({ dataDir, kit, record, takeSlot }) {
  return withRegistryLock(dataDir, () => {
    const lane = readRegistry(dataDir).orgs[kit.orgId]?.lane;
    if (!lane || !same(lane, kit.root)) throw new Refusal(`the common org's lane is now ${lane ?? 'unset'}, not this checkout; run sf mp there`);
    try {
      return takeSlot(kit.root, kit.orgId, record);
    } catch (error) {
      throw new Refusal(`couldn't write the intent record (${error.message}); nothing was sent`);
    }
  });
}

/** sourceApiVersion pins every retrieve, comparison and deploy to one API version. */
export function sourceApiVersionOf(project) {
  const version = project?.sourceApiVersion;
  if (!/^\d+\.0$/.test(String(version ?? ''))) throw new Refusal('set "sourceApiVersion" in sfdx-project.json (for example "64.0"), so every retrieve and deploy uses one API version');
  return String(version);
}

export const comparisonContext = (sourceApiVersion) => ({ sourceApiVersion, sdr: hostVersion('@salesforce/source-deploy-retrieve'), policy: 'v1' });

export const sameContext = (a, b) => a?.sourceApiVersion === b?.sourceApiVersion && a?.policy === b?.policy;

const toPosix = (path) => path.split(sep).join('/');

/**
 * Where a source component lives in the repo: its base folder (the metadata file's folder) and
 * either its exact files or, for a bundle, its whole folder.
 */
export function layoutOf(root, component) {
  const base = repoPath(root, dirname(component.xml ?? component.content));
  const bundle = component.type?.strategies?.adapter === 'bundle' || component.type?.name === 'LightningComponentBundle';
  return bundle
    ? { base, bundleDir: repoPath(root, component.content) }
    : { base, files: [component.xml, ...(component.content ? component.walkContent() : [])].filter(Boolean).map((path) => repoPath(root, path)) };
}

/** The component's files at a commit for exactly these keys; undefined if any is missing there. */
export function filesAtCommit(root, rev, layout, keys) {
  if (!keys?.length) return undefined;
  const files = [];
  for (const key of keys) {
    const path = posix.join(layout.base, key);
    if (!fileExists(root, rev, path)) return undefined;
    files.push({ key, bytes: showFile(root, rev, path) });
  }
  return files;
}

/** The revision when the component's content there hashes to `hash`, otherwise null. */
export function verifiedRevision(root, rev, layout, keys, hash) {
  if (!rev || !hash) return null;
  const files = filesAtCommit(root, rev, layout, keys);
  return files && hashFiles(files) === hash ? rev : null;
}

/**
 * Does rev's history contain the baseline's source? A recorded commit counts only when it's an
 * ancestor and really holds that content; otherwise any commit in rev's history that touched
 * the component and holds it (which covers amended and rebased history).
 * Returns that commit, or undefined.
 */
export function sourceAncestor(root, rev, layout, source) {
  if (!source?.hash || !source.keys?.length) return undefined;
  if (source.revision && isAncestor(root, source.revision, rev) && verifiedRevision(root, source.revision, layout, source.keys, source.hash)) return source.revision;
  const paths = source.keys.map((key) => posix.join(layout.base, key));
  for (const commit of history(root, rev, paths, 100)) {
    if (verifiedRevision(root, commit, layout, source.keys, source.hash)) return commit;
  }
  return undefined;
}

const safeName = (key) => key.replace(/[^A-Za-z0-9._-]+/g, '_');

/** Saves a retrieved copy of components (files keyed relative to their base) under a folder. */
export function saveCopy(folder, key, retrieved) {
  const dir = join(folder, safeName(key));
  for (const { key: fileKey, bytes } of retrieved.files ?? []) {
    const path = join(dir, 'files', ...fileKey.split('/'));
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, bytes);
  }
  writeJsonAtomic(join(dir, 'meta.json'), {
    component: key,
    state: retrieved.state,
    hash: retrieved.hash ?? null,
    lastModifiedBy: retrieved.lastModifiedBy ?? null,
    lastModifiedDate: retrieved.lastModifiedDate ?? null,
    savedAt: new Date().toISOString(),
  });
  return dir;
}

export const mergeFolder = (kitRoot, orgId) => join(kitRoot, '.mp', 'merge', orgId);
export const mergeCopyDir = (kitRoot, orgId, key) => join(mergeFolder(kitRoot, orgId), safeName(key));

export const relativeTo = (from, path) => toPosix(relative(from, path));
