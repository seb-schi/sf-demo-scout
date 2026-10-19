// sf mp retrieve (baselines only where the contract allows them) and sf mp reconcile.
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { after, test } from 'node:test';
import { addApex, addField, apexBody, APEX_META, cleanupTemps, commitAll, FakeOrg, fakeRuntime, git, makeKit, ORG15, write } from './helpers.mjs';

const { guardedDeploy } = await import('../src/deploy.mjs');
const { guardedRetrieve } = await import('../src/retrieve.mjs');
const { reconcile } = await import('../src/reconcile.mjs');
const { readBaselines } = await import('../src/baselines.mjs');
const { readSlot, settledRecords, takeSlot } = await import('../src/journal.mjs');
const { Refusal } = await import('../src/lane.mjs');

after(cleanupTemps);

const retrieve = (ctx, values, options = {}, runtimeOptions = {}) =>
  guardedRetrieve({ cwd: ctx.root, values, target: 'common', runtime: fakeRuntime(ctx.org, runtimeOptions), dataDir: ctx.dataDir, ...options });
const outcomes = (result) => Object.fromEntries(result.components.map((c) => [c.component, c.outcome]));

async function kitWithOrg() {
  const { root, dataDir } = await makeKit();
  return { root, dataDir, org: new FakeOrg() };
}

test('retrieve writes a missing component, and its baseline waits for the commit to tie it to history', async () => {
  const ctx = await kitWithOrg();
  ctx.org.put('ApexClass:FromOrg', [{ key: 'FromOrg.cls', bytes: apexBody('FromOrg') }, { key: 'FromOrg.cls-meta.xml', bytes: APEX_META }]);
  ctx.org.put('CustomField:Thing__c.Note__c', [{ key: 'Note__c.field-meta.xml', bytes: '<?xml version="1.0" encoding="UTF-8"?>\n<CustomField xmlns="http://soap.sforce.com/2006/04/metadata">\n    <fullName>Note__c</fullName>\n    <label>Note</label>\n    <length>80</length>\n    <type>Text</type>\n</CustomField>\n' }]);
  const result = await retrieve(ctx, ['ApexClass:FromOrg', 'CustomField:Thing__c.Note__c']);
  assert.deepEqual(outcomes(result), { 'ApexClass:FromOrg': 'written', 'CustomField:Thing__c.Note__c': 'written' });
  assert.match(readFileSync(join(ctx.root, 'force-app/main/default/classes/FromOrg.cls'), 'utf8'), /class FromOrg/);
  assert.ok(existsSync(join(ctx.root, 'force-app/main/default/objects/Thing__c/fields/Note__c.field-meta.xml')));
  const baseline = readBaselines(ctx.root, ORG15).components['ApexClass:FromOrg'];
  assert.equal(baseline.source.revision, null, 'not committed yet');
  // Committed unchanged, then edited: the deploy finds the org's version in history by content.
  commitAll(ctx.root, 'from the org');
  write(ctx.root, 'force-app/main/default/classes/FromOrg.cls', apexBody('FromOrg', 'return 1;'));
  commitAll(ctx.root, 'my change');
  const { record } = await guardedDeploy({ cwd: ctx.root, values: ['ApexClass:FromOrg'], target: 'common', runtime: fakeRuntime(ctx.org), dataDir: ctx.dataDir });
  assert.equal(record.state, 'settled-success');
});

test('retrieve edited before the first commit: the deploy can\'t tie the baseline to history and refuses', async () => {
  const ctx = await kitWithOrg();
  ctx.org.put('ApexClass:Hasty', [{ key: 'Hasty.cls', bytes: apexBody('Hasty') }, { key: 'Hasty.cls-meta.xml', bytes: APEX_META }]);
  await retrieve(ctx, ['ApexClass:Hasty']);
  write(ctx.root, 'force-app/main/default/classes/Hasty.cls', apexBody('Hasty', 'return 7;'));
  commitAll(ctx.root, 'edited before committing the org version');
  const { record } = await guardedDeploy({ cwd: ctx.root, values: ['ApexClass:Hasty'], target: 'common', runtime: fakeRuntime(ctx.org), dataDir: ctx.dataDir });
  assert.match(record.result.reasons[0], /HEAD's history doesn't contain the version the org has/);
});

