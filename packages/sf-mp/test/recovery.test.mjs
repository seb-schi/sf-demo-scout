// Focused recovery cases: provenance under concurrent commits, local-work preservation,
// empty XML values, recovery ownership, lane moves, the ID-less lookup, interrupted writes with
// a retry, and read-back cleanup.
import assert from 'node:assert/strict';
import { chmodSync, existsSync, readFileSync } from 'node:fs';
import { hostname } from 'node:os';
import { join } from 'node:path';
import { after, test } from 'node:test';
import { addApex, apexBody, APEX_META, cleanupTemps, commitAll, FakeOrg, fakeRuntime, git, makeKit, ORG15, write } from './helpers.mjs';

const { guardedDeploy } = await import('../src/deploy.mjs');
const { guardedRetrieve } = await import('../src/retrieve.mjs');
const { reconcile } = await import('../src/reconcile.mjs');
const { readBaselines, writeBaselines } = await import('../src/baselines.mjs');
const { journalDir, readSlot, thisHolder } = await import('../src/journal.mjs');
const { Refusal } = await import('../src/lane.mjs');
const { updateRegistry } = await import('../src/kit.mjs');
const { hashFiles } = await import('../src/hash.mjs');
const { xmlWithin } = await import('../src/xml.mjs');

after(cleanupTemps);

const run = {
  retrieve: (ctx, values, options = {}, rt = {}) => guardedRetrieve({ cwd: ctx.root, values, target: 'common', runtime: fakeRuntime(ctx.org, rt), dataDir: ctx.dataDir, ...options }),
  deploy: (ctx, values, options = {}, rt = {}) => guardedDeploy({ cwd: ctx.root, values, target: 'common', runtime: fakeRuntime(ctx.org, rt), dataDir: ctx.dataDir, ...options }),
  reconcile: (ctx, options = {}, rt = {}) => reconcile({ cwd: ctx.root, target: 'common', runtime: fakeRuntime(ctx.org, rt), dataDir: ctx.dataDir, ...options }),
};
const refused = (promise, pattern) => assert.rejects(promise, (error) => error instanceof Refusal && pattern.test(error.message));

async function lane() {
  const { root, dataDir } = await makeKit();
  addApex(root, 'Foo');
  commitAll(root, 'foo');
  const org = new FakeOrg();
  await org.seedFrom(root, ['ApexClass:Foo']);
  const ctx = { root, dataDir, org };
  await run.retrieve(ctx, ['ApexClass:Foo']);
  return ctx;
}

const stopHolder = (ctx) => {
  const record = readSlot(ctx.root, ORG15).record;
  write(ctx.root, `.mp/journal/open-${ORG15}.json`, JSON.stringify({ ...record, holder: { ...record.holder, pid: 999999 } }));
};

test('--merged with the merge committed while the retrieve runs: the baseline pairs the content with the commit that holds it', async () => {
  const ctx = await lane();
  ctx.org.put('ApexClass:Foo', [{ key: 'Foo.cls', bytes: apexBody('Foo', 'return 41;') }, { key: 'Foo.cls-meta.xml', bytes: APEX_META }], 'Setup User');
  write(ctx.root, 'force-app/main/default/classes/Foo.cls', apexBody('Foo', 'return 1;'));
  assert.equal((await run.retrieve(ctx, ['ApexClass:Foo'])).components[0].outcome, 'conflict');
  write(ctx.root, 'force-app/main/default/classes/Foo.cls', apexBody('Foo', 'return 41 + 1;'));
  commitAll(ctx.root, 'merged, committed before --merged');
  const before = git(ctx.root, 'rev-parse', 'HEAD');
  let during;
  await run.retrieve(ctx, ['ApexClass:Foo'], { merged: true }, {
    onRetrieve: () => {
      // Another terminal commits a further change while the retrieve waits on the network.
      write(ctx.root, 'force-app/main/default/classes/Foo.cls', apexBody('Foo', 'return 43;'));
      during = commitAll(ctx.root, 'committed during the retrieve');
    },
  });
  const source = readBaselines(ctx.root, ORG15).components['ApexClass:Foo'].source;
  assert.notEqual(source.revision, before);
  assert.equal(source.revision, during, 'the revision read after the network wait');
  const atRevision = [{ key: 'Foo.cls', bytes: git(ctx.root, 'show', `${during}:force-app/main/default/classes/Foo.cls`) + '\n' }, { key: 'Foo.cls-meta.xml', bytes: APEX_META }];
  assert.equal(source.hash, hashFiles(atRevision), 'and the content that revision holds');
});

