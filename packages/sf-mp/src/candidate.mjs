// The frozen candidate: components exported from a commit into a private staging project, with
// the project config and .forceignore as committed there. What gets deployed (and what a
// read-back is compared with) is exactly this copy, never the working tree.
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileExists, showFile } from './git.mjs';
import { Refusal } from './lane.mjs';

/**
 * Exports `paths` (Map key -> repo-relative files) at `revision` and resolves the entries there.
 * Returns { staging, staged: { componentSet, found } }.
 */
export async function exportCandidate({ ctx, revision, entries, paths, runtime, sourceApiVersion }) {
  const { root, kit, kitRel, at, packageDirs } = ctx;
  const staging = mkdtempSync(join(tmpdir(), 'sf-mp-stage-'));
  const put = (repoPathName) => {
    const kitRelative = kitRel ? repoPathName.slice(kitRel.length + 1) : repoPathName;
    const target = join(staging, ...kitRelative.split('/'));
    mkdirSync(dirname(target), { recursive: true });
    writeFileSync(target, showFile(root, revision, repoPathName));
  };
  put(at('sfdx-project.json'));
  if (fileExists(root, revision, at('.forceignore'))) put(at('.forceignore'));
  for (const list of paths.values()) for (const path of list) put(path);
  const stagedDirs = packageDirs.map((dir) => join(staging, ...dir.slice(kit.root.length + 1).split(/[\\/]/)));
  const staged = await runtime.resolveSource(staging, stagedDirs, entries, sourceApiVersion);
  const lost = entries.filter((entry) => !staged.found.has(entry.key)).map((entry) => entry.key);
  if (lost.length) throw new Refusal(`these didn't resolve from the committed copy: ${lost.join(', ')}`);
  return { staging, staged };
}
