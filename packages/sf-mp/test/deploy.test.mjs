// The guarded deploy sequence, end to end, with real Git, real SDR resolution and a fake org.
import assert from 'node:assert/strict';
import { chmodSync, existsSync, mkdirSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { after, test } from 'node:test';
import { addApex, addField, addLwc, apexBody, cleanupTemps, commitAll, FakeOrg, fakeRuntime, git, makeKit, ORG15, write } from './helpers.mjs';

const { guardedDeploy } = await import('../src/deploy.mjs');
const { guardedRetrieve } = await import('../src/retrieve.mjs');
const { readBaselines } = await import('../src/baselines.mjs');
const { readSlot, settledRecords, slotPath, journalDir } = await import('../src/journal.mjs');
const { Refusal } = await import('../src/lane.mjs');
const { updateRegistry } = await import('../src/kit.mjs');

after(cleanupTemps);

/** A lane whose org holds exactly the committed components, with baselines taken by retrieve. */
async function lane(keys, setup) {
  const { root, dataDir } = await makeKit();
  setup(root);
  commitAll(root, 'components');
  const org = new FakeOrg();
  await org.seedFrom(root, keys);
  const result = await guardedRetrieve({ cwd: root, values: keys, target: 'common', runtime: fakeRuntime(org), dataDir });
  assert.ok(result.components.every((c) => c.outcome === 'matches'), JSON.stringify(result.components));
  return { root, dataDir, org };
}

const deploy = (ctx, values, options = {}, runtimeOptions = {}) =>
  guardedDeploy({ cwd: ctx.root, values, target: 'common', runtime: fakeRuntime(ctx.org, runtimeOptions), dataDir: ctx.dataDir, ...options });

const refused = async (promise, pattern) => {
  await assert.rejects(promise, (error) => error instanceof Refusal && pattern.test(error.message));
};

test('a fresh candidate deploys, reads back, and moves the baseline and the last deploy', async () => {
  const ctx = await lane(['ApexClass:Foo'], (root) => addApex(root, 'Foo'));
  addApex(ctx.root, 'Foo', 'return 1;');
  const rev = commitAll(ctx.root, 'v2');
  const { record, exitCode } = await deploy(ctx, ['ApexClass:Foo']);
  assert.equal(exitCode, 0);
  assert.equal(record.state, 'settled-success');
  assert.deepEqual(record.transitions.map((t) => t.state), ['intent', 'submitting', 'dispatched', 'settled-success']);
  assert.match(ctx.org.components.get('ApexClass:Foo').files.find((f) => f.key === 'Foo.cls').bytes.toString(), /return 1;/);
  const baselines = readBaselines(ctx.root, ORG15);
  assert.equal(baselines.lastDeploy.revision, rev);
  assert.equal(baselines.components['ApexClass:Foo'].source.revision, rev);
  assert.equal(readSlot(ctx.root, ORG15), undefined);
  assert.equal(settledRecords(ctx.root)[0].opId, record.opId);
  const backup = readFileSync(join(ctx.root, '.mp', 'backups', record.opId, 'ApexClass_Foo', 'files', 'Foo.cls'), 'utf8');
  assert.match(backup, /return 0;/, 'the backup is the org copy from before the deploy');
});

test('a check-only deploy settles without touching the baselines or the last deploy', async () => {
  const ctx = await lane(['ApexClass:Foo'], (root) => addApex(root, 'Foo'));
  const before = readBaselines(ctx.root, ORG15);
  addApex(ctx.root, 'Foo', 'return 2;');
  commitAll(ctx.root, 'v2');
  const { record } = await deploy(ctx, ['ApexClass:Foo'], { dryRun: true });
  assert.equal(record.state, 'settled-success');
  assert.equal(record.checkOnly, true);
  assert.deepEqual(readBaselines(ctx.root, ORG15), before);
  assert.match(ctx.org.components.get('ApexClass:Foo').files.find((f) => f.key === 'Foo.cls').bytes.toString(), /return 0;/);
});

test('a change in the org since the baseline blocks, naming who and when, and saves the org copy', async () => {
  const ctx = await lane(['ApexClass:Foo'], (root) => addApex(root, 'Foo'));
  ctx.org.put('ApexClass:Foo', [
    { key: 'Foo.cls', bytes: apexBody('Foo', 'return 42;') },
    { key: 'Foo.cls-meta.xml', bytes: readFileSync(join(ctx.root, 'force-app/main/default/classes/Foo.cls-meta.xml')) },
  ], 'Setup User', '2026-10-18T02:00:00.000Z');
  addApex(ctx.root, 'Foo', 'return 1;');
  commitAll(ctx.root, 'mine');
  const { record, exitCode } = await deploy(ctx, ['ApexClass:Foo']);
  assert.equal(exitCode, 2);
  assert.equal(record.state, 'settled-failed');
  assert.equal(record.result.sent, false);
  assert.match(record.result.reasons[0], /changed in the org since your baseline by Setup User on 2026-10-18T02:00:00.000Z/);
  assert.match(record.result.reasons[0], /differs in Foo\.cls/);
  assert.equal(ctx.org.deploys.length, 0, 'nothing was sent');
  assert.match(readFileSync(join(ctx.root, '.mp', 'merge', ORG15, 'ApexClass_Foo', 'files', 'Foo.cls'), 'utf8'), /return 42;/);
});

test('a missing or unknown baseline blocks', async () => {
  const ctx = await lane(['ApexClass:Foo'], (root) => {
    addApex(root, 'Foo');
    addApex(root, 'Bar');
  });
  await ctx.org.seedFrom(ctx.root, ['ApexClass:Bar']);
  let { record } = await deploy(ctx, ['ApexClass:Bar']);
  assert.match(record.result.reasons[0], /Bar has no baseline/);
  ({ record } = await deploy(ctx, ['ApexClass:Foo'], {}, { unknown: ['ApexClass:Foo'] }));
  assert.match(record.result.reasons[0], /can't be read/);
});

test('confirmed-absent allows a create; a component created meanwhile blocks', async () => {
  const ctx = await lane(['ApexClass:Foo'], (root) => addApex(root, 'Foo'));
  addApex(ctx.root, 'Fresh');
  addApex(ctx.root, 'Racy');
  commitAll(ctx.root, 'new classes');
  const taken = await guardedRetrieve({ cwd: ctx.root, values: ['ApexClass:Fresh', 'ApexClass:Racy'], target: 'common', runtime: fakeRuntime(ctx.org), dataDir: ctx.dataDir });
  assert.deepEqual(taken.components.map((c) => c.outcome), ['absent', 'absent']);
  let { record } = await deploy(ctx, ['ApexClass:Fresh']);
  assert.equal(record.state, 'settled-success');
  assert.ok(ctx.org.components.has('ApexClass:Fresh'));
  ctx.org.put('ApexClass:Racy', [{ key: 'Racy.cls', bytes: apexBody('Racy', 'return 9;') }, { key: 'Racy.cls-meta.xml', bytes: '<x/>' }], 'Other Builder');
  ({ record } = await deploy(ctx, ['ApexClass:Racy']));
  assert.match(record.result.reasons[0], /created in the org since your baseline by Other Builder/);
});

test('uncommitted or untracked selected files are refused, and nothing is recorded', async () => {
  const ctx = await lane(['ApexClass:Foo'], (root) => addApex(root, 'Foo'));
  addApex(ctx.root, 'Foo', 'return 3;');
  await refused(deploy(ctx, ['ApexClass:Foo']), /commit these first.*Foo\.cls/);
  git(ctx.root, 'checkout', '--', '.');
  addApex(ctx.root, 'Untracked');
  await refused(deploy(ctx, ['ApexClass:Untracked']), /commit these first/);
  assert.equal(readSlot(ctx.root, ORG15), undefined);
  assert.equal(settledRecords(ctx.root).length, 0);
});

test('a branch without the version the org has is refused; amended history is found by content', async () => {
  const ctx = await lane(['ApexClass:Foo'], (root) => addApex(root, 'Foo'));
  const start = git(ctx.root, 'rev-parse', 'HEAD');
  addApex(ctx.root, 'Foo', 'return 1;');
  commitAll(ctx.root, 'v2');
  assert.equal((await deploy(ctx, ['ApexClass:Foo'])).record.state, 'settled-success');
  // A branch cut before v2 reached the org: its history lacks v2.
  git(ctx.root, 'checkout', '-q', '-b', 'stale', start);
  addApex(ctx.root, 'Foo', 'return 3;');
  commitAll(ctx.root, 'v3 on a stale branch');
  const { record } = await deploy(ctx, ['ApexClass:Foo']);
  assert.match(record.result.reasons[0], /HEAD's history doesn't contain the version the org has/);
  // Back on main, amend the deployed commit (same content, new SHA), then build on it.
  git(ctx.root, 'checkout', '-q', 'main');
  git(ctx.root, 'commit', '-q', '--amend', '-m', 'v2, reworded');
  addApex(ctx.root, 'Foo', 'return 4;');
  commitAll(ctx.root, 'v4');
  assert.equal((await deploy(ctx, ['ApexClass:Foo'])).record.state, 'settled-success');
});

test('an open operation blocks, and so does an unreadable slot', async () => {
  const ctx = await lane(['ApexClass:Foo'], (root) => addApex(root, 'Foo'));
  write(ctx.root, `.mp/journal/open-${ORG15}.json`, JSON.stringify({ schema: 1, opId: 'held', state: 'intent', transitions: [] }));
  await refused(deploy(ctx, ['ApexClass:Foo']), /operation held \(intent\) is still open/);
  write(ctx.root, `.mp/journal/open-${ORG15}.json`, '{ torn');
  await refused(deploy(ctx, ['ApexClass:Foo']), /slot for the common org is unreadable/);
  assert.equal(ctx.org.deploys.length, 0);
});

test('an unwritable journal refuses before anything is sent', async () => {
  const ctx = await lane(['ApexClass:Foo'], (root) => addApex(root, 'Foo'));
  const dir = journalDir(ctx.root);
  mkdirSync(dir, { recursive: true });
  chmodSync(dir, 0o500);
  try {
    await refused(deploy(ctx, ['ApexClass:Foo']), /couldn't write the intent record/);
  } finally {
    chmodSync(dir, 0o700);
  }
  assert.equal(ctx.org.deploys.length, 0);
});

test('when submitting can\'t be recorded, nothing is sent and the slot still says intent', async () => {
  const ctx = await lane(['ApexClass:Foo'], (root) => addApex(root, 'Foo'));
  const dir = journalDir(ctx.root);
  try {
    const { record, exitCode } = await deploy(ctx, ['ApexClass:Foo'], {}, { beforeSubmit: () => chmodSync(dir, 0o500) });
    assert.equal(exitCode, 1);
    assert.equal(record.result.sent, false);
  } finally {
    chmodSync(dir, 0o700);
  }
  assert.equal(ctx.org.deploys.length, 0, 'the deploy never left');
  assert.equal(readSlot(ctx.root, ORG15).record.state, 'intent');
});

test('a failure after submitting, a missing job ID or a lost status leaves the operation unresolved', async () => {
  for (const injected of [{ failAfterSubmit: true }, { noJobId: true }, { failPoll: true }, { notDone: true }]) {
    const ctx = await lane(['ApexClass:Foo'], (root) => addApex(root, 'Foo'));
    const { record, exitCode } = await deploy(ctx, ['ApexClass:Foo'], {}, injected);
    assert.equal(exitCode, 1, JSON.stringify(injected));
    assert.equal(record.state, 'unresolved', JSON.stringify(injected));
    assert.equal(readSlot(ctx.root, ORG15).record.state, 'unresolved');
    assert.equal(readBaselines(ctx.root, ORG15).lastDeploy, null);
  }
});

test('a failed deploy settles as failed and leaves the baselines alone', async () => {
  const ctx = await lane(['ApexClass:Foo'], (root) => addApex(root, 'Foo'));
  const before = readBaselines(ctx.root, ORG15);
  const { record } = await deploy(ctx, ['ApexClass:Foo'], {}, { deployFails: true });
  assert.equal(record.state, 'settled-failed');
  assert.equal(record.result.sent, true);
  assert.deepEqual(readBaselines(ctx.root, ORG15), before);
});

test('a read-back mismatch keeps the operation open and the baseline unchanged', async () => {
  const ctx = await lane(['ApexClass:Foo'], (root) => addApex(root, 'Foo'));
  const before = readBaselines(ctx.root, ORG15);
  addApex(ctx.root, 'Foo', 'return 5;');
  commitAll(ctx.root, 'v5');
  const { record } = await deploy(ctx, ['ApexClass:Foo'], {}, { reformatOnDeploy: true });
  assert.equal(record.state, 'unresolved');
  assert.match(record.note, /read-back doesn't match: ApexClass:Foo: Foo\.cls differs/);
  assert.deepEqual(readBaselines(ctx.root, ORG15), before);
  assert.ok(readSlot(ctx.root, ORG15).record, 'the slot stays taken');
});

test('the working tree is never read for the deploy, even when it changes mid-run', async () => {
  const ctx = await lane(['ApexClass:Foo'], (root) => addApex(root, 'Foo'));
  addApex(ctx.root, 'Foo', 'return 6;');
  commitAll(ctx.root, 'v6');
  const { record } = await deploy(ctx, ['ApexClass:Foo'], {}, { duringDeploy: () => addApex(ctx.root, 'Foo', 'return 999;') });
  assert.equal(record.state, 'settled-success');
  assert.match(ctx.org.components.get('ApexClass:Foo').files.find((f) => f.key === 'Foo.cls').bytes.toString(), /return 6;/);
});

test('an owned component needs its owner running the lane, or --approved-by', async () => {
  const ctx = await lane(['ApexClass:Foo'], (root) => addApex(root, 'Foo'));
  write(ctx.root, '.mp/owners.yaml', 'components:\n  ApexClass:Foo: Ada Owner\n');
  commitAll(ctx.root, 'owners');
  await refused(deploy(ctx, ['ApexClass:Foo'], { dryRun: true }), /owned by Ada Owner/);
  const { record } = await deploy(ctx, ['ApexClass:Foo'], { dryRun: true, approvedBy: ['Ada Owner'] });
  assert.deepEqual(record.approvals.map((a) => [a.component, a.owner]), [['ApexClass:Foo', 'Ada Owner']]);
  write(ctx.root, '.mp/owners.yaml', 'components:\n  ApexClass:*: Lane Captain\n');
  commitAll(ctx.root, 'owners: the captain owns Apex');
  assert.equal((await deploy(ctx, ['ApexClass:Foo'], { dryRun: true })).record.state, 'settled-success');
});

test('scope rules: wildcards, disabled and unknown types, the ceiling, replacements', async () => {
  const ctx = await lane(['ApexClass:Foo'], (root) => addApex(root, 'Foo'));
  await refused(deploy(ctx, ['ApexClass:*']), /wildcard/);
  await refused(deploy(ctx, ['ApexTrigger:T']), /isn't switched on in v1 yet/);
  await refused(deploy(ctx, ['Flow:F']), /Flow isn't enabled in v1/);
  await refused(deploy(ctx, Array.from({ length: 26 }, (_, i) => `ApexClass:C${i}`)), /over the ceiling of 25/);
  await refused(deploy(ctx, ['ApexClass:Missing']), /not found in the project: ApexClass:Missing/);
  const project = JSON.parse(readFileSync(join(ctx.root, 'sfdx-project.json'), 'utf8'));
  write(ctx.root, 'sfdx-project.json', JSON.stringify({ ...project, replacements: [{ filename: 'x', stringToReplace: 'a', replaceWithEnv: 'B' }] }));
  commitAll(ctx.root, 'replacements');
  await refused(deploy(ctx, ['ApexClass:Foo']), /replacements/);
});

test('fields: a picklist, in the candidate or the org, and a type change are refused; a text field deploys', async () => {
  const ctx = await lane(['CustomField:Thing__c.Note__c', 'CustomField:Thing__c.Kind__c'], (root) => {
    addField(root, 'Thing__c', 'Note__c', 'Text');
    addField(root, 'Thing__c', 'Kind__c', 'Text');
  });
  addField(ctx.root, 'Thing__c', 'Note__c', 'Text', '<length>120</length>');
  commitAll(ctx.root, 'longer note');
  const ok = await deploy(ctx, ['CustomField:Thing__c.Note__c'], { dryRun: true });
  assert.equal(ok.record.state, 'settled-success');
  assert.deepEqual(ok.record.components, ['CustomField:Thing__c.Note__c']);
  addField(ctx.root, 'Thing__c', 'Kind__c', 'Picklist', '<valueSet><valueSetDefinition><value><fullName>A</fullName><default>false</default><label>A</label></value></valueSetDefinition></valueSet>');
  commitAll(ctx.root, 'make it a picklist');
  let { record } = await deploy(ctx, ['CustomField:Thing__c.Kind__c']);
  assert.match(record.result.reasons.join(), /is a picklist/);
  addField(ctx.root, 'Thing__c', 'Kind__c', 'Number', '<precision>18</precision><scale>0</scale>');
  commitAll(ctx.root, 'make it a number');
  ({ record } = await deploy(ctx, ['CustomField:Thing__c.Kind__c']));
  assert.match(record.result.reasons.join(), /would change type from Text to Number/);
});

test('bundles: a dropped file and a hidden deployable file are refused; tests and local tooling are fine', async () => {
  const ctx = await lane(['LightningComponentBundle:card'], (root) => addLwc(root, 'card', { 'card.css': 'p { color: red; }\n' }));
  git(ctx.root, 'rm', '-q', 'force-app/main/default/lwc/card/card.css');
  commitAll(ctx.root, 'drop css');
  let { record } = await deploy(ctx, ['LightningComponentBundle:card']);
  assert.match(record.result.reasons.join(), /would drop card\.css from the org's bundle/);
  write(ctx.root, 'force-app/main/default/lwc/card/card.css', 'p { color: red; }\n');
  write(ctx.root, 'force-app/main/default/lwc/card/__tests__/card.test.js', 'test("x", () => {});\n');
  write(ctx.root, 'force-app/main/default/lwc/card/jsconfig.json', '{}\n');
  write(ctx.root, 'force-app/main/default/lwc/card/helper.js', 'export const x = 1;\n');
  write(ctx.root, '.forceignore', '**/__tests__/**\n**/jsconfig.json\n**/card/helper.js\n');
  commitAll(ctx.root, 'restore css; add tests, local tooling and a hidden deployable file');
  await refused(deploy(ctx, ['LightningComponentBundle:card']), /\.forceignore hides force-app\/main\/default\/lwc\/card\/helper\.js, which the deploy/);
  git(ctx.root, 'rm', '-q', 'force-app/main/default/lwc/card/helper.js');
  write(ctx.root, '.forceignore', '**/__tests__/**\n**/jsconfig.json\n');
  commitAll(ctx.root, 'no hidden deployable file; tests and jsconfig.json stay');
  ({ record } = await deploy(ctx, ['LightningComponentBundle:card']));
  assert.equal(record.state, 'settled-success');
});

test('another checkout of the same org, an unbound target and a missing --target-org are refused', async () => {
  const ctx = await lane(['ApexClass:Foo'], (root) => addApex(root, 'Foo'));
  await refused(guardedDeploy({ cwd: ctx.root, values: ['ApexClass:Foo'], runtime: fakeRuntime(ctx.org), dataDir: ctx.dataDir }), /pass --target-org explicitly/);
  await refused(deploy(ctx, ['ApexClass:Foo'], {}, { connectOrgId: '00D000000000009AAA' }), /not the common org/);
  await updateRegistry(ctx.dataDir, (registry) => ({ orgs: { ...registry.orgs, [ORG15]: { lane: '/somewhere/else', boundAt: 'x' } } }));
  await refused(deploy(ctx, ['ApexClass:Foo']), /lane on this machine is \/somewhere\/else/);
});

test('the journal keeps one record per settled operation', async () => {
  const ctx = await lane(['ApexClass:Foo'], (root) => addApex(root, 'Foo'));
  await deploy(ctx, ['ApexClass:Foo'], { dryRun: true });
  await deploy(ctx, ['ApexClass:Foo'], { dryRun: true });
  const names = readdirSync(journalDir(ctx.root));
  assert.equal(names.filter((n) => n.endsWith('.json')).length, 2);
  assert.ok(!existsSync(slotPath(ctx.root, ORG15)));
});
