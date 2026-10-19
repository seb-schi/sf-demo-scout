// `sf mp reconcile`: settles the common org's open operation (CONTRACT.md §4 rule 6).
// It never redeploys, never acts while the operation's own process may still be running, and
// only one reconcile works on an org at a time.
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { recordBaselines } from './baselines.mjs';
import { exportCandidate } from './candidate.mjs';
import { finishRealSuccess } from './deploy.mjs';
import { publishJsonExclusive, readJson } from './fsx.mjs';
import { holderState, journalDir, readSlot, recordPath, releaseSlot, settle, thisHolder, transition, updateSlot } from './journal.mjs';
import { comparisonContext, laneContext, Refusal, sourceApiVersionOf } from './lane.mjs';
import { compareWithOrg, parseEntries } from './types.mjs';

/** Claims the org's reconcile lock; returns a release function. */
function claimLock(root, orgId, holderStopped) {
  const lock = join(journalDir(root), `reconcile-${orgId}.lock`);
  for (let attempt = 0; attempt < 2; attempt++) {
    if (publishJsonExclusive(lock, thisHolder())) return () => rmSync(lock, { force: true });
    let holder;
    try {
      holder = readJson(lock);
    } catch {
      holder = undefined;
    }
    const state = holderState(holder);
    if (state === 'running') throw new Refusal(`another sf mp reconcile is working on the common org (process ${holder.pid}); wait for it`);
    if (state === 'unknown' && !holderStopped) throw new Refusal(`a reconcile lock is left from a process sf mp can't check (${holder?.pid ?? '?'} on ${holder?.host ?? '?'}); once you're sure it stopped, add --holder-stopped`);
    rmSync(lock, { force: true });
  }
  throw new Refusal('couldn\'t claim the reconcile lock; run sf mp reconcile again');
}

const stamp = () => new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z');