test('a recorded revision that doesn\'t hold the baseline\'s content isn\'t trusted', async () => {
  const ctx = await lane();
  const old = git(ctx.root, 'rev-parse', 'HEAD');
  addApex(ctx.root, 'Foo', 'return 2;');
  commitAll(ctx.root, 'v2');
  assert.equal((await run.deploy(ctx, ['ApexClass:Foo'])).record.state, 'settled-success');
  // Point the baseline's revision at the old commit, which doesn't hold v2.
  const data = readBaselines(ctx.root, ORG15);
  data.components['ApexClass:Foo'].source.revision = old;
  writeBaselines(ctx.root, ORG15, data);
  git(ctx.root, 'checkout', '-q', '-b', 'from-old', old);
  addApex(ctx.root, 'Foo', 'return 3;');
  commitAll(ctx.root, 'v3 on the old line');
  const { record } = await run.deploy(ctx, ['ApexClass:Foo']);
  assert.match(record.result.reasons[0], /HEAD's history doesn't contain the version the org has/);
});

test('retrieve never writes over a file the project doesn\'t resolve because .forceignore hides it', async () => {
  const ctx = await lane();
  write(ctx.root, '.forceignore', '**/__tests__/**\n**/classes/Hidden.cls*\n');
  addApex(ctx.root, 'Hidden', 'return 7; // my local work');
  ctx.org.put('ApexClass:Hidden', [{ key: 'Hidden.cls', bytes: apexBody('Hidden', 'return 0;') }, { key: 'Hidden.cls-meta.xml', bytes: APEX_META }]);
  const result = await run.retrieve(ctx, ['ApexClass:Hidden']);
  assert.equal(result.components[0].outcome, 'conflict');
  assert.match(result.components[0].detail, /already exist \(hidden by \.forceignore\?\)/);
  assert.match(readFileSync(join(ctx.root, 'force-app/main/default/classes/Hidden.cls'), 'utf8'), /my local work/);
  assert.equal(readBaselines(ctx.root, ORG15).components['ApexClass:Hidden'], undefined);
  assert.equal(readSlot(ctx.root, ORG15), undefined, 'the slot is freed');
});