test('retrieve never overwrites a different local copy: it saves the org copy, and --merged needs a commit', async () => {
  const ctx = await kitWithOrg();
  addApex(ctx.root, 'Both');
  commitAll(ctx.root, 'local');
  await ctx.org.seedFrom(ctx.root, ['ApexClass:Both']);
  assert.equal(outcomes(await retrieve(ctx, ['ApexClass:Both']))['ApexClass:Both'], 'matches');
  // Someone changes it in the org; my local edit is different again.
  ctx.org.put('ApexClass:Both', [{ key: 'Both.cls', bytes: apexBody('Both', 'return 41;') }, { key: 'Both.cls-meta.xml', bytes: APEX_META }], 'Setup User');
  write(ctx.root, 'force-app/main/default/classes/Both.cls', apexBody('Both', 'return 1;'));
  const before = readBaselines(ctx.root, ORG15).components['ApexClass:Both'];
  const result = await retrieve(ctx, ['ApexClass:Both']);
  assert.equal(outcomes(result)['ApexClass:Both'], 'conflict');
  assert.match(result.components[0].detail, /last changed by Setup User/);
  assert.match(readFileSync(join(ctx.root, 'force-app/main/default/classes/Both.cls'), 'utf8'), /return 1;/, 'local work kept');
  assert.deepEqual(readBaselines(ctx.root, ORG15).components['ApexClass:Both'], before, 'baseline untouched');
  // Merge by hand, but don't commit yet: --merged refuses.
  write(ctx.root, 'force-app/main/default/classes/Both.cls', apexBody('Both', 'return 41 + 1;'));
  assert.equal(outcomes(await retrieve(ctx, ['ApexClass:Both'], { merged: true }))['ApexClass:Both'], 'refused');
  const merge = commitAll(ctx.root, 'merged');
  assert.equal(outcomes(await retrieve(ctx, ['ApexClass:Both'], { merged: true }))['ApexClass:Both'], 'merged');
  const after = readBaselines(ctx.root, ORG15).components['ApexClass:Both'];
  assert.equal(after.source.revision, merge);
  assert.equal(after.hash, ctx.org.components.get('ApexClass:Both') && (await fakeRuntime(ctx.org).retrieve({}, [{ key: 'ApexClass:Both', type: 'ApexClass', name: 'Both' }])).get('ApexClass:Both').hash);
  const { record } = await guardedDeploy({ cwd: ctx.root, values: ['ApexClass:Both'], target: 'common', runtime: fakeRuntime(ctx.org), dataDir: ctx.dataDir });
  assert.equal(record.state, 'settled-success');
});

test('retrieve: unchanged org with local edits keeps the baseline; a deletion in the org is reported', async () => {
  const ctx = await kitWithOrg();
  addApex(ctx.root, 'Mine');
  commitAll(ctx.root, 'local');
  await ctx.org.seedFrom(ctx.root, ['ApexClass:Mine']);
  await retrieve(ctx, ['ApexClass:Mine']);
  write(ctx.root, 'force-app/main/default/classes/Mine.cls', apexBody('Mine', 'return 2;'));
  assert.equal(outcomes(await retrieve(ctx, ['ApexClass:Mine']))['ApexClass:Mine'], 'unchanged');
  ctx.org.components.delete('ApexClass:Mine');
  assert.equal(outcomes(await retrieve(ctx, ['ApexClass:Mine']))['ApexClass:Mine'], 'deleted-in-org');
});

test('retrieve refuses while an operation is open', async () => {
  const ctx = await kitWithOrg();
  takeSlot(ctx.root, ORG15, { schema: 1, opId: 'open-one', state: 'intent', transitions: [] });
  await assert.rejects(retrieve(ctx, ['ApexClass:X']), (error) => error instanceof Refusal && /operation is open/.test(error.message));
});

// ---- reconcile ----

async function laneWithOpen(runtimeOptions) {
  const ctx = await kitWithOrg();
  addApex(ctx.root, 'Foo');
  commitAll(ctx.root, 'foo');
  await ctx.org.seedFrom(ctx.root, ['ApexClass:Foo']);
  await retrieve(ctx, ['ApexClass:Foo']);
  write(ctx.root, 'force-app/main/default/classes/Foo.cls', apexBody('Foo', 'return 1;'));
  commitAll(ctx.root, 'v2');
  const { record } = await guardedDeploy({ cwd: ctx.root, values: ['ApexClass:Foo'], target: 'common', runtime: fakeRuntime(ctx.org, runtimeOptions), dataDir: ctx.dataDir });
  return { ...ctx, record };
}

/** Pretends the operation's process has stopped (it ran in this test process). */
function stopHolder(ctx) {
  const slot = readSlot(ctx.root, ORG15);
  const record = { ...slot.record, holder: { ...slot.record.holder, pid: 999999 } };
  write(ctx.root, `.mp/journal/open-${ORG15}.json`, JSON.stringify(record));
}

