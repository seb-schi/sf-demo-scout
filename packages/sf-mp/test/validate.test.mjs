// `sf mp validate` (a check-only deploy into the common org, for teams on Lifecycle Center), guard-only
// registration without a kit project (a captain's and a builder's), and the effect bridge Scout calls, with real
// SDR resolution and a fake org.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { after, test } from 'node:test';
import { addApex, cleanupTemps, FakeOrg, fakeRuntime, makeKit, ORG15, OTHER, temp, write } from './helpers.mjs';

const { guardedValidate } = await import('../src/validate.mjs');
const { init } = await import('../src/init.mjs');
const { Refusal } = await import('../src/lane.mjs');
const { readRegistry, updateRegistry } = await import('../src/kit.mjs');
const { preDeployReasons, decide } = await import('../src/guard.mjs');

after(cleanupTemps);

const LAYOUT = '<?xml version="1.0" encoding="UTF-8"?>\n<Layout xmlns="http://soap.sforce.com/2006/04/metadata">\n    <showHighlightsPanel>true</showHighlightsPanel>\n</Layout>\n';

/** A team checkout (no .mp folder) and a data dir whose registry guards the common org, as its captain's by default. */
async function captain({ guard = true, lifecycleCaptain = true } = {}) {
  const root = temp('sf-mp-lc-');
  write(root, 'sfdx-project.json', JSON.stringify({ packageDirectories: [{ path: 'force-app', default: true }], sourceApiVersion: '64.0' }));
  const dataDir = temp('sf-mp-lc-data-');
  const binding = { role: 'guard', checkout: root, boundAt: '2026-10-18T00:00:00Z', ...(lifecycleCaptain ? { lifecycleCaptain: true } : {}) };
  if (guard) await updateRegistry(dataDir, (registry) => ({ orgs: { ...registry.orgs, [ORG15]: binding } }));
  const candidate = join(root, '.scout', 'candidate');
  mkdirSync(candidate, { recursive: true });
  return { root, dataDir, candidate };
}

const refused = async (promise, pattern) => {
  await assert.rejects(promise, (error) => error instanceof Refusal && pattern.test(error.message));
};

test('a validation is check-only, runs exactly the named tests, and leaves the org unchanged', async () => {
  const ctx = await captain();
  addApex(ctx.candidate, 'Invoice', 'return 2;');
  const org = new FakeOrg();
  const runtime = fakeRuntime(org, { testsRun: 2 });
  const result = await guardedValidate({ cwd: ctx.root, target: 'common', sourceDir: ctx.candidate, tests: ['InvoiceTest'], runtime, dataDir: ctx.dataDir });
  assert.equal(result.validated, true);
  assert.equal(result.checkOnly, true);
  assert.deepEqual(result.components, ['ApexClass:Invoice']);
  const [, keys, apiOptions] = runtime.calls.find((call) => call[0] === 'deploy');
  assert.deepEqual(keys, ['ApexClass:Invoice']);
  assert.equal(apiOptions.checkOnly, true);
  assert.equal(apiOptions.testLevel, 'RunSpecifiedTests');
  assert.deepEqual(apiOptions.runTests, ['InvoiceTest']);
  assert.equal(org.components.size, 0, 'a check-only deploy changes nothing in the org');
});

test('a validation whose named tests never ran does not count', async () => {
  const ctx = await captain();
  addApex(ctx.candidate, 'Invoice');
  const result = await guardedValidate({ cwd: ctx.root, target: 'common', sourceDir: ctx.candidate, tests: ['InvoiceTest'], runtime: fakeRuntime(new FakeOrg(), { testsRun: 0 }), dataDir: ctx.dataDir });
  assert.equal(result.validated, false);
  assert.match(result.failures.join('\n'), /ran none of the named tests/);
});

test('ranNone: only a successful check-only deploy that enabled tests and ran none of them proves the platform skipped them', async () => {
  const ctx = await captain();
  addApex(ctx.candidate, 'Invoice');
  const run = (options) => guardedValidate({ cwd: ctx.root, target: 'common', sourceDir: ctx.candidate, tests: ['InvoiceTest'],
    runtime: fakeRuntime(new FakeOrg(), options), dataDir: ctx.dataDir });
  const skipped = await run({ testsRun: 0 });
  assert.equal(skipped.validated, false, 'still not validated');
  assert.equal(skipped.ranNone, true);
  assert.equal((await run({ testsRun: 2 })).ranNone, false, 'tests ran');
  assert.equal((await run({ testsRun: 0, runTestsEnabled: false })).ranNone, false, 'the platform never enabled tests');
});