test('half a component in the project: SDR can\'t resolve it, so retrieve refuses and writes nothing', async () => {
  const ctx = await lane();
  write(ctx.root, 'force-app/main/default/classes/Half.cls-meta.xml', APEX_META.replace('Active', 'Inactive'));
  ctx.org.put('ApexClass:Half', [{ key: 'Half.cls', bytes: apexBody('Half', 'return 0;') }, { key: 'Half.cls-meta.xml', bytes: APEX_META }]);
  await refused(run.retrieve(ctx, ['ApexClass:Half']), /source doesn't resolve, so nothing was changed/);
  assert.match(readFileSync(join(ctx.root, 'force-app/main/default/classes/Half.cls-meta.xml'), 'utf8'), /Inactive/);
  assert.ok(!existsSync(join(ctx.root, 'force-app/main/default/classes/Half.cls')));
  assert.equal(readSlot(ctx.root, ORG15), undefined, 'the slot is freed');
});

test('empty XML values: a cleared element must be cleared in the org, and the API may omit it', () => {
  assert.equal(xmlWithin('<R><description></description></R>', '<R><description>old text</description></R>'), false);
  assert.equal(xmlWithin('<R><description/></R>', '<R><description>old text</description></R>'), false);
  assert.equal(xmlWithin('<R><description/></R>', '<R><label>x</label></R>'), true);
  assert.equal(xmlWithin('<R><v> </v></R>', '<R><v></v></R>'), false, 'whitespace is a value');
});

test('only one reconcile at a time: a live lock refuses the second', async () => {
  const ctx = await lane();
  addApex(ctx.root, 'Foo', 'return 2;');
  commitAll(ctx.root, 'v2');
  await run.deploy(ctx, ['ApexClass:Foo'], {}, { failPoll: true });
  stopHolder(ctx);
  write(ctx.root, `.mp/journal/reconcile-${ORG15}.lock`, JSON.stringify(thisHolder()));
  await refused(run.reconcile(ctx), /another sf mp reconcile is working/);
  write(ctx.root, `.mp/journal/reconcile-${ORG15}.lock`, JSON.stringify({ ...thisHolder(), pid: 999999 }));
  assert.equal((await run.reconcile(ctx)).outcome, 'reconciled-success', 'a dead lock is cleared');
  assert.ok(!existsSync(join(journalDir(ctx.root), `reconcile-${ORG15}.lock`)));
});

test('a retrieve holds the slot: a deploy started meanwhile is refused, and the slot is freed after', async () => {
  const ctx = await lane();
  let inner;
  await run.retrieve(ctx, ['ApexClass:Foo'], {}, {
    onRetrieve: async () => {
      inner = await run.deploy(ctx, ['ApexClass:Foo'], { dryRun: true }).catch((error) => error);
    },
  });
  assert.ok(inner instanceof Refusal && /still open|took the common org's slot/.test(inner.message), String(inner?.message));
  assert.equal(readSlot(ctx.root, ORG15), undefined);
  // An interrupted retrieve's slot is simply released by reconcile.
  write(ctx.root, `.mp/journal/open-${ORG15}.json`, JSON.stringify({ schema: 1, opId: 'r1', kind: 'retrieve', state: 'intent', holder: { pid: 999999, host: hostname() }, transitions: [] }));
  assert.equal((await run.reconcile(ctx)).outcome, 'released');
});

test('a lane moved while a deploy was starting: the deploy refuses at its slot', async () => {
  const ctx = await lane();
  await refused(run.deploy(ctx, ['ApexClass:Foo'], { dryRun: true }, {
    onConnect: () => updateRegistry(ctx.dataDir, (registry) => ({ orgs: { ...registry.orgs, [ORG15]: { lane: '/moved/elsewhere', boundAt: 'x' } } })),
  }), /lane is now \/moved\/elsewhere/);
  assert.equal(readSlot(ctx.root, ORG15), undefined);
});

test('ID-less recovery looks for the recorded submitter\'s request, in the operation\'s mode', async () => {
  const ctx = await lane();
  addApex(ctx.root, 'Foo', 'return 2;');
  commitAll(ctx.root, 'v2');
  await run.deploy(ctx, ['ApexClass:Foo'], {}, { noJobId: true });
  stopHolder(ctx);
  const rt = fakeRuntime(ctx.org, { connectUser: 'steward@example.com' });
  const result = await reconcile({ cwd: ctx.root, target: 'common', runtime: rt, dataDir: ctx.dataDir });
  assert.equal(result.outcome, 'reconciled-success');
  assert.deepEqual(rt.calls.find((c) => c[0] === 'deployRequestsSince')[1], 'captain@example.com', 'the submitter, not the steward');
  for (const requests of [
    [{ id: '0Af1', checkOnly: false }, { id: '0Af2', checkOnly: false }], // a preceding request
    [{ id: '0Af3', checkOnly: true }], // the wrong mode
  ]) {
    const other = await lane();
    addApex(other.root, 'Foo', 'return 2;');
    commitAll(other.root, 'v2');
    await run.deploy(other, ['ApexClass:Foo'], {}, { noJobId: true });
    stopHolder(other);
    assert.equal((await run.reconcile(other, {}, { requests: requests.map((r) => ({ ...r, user: 'captain@example.com' })) })).outcome, 'needs-steward', JSON.stringify(requests));
  }
});

test('the job ID and the settled record can\'t be written: the slot stays, and reconcile finishes the job', async () => {
  const ctx = await lane();
  addApex(ctx.root, 'Foo', 'return 2;');
  commitAll(ctx.root, 'v2');
  const dir = journalDir(ctx.root);
  let outcome;
  try {
    outcome = await run.deploy(ctx, ['ApexClass:Foo'], {}, { afterSubmit: () => chmodSync(dir, 0o500) });
  } finally {
    chmodSync(dir, 0o700);
  }
  assert.match(outcome.record.note, /couldn't write the settled record/);
  assert.equal(readSlot(ctx.root, ORG15).record.state, 'submitting', 'what could be written last');
  stopHolder(ctx);
  assert.equal((await run.reconcile(ctx)).outcome, 'reconciled-success');
  assert.equal(readSlot(ctx.root, ORG15), undefined);
});

test('the baselines can\'t be written after a deploy: the slot stays dispatched, and reconcile completes it', async () => {
  const ctx = await lane();
  addApex(ctx.root, 'Foo', 'return 2;');
  commitAll(ctx.root, 'v2');
  const baselines = join(ctx.root, '.mp', 'baselines');
  let retrieves = 0;
  try {
    await assert.rejects(run.deploy(ctx, ['ApexClass:Foo'], {}, { onRetrieve: () => { if (++retrieves === 2) chmodSync(baselines, 0o500); } }));
  } finally {
    chmodSync(baselines, 0o700);
  }
  assert.equal(readSlot(ctx.root, ORG15).record.state, 'dispatched');
  stopHolder(ctx);
  assert.equal((await run.reconcile(ctx)).outcome, 'reconciled-success');
  assert.equal(readBaselines(ctx.root, ORG15).components['ApexClass:Foo'].recordedBy, 'deploy');
});

test('read-back output is cleaned up only after the read-back finished', async () => {
  const ctx = await lane();
  addApex(ctx.root, 'Foo', 'return 2;');
  commitAll(ctx.root, 'v2');
  const rt = fakeRuntime(ctx.org, { writeOutput: true });
  const { record } = await guardedDeploy({ cwd: ctx.root, values: ['ApexClass:Foo'], target: 'common', runtime: rt, dataDir: ctx.dataDir });
  assert.equal(record.state, 'settled-success');
  for (const [, , outDir] of rt.calls.filter((c) => c[0] === 'retrieve')) assert.ok(!existsSync(outDir), `${outDir} left behind`);
});

test('a kit project in a subfolder of its Git repo deploys and anchors its baselines', async () => {
  const { temp } = await import('./helpers.mjs');
  const repo = temp('sf-mp-repo-');
  git(repo, 'init', '-q', '-b', 'main');
  git(repo, 'config', 'user.name', 'Lane Captain');
  git(repo, 'config', 'user.email', 'captain@example.com');
  git(repo, 'config', 'commit.gpgsign', 'false');
  write(repo, 'README.md', 'monorepo\n');
  const root = join(repo, 'apps', 'demo');
  write(root, 'sfdx-project.json', JSON.stringify({ packageDirectories: [{ path: 'force-app', default: true }], sourceApiVersion: '64.0' }));
  write(root, '.mp/config.json', JSON.stringify({ schema: 1, commonOrgId: '00D000000000042EAC', session: 's', authority: 'lane', testLevel: 'NoTestRun' }));
  write(root, '.mp/.gitignore', 'journal/\nbaselines/\nmerge/\nbackups/\n');
  addApex(root, 'Foo');
  commitAll(repo, 'start');
  const dataDir = temp('sf-mp-data-');
  await updateRegistry(dataDir, () => ({ orgs: { [ORG15]: { lane: root, boundAt: 'x' } } }));
  const org = new FakeOrg();
  await org.seedFrom(root, ['ApexClass:Foo']);
  const ctx = { root, dataDir, org };
  assert.equal((await run.retrieve(ctx, ['ApexClass:Foo'])).components[0].outcome, 'matches');
  assert.ok(readBaselines(root, ORG15).components['ApexClass:Foo'].source.revision, 'anchored to the commit');
  addApex(root, 'Foo', 'return 2;');
  commitAll(repo, 'v2');
  assert.equal((await run.deploy(ctx, ['ApexClass:Foo'])).record.state, 'settled-success');
});

test('a sole request stamped before submission is never taken as the job', async () => {
  const ctx = await lane();
  addApex(ctx.root, 'Foo', 'return 2;');
  commitAll(ctx.root, 'v2');
  await run.deploy(ctx, ['ApexClass:Foo'], {}, { noJobId: true });
  stopHolder(ctx);
  const submitting = readSlot(ctx.root, ORG15).record.transitions.find((t) => t.state === 'submitting').at;
  const earlier = new Date(new Date(submitting).getTime() - 10_000).toISOString();
  const result = await run.reconcile(ctx, {}, { requests: [{ id: '0AfEarlier', checkOnly: false, createdDate: earlier, user: 'captain@example.com' }] });
  assert.equal(result.outcome, 'needs-steward');
});

test('a missing empty element with attributes (an LWC design property) is a mismatch', () => {
  const candidate = '<LightningComponentBundle><targetConfigs><targetConfig targets="lightning__RecordPage"><property name="greeting" type="String"/><objects><object>Account</object></objects></targetConfig></targetConfigs></LightningComponentBundle>';
  const org = '<LightningComponentBundle><targetConfigs><targetConfig targets="lightning__RecordPage"><objects><object>Account</object></objects></targetConfig></targetConfigs></LightningComponentBundle>';
  assert.equal(xmlWithin(candidate, org), false);
  assert.equal(xmlWithin(candidate, org.replace('<objects>', '<property name="greeting" type="String"/><objects>')), true);
});

test('a baseline from before source keys: the deploy says so, and retrieve plus --merged migrates it', async () => {
  const ctx = await lane();
  const data = readBaselines(ctx.root, ORG15);
  delete data.components['ApexClass:Foo'].source.keys;
  writeBaselines(ctx.root, ORG15, data);
  addApex(ctx.root, 'Foo', 'return 2;');
  commitAll(ctx.root, 'local work on an old baseline');
  assert.match((await run.deploy(ctx, ['ApexClass:Foo'])).record.result.reasons[0], /comes from an older sf mp/);
  assert.equal((await run.retrieve(ctx, ['ApexClass:Foo'])).components[0].outcome, 'conflict', 'saves the org copy');
  assert.equal((await run.retrieve(ctx, ['ApexClass:Foo'], { merged: true })).components[0].outcome, 'merged');
  assert.ok(readBaselines(ctx.root, ORG15).components['ApexClass:Foo'].source.keys.length);
  assert.equal((await run.deploy(ctx, ['ApexClass:Foo'])).record.state, 'settled-success');
});
