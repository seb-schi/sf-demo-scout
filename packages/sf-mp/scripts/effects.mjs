// The effect checks of sf-mp's type contracts, for callers outside `sf` (Scout's Lifecycle Center mode, where
// promotions deploy server-side and the captain lints a delivery before merging it). Only the checks about what a
// deploy would do to the org run here: changed page assignments in an object file, an active flow version, and
// files a bundle would drop from the org. The lane's own type rules (picklists, field type changes) stay the lane's.
// Aura bundles aren't a lane type, but a delivery can carry one, so the bridge gives them the bundle check too.
//
// stdin: [{ key: "Type:Name", candidate: [{ key, b64 }], org: [{ key, b64 }] | null }]
// stdout: { "Type:Name": ["problem", …] }, with only the components that have problems
import { execFileSync } from 'node:child_process';
import { readFileSync, realpathSync } from 'node:fs';
import { dirname } from 'node:path';
import { setCliRoot } from '../src/host.mjs';
import { candidateProblems, STEWARD_TYPES, TYPES } from '../src/types.mjs';

// The XML parser is the host CLI's: SF_MP_CLI_ROOT, else the install folder of the sf on the PATH.
setCliRoot(process.env.SF_MP_CLI_ROOT || dirname(dirname(realpathSync(execFileSync('sh', ['-c', 'command -v sf'], { encoding: 'utf8' }).trim()))));

const EFFECTS = new Set(['object-v1', 'flow-v1', 'bundle-v1']);
const BRIDGE_ONLY = new Map([['AuraDefinitionBundle', 'bundle-v1']]);
const files = (list) => (list ?? []).map((file) => ({ key: file.key, bytes: Buffer.from(file.b64, 'base64') }));

const report = {};
for (const item of JSON.parse(readFileSync(0, 'utf8') || '[]')) {
  const at = item.key.indexOf(':');
  const entry = { key: item.key, type: item.key.slice(0, at), name: item.key.slice(at + 1) };
  const policy = (TYPES.get(entry.type) ?? STEWARD_TYPES.get(entry.type))?.policy ?? BRIDGE_ONLY.get(entry.type);
  if (!EFFECTS.has(policy)) continue;
  const problems = candidateProblems(entry, files(item.candidate), item.org ? files(item.org) : null, policy);
  if (problems.length) report[item.key] = problems;
}
process.stdout.write(JSON.stringify(report));
