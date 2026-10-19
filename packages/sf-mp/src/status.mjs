// `sf mp status`: the session, the open operation if any, recent settled ones, the baselines,
// the last deploy's source revision, and shared .mp files not yet committed. Read-only.
import { readBaselines } from './baselines.mjs';
import { gitRoot, statusShort } from './git.mjs';
import { holderState, openSlots, settledRecords } from './journal.mjs';
import { findKit, readRegistry } from './kit.mjs';
import { Refusal } from './lane.mjs';

export function status({ cwd, dataDir }) {
  let kit;
  try {
    kit = findKit(cwd);
  } catch (error) {
    throw new Refusal(error.message);
  }
  if (!kit) throw new Refusal('this folder isn\'t in a kit project');
  const registry = readRegistry(dataDir);
  const lane = registry.orgs[kit.orgId]?.lane ?? null;
  let baselines;
  let baselineProblem;
  try {
    baselines = readBaselines(kit.root, kit.orgId);
  } catch (error) {
    baselineProblem = error.message;
  }
  const counts = {};
  for (const baseline of Object.values(baselines?.components ?? {})) counts[baseline.state] = (counts[baseline.state] ?? 0) + 1;
  const open = openSlots(kit.root).map((slot) => ({
    orgId: slot.orgId,
    unreadable: slot.unreadable,
    opId: slot.record?.opId,
    state: slot.record?.state,
    components: slot.record?.components,
    jobId: slot.record?.jobId,
    note: slot.record?.note,
    holder: slot.record ? holderState(slot.record.holder) : undefined,
  }));
  const root = gitRoot(kit.root);
  return {
    commonOrgId: kit.config.commonOrgId,
    session: kit.config.session,
    authority: kit.config.authority,
    testLevel: kit.config.testLevel,
    lane,
    thisCheckoutIsTheLane: lane === kit.root,
    open,
    recent: settledRecords(kit.root).slice(0, 5).map((r) => ({ opId: r.opId, state: r.state, checkOnly: r.checkOnly, components: r.components, unreadable: r.unreadable })),
    baselines: baselineProblem ? { problem: baselineProblem } : { counts, total: Object.keys(baselines.components).length },
    lastDeploy: baselines?.lastDeploy ?? null,
    uncommitted: root ? statusShort(root, [kit.root + '/.mp']).split('\n').filter(Boolean) : [],
  };
}
