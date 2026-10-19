// Baselines (CONTRACT.md §4 rule 3): for each component, the org content the lane last
// saw and the committed source that content maps to. Recorded only when the kit can tie the
// working tree to it; refreshing one never legitimizes a stale candidate.
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { readJson, writeJsonAtomic } from './fsx.mjs';

export const baselinesPath = (root, orgId) => join(root, '.mp', 'baselines', `${orgId}.json`);

export function readBaselines(root, orgId) {
  const path = baselinesPath(root, orgId);
  if (!existsSync(path)) return { schema: 1, orgId, components: {}, lastDeploy: null };
  let data;
  try {
    data = readJson(path);
  } catch (error) {
    throw new Error(`${path} is unreadable (${error.message})`);
  }
  if (data?.schema !== 1 || data.orgId !== orgId || typeof data.components !== 'object' || data.components === null) {
    throw new Error(`${path} isn't a baselines file for ${orgId}`);
  }
  return data;
}

export const writeBaselines = (root, orgId, data) => writeJsonAtomic(baselinesPath(root, orgId), data);

/** Applies { key: baseline } to the file in one atomic write; returns the new data. */
export function recordBaselines(root, orgId, updates, lastDeploy) {
  const data = readBaselines(root, orgId);
  for (const [key, baseline] of Object.entries(updates)) data.components[key] = baseline;
  if (lastDeploy) data.lastDeploy = lastDeploy;
  writeBaselines(root, orgId, data);
  return data;
}
