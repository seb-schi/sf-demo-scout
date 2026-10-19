// 0.2.0 for team use: guard-only machines, the steward route and its effect checks, conflict
// reports that name the local files and the saved org copy, and `verified` in the JSON record.
import assert from 'node:assert/strict';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { after, test } from 'node:test';
import { addApex, cleanupTemps, commitAll, FakeOrg, fakeRuntime, makeKit, ORG15, temp, write } from './helpers.mjs';

const { guardedDeploy } = await import('../src/deploy.mjs');
const { guardedRetrieve } = await import('../src/retrieve.mjs');
const { candidateProblems, compareWithOrg, pageAssignments, parseEntries } = await import('../src/types.mjs');
const { init } = await import('../src/init.mjs');
const { boundOrgs, readRegistry, updateRegistry } = await import('../src/kit.mjs');
const { Refusal } = await import('../src/lane.mjs');
const { describeRecord } = await import('../src/command.mjs');

after(cleanupTemps);

const refused = async (promise, pattern) => {
  await assert.rejects(promise, (error) => error instanceof Refusal && pattern.test(error.message));
};

const OVERRIDE = (name, type, content = '') =>
  `    <actionOverrides>\n        <actionName>${name}</actionName>\n        ${content ? `<content>${content}</content>\n        ` : ''}<formFactor>Large</formFactor>\n        <type>${type}</type>\n    </actionOverrides>\n`;
const objectXml = (overrides = OVERRIDE('View', 'Default')) =>
  `<?xml version="1.0" encoding="UTF-8"?>\n<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">\n${overrides}    <deploymentStatus>Deployed</deploymentStatus>\n    <label>Thing</label>\n    <nameField>\n        <label>Thing Name</label>\n        <type>Text</type>\n    </nameField>\n    <pluralLabel>Things</pluralLabel>\n    <sharingModel>ReadWrite</sharingModel>\n</CustomObject>\n`;
const permsetXml = (fields) =>
  `<?xml version="1.0" encoding="UTF-8"?>\n<PermissionSet xmlns="http://soap.sforce.com/2006/04/metadata">\n${fields.map((f) => `    <fieldPermissions>\n        <editable>true</editable>\n        <field>${f}</field>\n        <readable>true</readable>\n    </fieldPermissions>\n`).join('')}    <label>Thing Access</label>\n</PermissionSet>\n`;
const file = (key, text) => ({ key, bytes: Buffer.from(text) });