const settleIt = (ctx, extra = {}, runtimeOptions = {}) =>
  reconcile({ cwd: ctx.root, target: 'common', runtime: fakeRuntime(ctx.org, runtimeOptions), dataDir: ctx.dataDir, ...extra });

test('reconcile refuses while the operation\'s process is still running', async () => {
  const ctx = await laneWithOpen({ failPoll: true });
  await assert.rejects(settleIt(ctx), (error) => error instanceof Refusal && /still running in process/.test(error.message));
});

test('reconcile (a): a job ID with a final success reads back and settles', async () => {
  const ctx = await laneWithOpen({ failPoll: true });
  stopHolder(ctx);
  const result = await settleIt(ctx);
  assert.equal(result.outcome, 'reconciled-success');
  assert.equal(readSlot(ctx.root, ORG15), undefined);
  assert.equal(readBaselines(ctx.root, ORG15).lastDeploy.opId, ctx.record.opId);
});

test('reconcile (b): no job ID, exactly one DeployRequest since submitting is taken as the job', async () => {
  const ctx = await laneWithOpen({ noJobId: true });
  stopHolder(ctx);
  assert.equal((await settleIt(ctx)).outcome, 'reconciled-success');
  // Two candidates: the steward decides.
  const twice = await laneWithOpen({ noJobId: true });
  stopHolder(twice);
  const result = await settleIt(twice, {}, { requests: [{ id: '0Af1' }, { id: '0Af2' }] });
  assert.equal(result.outcome, 'needs-steward');
  assert.ok(readSlot(twice.root, ORG15).record, 'still open');
});

test('reconcile (c): an operation still in intent settles as never submitted', async () => {
  const ctx = await kitWithOrg();
  takeSlot(ctx.root, ORG15, { schema: 1, opId: 'left-in-intent', state: 'intent', targetOrgId: ORG15, components: ['ApexClass:Foo'], holder: { pid: 999999, host: (await import('node:os')).hostname() }, transitions: [{ state: 'intent', at: new Date().toISOString() }], options: { sourceApiVersion: '64.0' } });
  const result = await settleIt(ctx);
  assert.equal(result.outcome, 'reconciled-failed');
  assert.match(result.record.note, /never submitted/);
  assert.equal(readSlot(ctx.root, ORG15), undefined);
});

test('reconcile (d): settling by hand closes the operation; baselines move only on a verified read-back', async () => {
  // The org reformatted the class: the steward closes it, but the baselines stay as they were.
  const ctx = await laneWithOpen({ reformatOnDeploy: true });
  stopHolder(ctx);
  const before = readBaselines(ctx.root, ORG15);
  await assert.rejects(settleIt(ctx, { settleAs: 'success' }), /needs --note/);
  const result = await settleIt(ctx, { settleAs: 'success', note: 'the org reformatted the class; checked by eye' });
  assert.equal(result.outcome, 'reconciled-success');
  assert.equal(result.record.verified, false);
  assert.match(result.record.note, /baselines unchanged/);
  assert.deepEqual(readBaselines(ctx.root, ORG15), before);
  // A lost status, but the org holds exactly the candidate: settling by hand verifies and moves them.
  const clean = await laneWithOpen({ failPoll: true });
  stopHolder(clean);
  const verified = await settleIt(clean, { settleAs: 'success', note: 'Deployment Status shows it succeeded' });
  assert.equal(verified.record.verified, true);
  assert.equal(readBaselines(clean.root, ORG15).components['ApexClass:Foo'].recordedBy, 'reconcile');
  assert.equal(readBaselines(clean.root, ORG15).lastDeploy.opId, clean.record.opId);
});

test('reconcile: an unreadable slot needs a hand settlement, which keeps the note and the raw text', async () => {
  const torn = await kitWithOrg();
  write(torn.root, `.mp/journal/open-${ORG15}.json`, '{ torn');
  await assert.rejects(settleIt(torn), /slot is unreadable/);
  const moved = await settleIt(torn, { settleAs: 'failed', note: 'nothing ran (Deployment Status)' });
  assert.match(moved.detail, /kept the unreadable slot and your note/);
  assert.equal(readSlot(torn.root, ORG15), undefined);
  const kept = settledRecords(torn.root)[0];
  assert.match(kept.note, /nothing ran/);
  assert.equal(kept.unreadableSlot.raw, '{ torn');
});

test('reconcile (a) on a real deploy whose read-back mismatches stays open', async () => {
  const ctx = await laneWithOpen({ failPoll: true, reformatOnDeploy: true });
  stopHolder(ctx);
  const result = await settleIt(ctx);
  assert.equal(result.outcome, 'unresolved');
  assert.ok(readSlot(ctx.root, ORG15).record);
  assert.equal(settledRecords(ctx.root).length, 0);
});
