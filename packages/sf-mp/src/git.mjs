// The Git calls the lane needs. The candidate always comes from a commit, never the working
// tree, so an editor saving mid-run changes nothing that gets deployed.
import { execFileSync } from 'node:child_process';
import { relative, sep } from 'node:path';

const run = (cwd, args, binary = false) =>
  execFileSync('git', args, { cwd, encoding: binary ? 'buffer' : 'utf8', maxBuffer: 256 * 1024 * 1024, stdio: ['ignore', 'pipe', 'pipe'] });

export function gitRoot(cwd) {
  try {
    return run(cwd, ['rev-parse', '--show-toplevel']).trim();
  } catch {
    return undefined;
  }
}

/** HEAD's commit, or undefined in a repo without commits. */
export function head(cwd) {
  try {
    return run(cwd, ['rev-parse', '--verify', 'HEAD^{commit}']).trim();
  } catch {
    return undefined;
  }
}

export const repoPath = (root, path) => relative(root, path).split(sep).join('/');

/** Paths (repo-relative) with uncommitted or untracked changes, among the given ones. */
export function dirtyPaths(root, paths) {
  if (!paths.length) return [];
  const out = run(root, ['status', '--porcelain=v1', '-z', '--untracked-files=all', '--', ...paths]);
  return out
    .split('\0')
    .filter(Boolean)
    .filter((entry) => entry.length > 3 && entry[2] === ' ')
    .map((entry) => entry.slice(3));
}

/** Files (repo-relative) under the given paths at a revision. */
export function listFiles(root, rev, paths) {
  if (!paths.length) return [];
  return run(root, ['ls-tree', '-r', '--name-only', '-z', rev, '--', ...paths]).split('\0').filter(Boolean);
}

export const showFile = (root, rev, path) => run(root, ['show', `${rev}:${path}`], true);

export function fileExists(root, rev, path) {
  try {
    run(root, ['cat-file', '-e', `${rev}:${path}`]);
    return true;
  } catch {
    return false;
  }
}

export function isAncestor(root, ancestor, rev) {
  try {
    run(root, ['merge-base', '--is-ancestor', ancestor, rev]);
    return true;
  } catch {
    return false;
  }
}

/** Commits in rev's history that touch the paths, newest first. */
export function history(root, rev, paths, max = 200) {
  if (!paths.length) return [];
  return run(root, ['log', '--format=%H', `-n${max}`, rev, '--', ...paths]).split('\n').filter(Boolean);
}

export function userName(root) {
  try {
    return run(root, ['config', 'user.name']).trim() || undefined;
  } catch {
    return undefined;
  }
}

export function statusShort(root, paths) {
  return run(root, ['status', '--porcelain=v1', '--', ...paths]).trim();
}