test('ranNone is never set when the deploy failed', async () => {
  const ctx = await captain();
  addApex(ctx.candidate, 'Invoice');
  const failed = await guardedValidate({ cwd: ctx.root, target: 'common', sourceDir: ctx.candidate, tests: ['InvoiceTest'],
    runtime: fakeRuntime(new FakeOrg(), { testsRun: 0, deployFails: true }), dataDir: ctx.dataDir });
  assert.equal(failed.ranNone, false, 'a failed deploy proves nothing about tests');
});

test('source without Apex validates with no tests; Apex never does', async () => {
  const ctx = await captain();
  write(ctx.candidate, 'force-app/main/default/layouts/Probe__c-Probe Layout.layout-meta.xml', LAYOUT);
  const runtime = fakeRuntime(new FakeOrg());
  const result = await guardedValidate({ cwd: ctx.root, target: 'common', sourceDir: ctx.candidate, noTests: true, runtime, dataDir: ctx.dataDir });
  assert.equal(result.validated, true);
  assert.equal(runtime.calls.find((call) => call[0] === 'deploy')[2].testLevel, 'NoTestRun');
  addApex(ctx.candidate, 'Invoice');
  await refused(guardedValidate({ cwd: ctx.root, target: 'common', sourceDir: ctx.candidate, noTests: true, runtime, dataDir: ctx.dataDir }), /holds Apex, so it needs tests/);
});