export async function reconcile({ cwd, target, settleAs, note, holderStopped = false, runtime, dataDir }) {
  if (settleAs && !['success', 'failed'].includes(settleAs)) throw new Refusal('--settle takes success or failed');
  if (settleAs && !note?.trim()) throw new Refusal('settling by hand needs --note saying what you checked');
  const ctx = laneContext({ cwd, dataDir, needsCommit: false });
  const { kit, project } = ctx;
  if (!readSlot(kit.root, kit.orgId)) return { outcome: 'nothing-open', detail: 'no operation is open on the common org' };

  const release = claimLock(kit.root, kit.orgId, holderStopped);
  const cleanup = [];
  try {
    // Re-read under the lock: another reconcile may have settled it meanwhile.
    const slot = readSlot(kit.root, kit.orgId);
    if (!slot) return { outcome: 'nothing-open', detail: 'no operation is open on the common org' };

    if (slot.unreadable) {
      if (!settleAs) throw new Refusal(`the slot is unreadable (${slot.unreadable}); check the org by hand, then run sf mp reconcile --settle failed|success --note "…"`);
      let raw = '';
      try {
        raw = readFileSync(slot.path, 'utf8');
      } catch {
        raw = '';
      }
      const kept = `${stamp()}-unreadable-slot`;
      publishJsonExclusive(recordPath(kit.root, kept), { schema: 1, opId: kept, state: `reconciled-${settleAs}`, note: `settled by hand: ${note.trim()}`, unreadableSlot: { problem: slot.unreadable, raw }, settledAt: new Date().toISOString() });
      rmSync(slot.path, { force: true });
      return { outcome: `reconciled-${settleAs}`, detail: `kept the unreadable slot and your note as ${kept}.json; baselines are unchanged, so retrieve again before the next deploy` };
    }

    let record = slot.record;
    const holder = holderState(record.holder);
    if (holder === 'running') throw new Refusal(`operation ${record.opId} is still running in process ${record.holder.pid}; wait for it, or stop it first`);
    if (holder === 'unknown' && !holderStopped) {
      throw new Refusal(`can't tell whether operation ${record.opId}'s process (${record.holder?.pid ?? '?'} on ${record.holder?.host ?? '?'}) has stopped; once you're sure, add --holder-stopped`);
    }
    if (record.kind === 'retrieve') {
      // A retrieve sends nothing to the org; its slot only guarded the baselines.
      releaseSlot(kit.root, kit.orgId, record.opId);
      return { outcome: 'released', detail: `released the slot of an interrupted retrieve (${record.opId}); nothing was recorded` };
    }
    if (!target) throw new Refusal('pass --target-org explicitly');
    const conn = await runtime.connect(target);
    if (conn.orgId !== record.targetOrgId) throw new Refusal(`${target} is org ${conn.orgId}, not the operation's org ${record.targetOrgId}`);

    const sourceApiVersion = record.options?.sourceApiVersion ?? sourceApiVersionOf(project);
    const context = comparisonContext(sourceApiVersion);
    const { entries } = parseEntries(record.components, { steward: Boolean(record.steward) });
    const stillOurs = () => {
      if (readSlot(kit.root, kit.orgId)?.record?.opId !== record.opId) throw new Refusal(`operation ${record.opId} no longer holds the slot; nothing was changed`);
    };
    const finish = (state, extra) => {
      stillOurs();
      record = transition(record, state, { ...extra, settledAt: new Date().toISOString() });
      settle(kit.root, kit.orgId, record);
      return record;
    };
    const keepOpen = (extra) => {
      stillOurs();
      record = transition(record, 'unresolved', extra);
      updateSlot(kit.root, kit.orgId, record);
      return record;
    };
    const candidate = async () => {
      const paths = new Map(Object.entries(record.candidate?.paths ?? {}));
      const { staging, staged } = await exportCandidate({ ctx, revision: record.candidate.revision, entries, paths, runtime, sourceApiVersion });
      cleanup.push(staging);
      return staged.found;
    };

    if (settleAs) {
      // The steward's call (rule 6 d). It closes the operation; baselines move only when the
      // full read-back comparison passes, exactly as for a deploy.
      const dir = mkdtempSync(join(tmpdir(), 'sf-mp-reconcile-'));
      cleanup.push(dir);
      let got;
      let evidence;
      try {
        got = await runtime.retrieve(conn, entries, dir, sourceApiVersion);
        evidence = Object.fromEntries([...got].map(([key, value]) => [key, { state: value.state, hash: value.hash ?? null }]));
      } catch (error) {
        evidence = { error: error.message };
      }
      let verified = false;
      if (settleAs === 'success' && !record.checkOnly && got && record.candidate) {
        const files = await candidate();
        verified = entries.every((entry) => got.get(entry.key)?.state === 'present' && compareWithOrg(files.get(entry.key).files, got.get(entry.key).files).matches);
        if (verified) {
          stillOurs();
          const at = new Date().toISOString();
          recordBaselines(kit.root, kit.orgId, Object.fromEntries(entries.map((entry) => [entry.key, {
            state: 'present', hash: got.get(entry.key).hash, source: { hash: record.candidate.hashes[entry.key], revision: record.candidate.revision, keys: files.get(entry.key).files.map((f) => f.key) },
            recordedBy: 'reconcile', opId: record.opId, recordedAt: at, context,
          }])), { revision: record.candidate.revision, opId: record.opId, at });
        }
      }
      const kept = verified ? 'baselines refreshed from the verified read-back' : 'baselines unchanged: retrieve, merge and commit before the next deploy of these components';
      const settled = finish(settleAs === 'success' ? 'reconciled-success' : 'reconciled-failed', { note: `settled by hand: ${note.trim()} (${kept})`, readback: evidence, verified });
      return { outcome: settled.state, record: settled };
    }

    if (record.state === 'intent') {
      // `submitting` is flushed before anything is sent, so this operation never left the machine.
      const settled = finish('reconciled-failed', { note: 'never submitted: the operation stopped before sending anything' });
      return { outcome: settled.state, record: settled };
    }

    let jobId = record.jobId;
    if (!jobId) {
      // Exactly one deploy request by the operation's own submitter, in the submission window,
      // in the operation's mode. Anything else is the steward's call.
      const since = record.transitions.find((t) => t.state === 'submitting')?.at ?? record.createdAt;
      const requests = await runtime.deployRequestsSince(conn, record.platformUser, since);
      // The org stamps whole seconds; anything stamped before the second we flushed `submitting`
      // in may belong to an earlier operation (or to clock skew), so it's the steward's call.
      const submittedAt = Math.floor(new Date(since).getTime() / 1000) * 1000;
      const fits = requests.filter((request) => Boolean(request.checkOnly) === Boolean(record.checkOnly) && new Date(request.createdDate).getTime() >= submittedAt);
      if (requests.length !== 1 || fits.length !== 1) {
        keepOpen({ note: `no job ID, and ${requests.length} deploy requests by ${record.platformUser ?? 'the submitter'} around ${since} (${fits.length} in this mode): settle by hand with --settle success|failed --note after checking Deployment Status in Setup` });
        return { outcome: 'needs-steward', record, requests };
      }
      jobId = fits[0].id;
      stillOurs();
      record = { ...record, jobId, note: `job ID found by its DeployRequest (${jobId})` };
      updateSlot(kit.root, kit.orgId, record);
    }

    const status = await runtime.deployStatus(conn, jobId);
    if (!status.done) return { outcome: 'still-running', detail: `job ${jobId} is ${status.status}; run sf mp reconcile again later`, record };
    if (!status.success) {
      const settled = finish('reconciled-failed', { result: { status: status.status, failures: status.failures, sent: true } });
      return { outcome: settled.state, record: settled };
    }
    if (record.checkOnly) {
      const settled = finish('reconciled-success', { result: { status: status.status, checkOnly: true } });
      return { outcome: settled.state, record: settled };
    }
    // A real deploy that succeeded: the read-back decides, exactly as in sf mp deploy.
    const staged = await candidate();
    const result = await finishRealSuccess({ ctx, record, entries, staged, runtime, conn, sourceApiVersion, context, cleanup, finish, keepOpen, outcome: status, settledState: 'reconciled-success' });
    return { outcome: result.record.state, record: result.record };
  } finally {
    for (const dir of cleanup) rmSync(dir, { recursive: true, force: true });
    release();
  }
}
