// The kit project (a Salesforce project with .mp/config.json) and this machine's registry of
// bound orgs. Both are read on every guarded command, so they fail loudly when unreadable:
// the prerun boundary turns that into a refusal for protected commands.
import { existsSync, readFileSync, realpathSync, rmSync } from 'node:fs';
import { hostname } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { publishExclusive, readJson, writeJsonAtomic } from './fsx.mjs';
import { org15 } from './ids.mjs';

export const TEST_LEVELS = new Set(['NoTestRun', 'RunLocalTests']);
const AUTHORITIES = new Set(['lane', 'board']);

const realPath = (path) => {
  try {
    return realpathSync(path);
  } catch {
    return resolve(path);
  }
};

/** The nearest folder at or above cwd holding sfdx-project.json, or undefined. */
export function findSfProject(cwd = process.cwd()) {
  for (let dir = resolve(cwd); ; dir = dirname(dir)) {
    if (existsSync(join(dir, 'sfdx-project.json'))) return realPath(dir);
    if (dirname(dir) === dir) return undefined;
  }
}

export function validateConfig(config) {
  const problems = [];
  if (!config || typeof config !== 'object' || Array.isArray(config)) return ['it is not a JSON object'];
  if (config.schema !== 1) problems.push('schema must be 1');
  if (!org15(config.commonOrgId)) problems.push('commonOrgId must be an org ID');
  if (typeof config.session !== 'string' || !config.session) problems.push('session must be a string');
  if (!AUTHORITIES.has(config.authority)) problems.push('authority must be "lane" or "board"');
  if (!TEST_LEVELS.has(config.testLevel)) problems.push('testLevel must be NoTestRun or RunLocalTests');
  return problems;
}

/** The kit project around cwd: { root, config }, or undefined outside one. Throws on a bad config. */
export function findKit(cwd = process.cwd()) {
  const root = findSfProject(cwd);
  if (!root) return undefined;
  const configPath = join(root, '.mp', 'config.json');
  if (!existsSync(configPath)) return undefined;
  let config;
  try {
    config = readJson(configPath);
  } catch (error) {
    throw new Error(`.mp/config.json is unreadable (${error.message})`);
  }
  const problems = validateConfig(config);
  if (problems.length) throw new Error(`.mp/config.json is invalid: ${problems.join('; ')}`);
  return { root, config, orgId: org15(config.commonOrgId) };
}

export function readSfProject(root) {
  const project = JSON.parse(readFileSync(join(root, 'sfdx-project.json'), 'utf8'));
  const dirs = (project.packageDirectories ?? []).map((dir) => dir.path).filter((path) => typeof path === 'string');
  if (!dirs.length) throw new Error('sfdx-project.json lists no packageDirectories');
  return { project, packageDirs: dirs.map((path) => join(root, path)) };
}

// ---- The machine registry: which orgs are bound here, and which checkout is each one's lane ----

export const registryPath = (dataDir) => join(dataDir, 'sf-mp', 'bound-orgs.json');

/** { orgs: { <org15>: { lane, boundAt } | { role: 'guard', checkout, boundAt } } }; empty when there's no registry yet. Throws when unreadable. */
export function readRegistry(dataDir) {
  if (!dataDir) return { orgs: {} };
  const path = registryPath(dataDir);
  if (!existsSync(path)) return { orgs: {} };
  let registry;
  try {
    registry = readJson(path);
  } catch (error) {
    throw new Error(`the sf-mp registry ${path} is unreadable (${error.message})`);
  }
  if (!registry || typeof registry.orgs !== 'object' || registry.orgs === null || Array.isArray(registry.orgs)) {
    throw new Error(`the sf-mp registry ${path} is invalid`);
  }
  for (const [id, entry] of Object.entries(registry.orgs)) {
    const valid = typeof entry?.lane === 'string' || (entry?.role === 'guard' && typeof entry?.checkout === 'string');
    if (org15(id) !== id || !valid) throw new Error(`the sf-mp registry ${path} has an invalid entry for ${id}`);
  }
  return registry;
}

const sleep = (ms) => new Promise((done) => setTimeout(done, ms));

function holderAlive(lockPath) {
  try {
    const { pid, host } = JSON.parse(readFileSync(lockPath, 'utf8'));
    if (host !== hostname()) return true;
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error.code === 'EPERM';
  }
}

/** Runs fn while holding the registry's exclusive lock (a short critical section). */
export async function withRegistryLock(dataDir, fn) {
  const path = registryPath(dataDir);
  const lock = `${path}.lock`;
  for (let attempt = 0; ; attempt++) {
    if (publishExclusive(lock, JSON.stringify({ pid: process.pid, host: hostname(), at: new Date().toISOString() }))) break;
    if (attempt >= 50) {
      if (holderAlive(lock)) throw new Error(`the sf-mp registry is locked by another process (${lock})`);
      rmSync(lock, { force: true });
      continue;
    }
    await sleep(100);
  }
  try {
    return await fn();
  } finally {
    rmSync(lock, { force: true });
  }
}

/** Runs update(registry) under the lock, then writes the result atomically. */
export async function updateRegistry(dataDir, update) {
  return withRegistryLock(dataDir, () => {
    const registry = readRegistry(dataDir);
    const next = update(structuredClone(registry)) ?? registry;
    writeJsonAtomic(registryPath(dataDir), next);
    return next;
  });
}

/** The orgs this cwd's guard protects: the kit's own binding plus every org bound on this machine. */
export function boundOrgs(kit, registry) {
  const bound = new Set(Object.keys(registry.orgs));
  if (kit) bound.add(kit.orgId);
  return bound;
}