test('validate refuses an unguarded org, a missing choice of tests, and odd test names', async () => {
  const ctx = await captain({ guard: false });
  addApex(ctx.candidate, 'Invoice');
  const runtime = fakeRuntime(new FakeOrg());
  await refused(guardedValidate({ cwd: ctx.root, target: 'common', sourceDir: ctx.candidate, tests: ['InvoiceTest'], runtime, dataDir: ctx.dataDir }), /isn't a common org on this machine/);
  const guarded = await captain();
  addApex(guarded.candidate, 'Invoice');
  await refused(guardedValidate({ cwd: guarded.root, target: 'common', sourceDir: guarded.candidate, runtime, dataDir: guarded.dataDir }), /--tests <ApexClass>/);
  await refused(guardedValidate({ cwd: guarded.root, target: 'common', sourceDir: guarded.candidate, tests: ['A'], noTests: true, runtime, dataDir: guarded.dataDir }), /--tests <ApexClass>/);
  await refused(guardedValidate({ cwd: guarded.root, target: 'common', sourceDir: guarded.candidate, tests: ['Bad Name;'], runtime, dataDir: guarded.dataDir }), /not an Apex class name/);
  assert.equal(runtime.calls.filter((call) => call[0] === 'deploy').length, 0, 'nothing was sent');
});

test('only the captain\'s binding validates: a builder\'s guard and a lane are refused before anything is sent', async () => {
  const builder = await captain({ lifecycleCaptain: false });
  addApex(builder.candidate, 'Invoice');
  const runtime = fakeRuntime(new FakeOrg());
  await refused(guardedValidate({ cwd: builder.root, target: 'common', sourceDir: builder.candidate, tests: ['InvoiceTest'], runtime, dataDir: builder.dataDir }), /only a Lifecycle Center team's captain validates/);
  const lane = await makeKit();
  addApex(join(lane.root, '.scout', 'candidate'), 'Invoice');
  await refused(guardedValidate({ cwd: lane.root, target: 'common', sourceDir: join(lane.root, '.scout', 'candidate'), tests: ['InvoiceTest'], runtime, dataDir: lane.dataDir }), /only a Lifecycle Center team's captain validates/);
  assert.equal(runtime.calls.filter((call) => call[0] === 'deploy').length, 0, 'nothing was sent');
});

test('the deploy listener lets the validation through only as marked, and the guard still refuses quick deploy', async () => {
  const bound = new Set([ORG15]);
  assert.deepEqual(preDeployReasons({ orgId: ORG15, keys: ['ApexClass:Invoice'], bound, mark: { orgId: ORG15, keys: ['ApexClass:Invoice'] } }), []);
  assert.ok(preDeployReasons({ orgId: ORG15, keys: ['ApexClass:Invoice'], bound, mark: undefined }).length, 'an unmarked deploy is stopped');
  const ctx = await captain();
  const quick = await decide({ Command: { id: 'project:deploy:quick' }, argv: ['--job-id', '0Af000000000001'], cwd: ctx.root, dataDir: ctx.dataDir, loadCore: () => ({}) });
  assert.match(quick.reasons.join('\n'), /can't be checked by the multiplayer guard/);
});

test('guard-only outside a kit project binds the org named with --target-org', async () => {
  const ctx = await captain({ guard: false });
  const result = await init({ cwd: ctx.root, target: 'common', guardOnly: true, runtime: fakeRuntime(new FakeOrg()), dataDir: ctx.dataDir, env: {}, home: temp() });
  assert.equal(result.role, 'guard');
  assert.equal(result.commonOrgId, ORG15);
  assert.equal(readRegistry(ctx.dataDir).orgs[ORG15].role, 'guard');
  await refused(init({ cwd: ctx.root, guardOnly: true, runtime: fakeRuntime(new FakeOrg()), dataDir: temp(), env: {}, home: temp() }), /or the common org itself with --target-org/);
  const other = await init({ cwd: ctx.root, target: 'other', guardOnly: true, runtime: fakeRuntime(new FakeOrg(), { connectOrgId: OTHER }), dataDir: ctx.dataDir, env: {}, home: temp() });
  assert.equal(other.commonOrgId, OTHER.slice(0, 15));
  assert.equal(readRegistry(ctx.dataDir).orgs[ORG15].lifecycleCaptain, undefined, "a builder's binding isn't a captain's");
});

test('--lifecycle-captain marks the captain\'s binding, and goes only with --guard-only outside a kit project', async () => {
  const ctx = await captain({ guard: false });
  const result = await init({ cwd: ctx.root, target: 'common', guardOnly: true, lifecycleCaptain: true, runtime: fakeRuntime(new FakeOrg()), dataDir: ctx.dataDir, env: {}, home: temp() });
  assert.equal(result.lifecycleCaptain, true);
  assert.equal(readRegistry(ctx.dataDir).orgs[ORG15].lifecycleCaptain, true);
  await init({ cwd: ctx.root, target: 'common', guardOnly: true, runtime: fakeRuntime(new FakeOrg()), dataDir: ctx.dataDir, env: {}, home: temp() });
  assert.equal(readRegistry(ctx.dataDir).orgs[ORG15].lifecycleCaptain, undefined, 'binding again as a builder hands the captaincy back');
  await refused(init({ cwd: ctx.root, target: 'common', lifecycleCaptain: true, runtime: fakeRuntime(new FakeOrg()), dataDir: ctx.dataDir, env: {}, home: temp() }), /goes with --guard-only/);
  const kit = await makeKit({ register: false });
  await refused(init({ cwd: kit.root, guardOnly: true, lifecycleCaptain: true, runtime: fakeRuntime(new FakeOrg()), dataDir: kit.dataDir, env: {}, home: temp() }), /no kit project/);
});

test('the effect bridge checks Aura bundles for dropped files, as it does LWC, and passes complete bundles', () => {
  const bridge = new URL('../scripts/effects.mjs', import.meta.url).pathname;
  const b64 = (text) => Buffer.from(text).toString('base64');
  const bundle = (keys) => keys.map((key) => ({ key, b64: b64(`// ${key}\n`) }));
  const run = (items) => JSON.parse(execFileSync(process.execPath, [bridge], { input: JSON.stringify(items), encoding: 'utf8', env: process.env }));
  const full = ['probe.cmp', 'probe.cmp-meta.xml', 'probeController.js'];
  const report = run([
    { key: 'AuraDefinitionBundle:probe', candidate: bundle(['probe.cmp', 'probe.cmp-meta.xml']), org: bundle(full) },
    { key: 'LightningComponentBundle:card', candidate: bundle(['card.js', 'card.js-meta.xml']), org: bundle(['card.js', 'card.html', 'card.js-meta.xml']) },
    { key: 'AuraDefinitionBundle:whole', candidate: bundle(full), org: bundle(full) },
    { key: 'AuraDefinitionBundle:fresh', candidate: bundle(full), org: null },
  ]);
  assert.match(report['AuraDefinitionBundle:probe'].join('\n'), /would drop probeController\.js/);
  assert.match(report['LightningComponentBundle:card'].join('\n'), /would drop card\.html/);
  assert.equal(report['AuraDefinitionBundle:whole'], undefined);
  assert.equal(report['AuraDefinitionBundle:fresh'], undefined);
});