test('the steward allow-list: refused without --steward, allowed with it; others stay refused', () => {
  assert.match(parseEntries(['CustomObject:Thing__c']).problems[0], /isn't enabled in v1 .*--steward/);
  const ok = parseEntries(['CustomObject:Thing__c', 'PermissionSet:Thing_Access', 'ApexClass:Foo'], { steward: true });
  assert.deepEqual(ok.problems, []);
  assert.deepEqual(ok.entries.map((e) => e.steward), [true, true, false]);
  assert.match(parseEntries(['Flow:F'], { steward: true }).problems[0], /isn't switched on on the steward route yet/);
  for (const type of ['Profile', 'CaseSettings', 'AiAuthoringBundle', 'GenAiPromptTemplate', 'FlowDefinition']) {
    assert.match(parseEntries([`${type}:X`], { steward: true }).problems[0], /isn't enabled/, type);
  }
  assert.match(parseEntries(['ApexTrigger:T'], { steward: true }).problems[0], /isn't switched on in v1 yet/);
});

test('object-v1: a page assignment can\'t change on the steward route; default overrides are fine', () => {
  const entry = { key: 'CustomObject:Thing__c', type: 'CustomObject', name: 'Thing__c' };
  const candidate = (xml) => [file('Thing__c.object-meta.xml', xml)];
  assert.deepEqual(pageAssignments(objectXml()), []);
  assert.deepEqual(candidateProblems(entry, candidate(objectXml()), undefined), [], 'a new object with default overrides');
  assert.deepEqual(candidateProblems(entry, candidate(objectXml()), candidate(objectXml())), []);
  const page = OVERRIDE('View', 'Flexipage', 'Thing_Record_Page');
  assert.match(candidateProblems(entry, candidate(objectXml(page)), candidate(objectXml()))[0], /which pages or overrides users get/);
  assert.match(candidateProblems(entry, candidate(objectXml()), candidate(objectXml(page)))[0], /which pages/, 'removing one counts too');
  assert.match(candidateProblems(entry, candidate(objectXml(page)), undefined)[0], /which pages/, 'a new object assigning a page');
  assert.deepEqual(candidateProblems(entry, candidate(objectXml(page)), candidate(objectXml(page))), [], 'unchanged assignment');
});

test('flow-v1: an active version is refused, an inactive one passes', () => {
  const entry = { key: 'Flow:F', type: 'Flow', name: 'F' };
  const flow = (status) => [file('F.flow-meta.xml', `<?xml version="1.0" encoding="UTF-8"?>\n<Flow xmlns="http://soap.sforce.com/2006/04/metadata">\n    <label>F</label>\n    <status>${status}</status>\n</Flow>\n`)];
  assert.match(candidateProblems(entry, flow('Active'), undefined)[0], /active flow version/);
  assert.deepEqual(candidateProblems(entry, flow('Draft'), undefined), []);
});

async function stewardKit() {
  const { root, dataDir } = await makeKit();
  write(root, 'force-app/main/default/objects/Thing__c/Thing__c.object-meta.xml', objectXml());
  write(root, 'force-app/main/default/permissionsets/Thing_Access.permissionset-meta.xml', permsetXml(['Thing__c.Note__c']));
  commitAll(root, 'steward components');
  return { root, dataDir, org: new FakeOrg() };
}

test('a steward create: absent baselines, a real deploy, a matching read-back, recorded as steward', async () => {
  const ctx = await stewardKit();
  const keys = ['CustomObject:Thing__c', 'PermissionSet:Thing_Access'];
  await refused(guardedRetrieve({ cwd: ctx.root, values: keys, target: 'common', runtime: fakeRuntime(ctx.org), dataDir: ctx.dataDir }), /--steward/);
  const taken = await guardedRetrieve({ cwd: ctx.root, values: keys, steward: true, target: 'common', runtime: fakeRuntime(ctx.org), dataDir: ctx.dataDir });
  assert.deepEqual(taken.components.map((c) => c.outcome), ['absent', 'absent']);
  const { record, exitCode } = await guardedDeploy({ cwd: ctx.root, values: keys, steward: true, target: 'common', runtime: fakeRuntime(ctx.org), dataDir: ctx.dataDir });
  assert.equal(exitCode, 0, JSON.stringify(record.result));
  assert.equal(record.state, 'settled-success');
  assert.equal(record.steward, true);
  assert.ok(ctx.org.components.has('PermissionSet:Thing_Access'));
  assert.equal(describeRecord(record).verified, true);
  assert.equal(describeRecord(record).steward, true);

  // Someone grants a second field in the org: the next steward deploy of the stale copy is refused.
  ctx.org.put('PermissionSet:Thing_Access', [file('Thing_Access.permissionset-meta.xml', permsetXml(['Thing__c.Note__c', 'Thing__c.Kind__c']))], 'Setup User');
  write(ctx.root, 'force-app/main/default/permissionsets/Thing_Access.permissionset-meta.xml', permsetXml(['Thing__c.Note__c', 'Thing__c.Size__c']));
  commitAll(ctx.root, 'my grant');
  const stale = await guardedDeploy({ cwd: ctx.root, values: ['PermissionSet:Thing_Access'], steward: true, target: 'common', runtime: fakeRuntime(ctx.org), dataDir: ctx.dataDir });
  assert.equal(stale.record.state, 'settled-failed');
  assert.match(stale.record.result.reasons[0], /changed in the org since your baseline by Setup User/);
  assert.match(ctx.org.components.get('PermissionSet:Thing_Access').files[0].bytes.toString(), /Kind__c/, 'the grant survives');
});

test('a steward deploy can\'t assign a page through the object file', async () => {
  const ctx = await stewardKit();
  await guardedRetrieve({ cwd: ctx.root, values: ['CustomObject:Thing__c'], steward: true, target: 'common', runtime: fakeRuntime(ctx.org), dataDir: ctx.dataDir });
  write(ctx.root, 'force-app/main/default/objects/Thing__c/Thing__c.object-meta.xml', objectXml(OVERRIDE('View', 'Flexipage', 'Thing_Record_Page')));
  commitAll(ctx.root, 'assign a page');
  const { record } = await guardedDeploy({ cwd: ctx.root, values: ['CustomObject:Thing__c'], steward: true, target: 'common', runtime: fakeRuntime(ctx.org), dataDir: ctx.dataDir });
  assert.equal(record.state, 'settled-failed');
  assert.match(record.result.reasons.join(' '), /which pages or overrides users get/);
  assert.equal(ctx.org.deploys.length, 0, 'nothing was sent');
});

test('a conflict report names the local files and the saved org copy', async () => {
  const { root, dataDir } = await makeKit();
  addApex(root, 'Foo');
  commitAll(root, 'foo');
  const org = new FakeOrg();
  await org.seedFrom(root, ['ApexClass:Foo']);
  await guardedRetrieve({ cwd: root, values: ['ApexClass:Foo'], target: 'common', runtime: fakeRuntime(org), dataDir });
  org.put('ApexClass:Foo', [file('Foo.cls', 'public class Foo { /* org */ }\n'), file('Foo.cls-meta.xml', '<x/>\n')], 'Setup User');
  addApex(root, 'Foo', 'return 7;');
  commitAll(root, 'mine');
  const result = await guardedRetrieve({ cwd: root, values: ['ApexClass:Foo'], target: 'common', runtime: fakeRuntime(org), dataDir });
  const [item] = result.components;
  assert.equal(item.outcome, 'conflict');
  assert.deepEqual(item.files, ['force-app/main/default/classes/Foo.cls', 'force-app/main/default/classes/Foo.cls-meta.xml']);
  assert.ok(existsSync(join(item.saved, 'files', 'Foo.cls')));
});

test('guard-only: registered without a lane, it guards the org and refuses lane work; a lane replaces it', async () => {
  const { root, dataDir } = await makeKit({ register: false });
  const result = await init({ cwd: root, guardOnly: true, dataDir });
  assert.equal(result.role, 'guard');
  const registry = readRegistry(dataDir);
  assert.deepEqual(Object.keys(registry.orgs), [ORG15]);
  assert.equal(registry.orgs[ORG15].role, 'guard');
  assert.ok(boundOrgs(undefined, registry).has(ORG15), 'the guard protects it from every folder');
  addApex(root, 'Foo');
  commitAll(root, 'foo');
  await refused(guardedDeploy({ cwd: root, values: ['ApexClass:Foo'], target: 'common', runtime: fakeRuntime(new FakeOrg()), dataDir }), /guards the common org but isn't its lane/);
  const lane = await init({ cwd: root, target: 'common', runtime: fakeRuntime(new FakeOrg()), dataDir });
  assert.equal(lane.role, 'lane');
  assert.equal(readRegistry(dataDir).orgs[ORG15].lane, root);
  await refused(init({ cwd: root, guardOnly: true, dataDir }), /already the common org's lane/);
});

test('guard-only warns about editor deploy-on-save, in the project and in VS Code or Cursor user settings', async () => {
  const { root, dataDir } = await makeKit({ register: false });
  const home = temp('sf-mp-home-');
  const user = process.platform === 'darwin' ? join(home, 'Library', 'Application Support', 'Cursor', 'User') : join(home, '.config', 'Cursor', 'User');
  mkdirSync(user, { recursive: true });
  writeFileSync(join(user, 'settings.json'), '{\n  // a comment, as editors allow\n  "salesforcedx-vscode-core.push-or-deploy-on-save.enabled": true\n}\n');
  const env = { XDG_CONFIG_HOME: join(home, '.config'), SFDX_AUTO_DEPLOY: 'true' };
  const result = await init({ cwd: root, guardOnly: true, dataDir, env, home });
  assert.equal(result.warnings.length, 2, result.warnings.join('\n'));
  assert.match(result.warnings[0], /SFDX_AUTO_DEPLOY/);
  assert.match(result.warnings[1], /Cursor.*deploys on save/);
  const quiet = await init({ cwd: root, guardOnly: true, dataDir, env: { SFDX_AUTO_DEPLOY: '0' }, home: temp('sf-mp-home-') });
  assert.deepEqual(quiet.warnings, []);
});

test('guard-only needs a kit project', async () => {
  const { root, dataDir } = await makeKit({ bind: null, register: false });
  await refused(init({ cwd: root, guardOnly: true, dataDir }), /needs a kit project/);
  await updateRegistry(dataDir, (registry) => registry);
  assert.deepEqual(readRegistry(dataDir).orgs, {});
});

test('read-back: an Apex body matches without the final newline Salesforce strips, and nothing else is forgiven', () => {
  const mine = [file('Foo.cls', 'public class Foo {}\n// a note\n'), file('Foo.cls-meta.xml', '<ApexClass/>\n')];
  const org = [file('Foo.cls', 'public class Foo {}\n// a note'), file('Foo.cls-meta.xml', '<ApexClass/>\n')];
  assert.equal(compareWithOrg(mine, org).matches, true);
  const changed = [file('Foo.cls', 'public class Foo {}\n// another note'), file('Foo.cls-meta.xml', '<ApexClass/>\n')];
  assert.deepEqual(compareWithOrg(mine, changed).differences, ['Foo.cls differs']);
  const js = [file('card.js', 'export default 1;\n')];
  assert.equal(compareWithOrg(js, [file('card.js', 'export default 1;')]).matches, false, 'only Apex bodies');
});
