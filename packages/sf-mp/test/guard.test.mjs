// The guard's decisions, the listener, and the flag reader against the real command classes.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { join } from 'node:path';
import { after, test } from 'node:test';
import { pathToFileURL } from 'node:url';
import { cleanupTemps, makeKit, ORG, ORG15, OTHER, temp, write } from './helpers.mjs';

const { decide, PROTECTED, preDeployReasons, watchDeploys, withMarker, setKeys } = await import('../src/guard.mjs');
const { readFlags } = await import('../src/flags.mjs');
const { core } = await import('../src/host.mjs');
const { updateRegistry } = await import('../src/kit.mjs');

after(cleanupTemps);

const CLI = process.env.SF_MP_CLI_ROOT; // set by helpers.mjs
const NM = join(CLI, 'node_modules');
const load = async (pkg, file) => {
  const module = await import(pathToFileURL(join(NM, pkg, 'lib/commands', file)).href);
  return module.default ?? Object.values(module).find((value) => typeof value === 'function');
};
const COMMANDS = {
  'project:deploy:start': await load('@salesforce/plugin-deploy-retrieve', 'project/deploy/start.js'),
  'project:deploy:validate': await load('@salesforce/plugin-deploy-retrieve', 'project/deploy/validate.js'),
  'project:deploy:quick': await load('@salesforce/plugin-deploy-retrieve', 'project/deploy/quick.js'),
  'project:delete:source': await load('@salesforce/plugin-deploy-retrieve', 'project/delete/source.js'),
  'project:reset:tracking': await load('@salesforce/plugin-deploy-retrieve', 'project/reset/tracking.js'),
  'apex:run': await load('@salesforce/plugin-apex', 'apex/run.js'),
  'agent:activate': await load('@salesforce/plugin-agent', 'agent/activate.js'),
  'agent:create': await load('@salesforce/plugin-agent', 'agent/create.js'),
  'agent:publish:authoring-bundle': await load('@salesforce/plugin-agent', 'agent/publish/authoring-bundle.js'),
};
for (const [id, Command] of Object.entries(COMMANDS)) Command.id ??= id;
const command = (id) => Object.assign(Object.create(COMMANDS[id]), { id, flags: COMMANDS[id].flags, baseFlags: COMMANDS[id].baseFlags });

/** A fake @salesforce/core for offline resolution: aliases, logins and a configured default. */
function fakeCore({ aliases = {}, logins = {}, defaultOrg } = {}) {
  return {
    ConfigAggregator: { create: async () => ({ getPropertyValue: (key) => (key === 'target-org' ? defaultOrg : undefined) }) },
    StateAggregator: {
      getInstance: async () => ({
        aliases: { resolveUsername: (value) => aliases[value] ?? value },
        orgs: { read: async (username) => logins[username] },
      }),
    },
  };
}
const logins = { 'admin@common.example': { orgId: ORG }, 'me@sandbox.example': { orgId: '00D000000000777AAA' } };
const aliases = { common: 'admin@common.example', mine: 'me@sandbox.example' };

async function verdict(id, argv, { cwd, dataDir, ...coreOptions }) {
  return decide({ Command: command(id), argv, cwd, dataDir, loadCore: () => fakeCore({ aliases, logins, ...coreOptions }) });
}

test('dormant without a kit project or bound orgs; awake with either', async () => {
  const plain = temp();
  write(plain, 'sfdx-project.json', '{"packageDirectories":[{"path":"force-app"}]}');
  const empty = temp();
  assert.equal((await verdict('project:deploy:start', ['-o', 'common'], { cwd: plain, dataDir: empty })).awake, false);
  await updateRegistry(empty, () => ({ orgs: { [ORG15]: { lane: '/elsewhere', boundAt: 'x' } } }));
  const fromAnywhere = await verdict('project:deploy:start', ['-o', 'common'], { cwd: plain, dataDir: empty });
  assert.equal(fromAnywhere.awake, true);
  assert.match(fromAnywhere.reasons.join(), /would write to the common org \(common \(admin@common\.example\)\)/);
});

test('every protected command is refused against the bound org and passes against another org', async () => {
  const { root, dataDir } = await makeKit();
  for (const id of Object.keys(COMMANDS)) {
    if (id === 'project:deploy:quick') continue;
    const bound = await verdict(id, ['--target-org', 'common'], { cwd: root, dataDir });
    assert.equal(bound.reasons.length, 1, `${id} against the common org`);
    const other = await verdict(id, ['--target-org', 'mine'], { cwd: root, dataDir });
    assert.deepEqual(other.reasons, [], `${id} against a personal sandbox`);
  }
});

test('the configured default counts: bound default refused, other default passes, none refused in a kit', async () => {
  const { root, dataDir } = await makeKit();
  assert.equal((await verdict('project:deploy:start', ['--metadata', 'ApexClass:X'], { cwd: root, dataDir, defaultOrg: 'common' })).reasons.length, 1);
  assert.deepEqual((await verdict('project:deploy:start', ['--metadata', 'ApexClass:X'], { cwd: root, dataDir, defaultOrg: 'mine' })).reasons, []);
  assert.match((await verdict('project:deploy:start', [], { cwd: root, dataDir })).reasons.join(), /can't tell which org/);
});

test('unresolvable targets: refused in a kit project, passed outside one', async () => {
  const { root, dataDir } = await makeKit();
  assert.match((await verdict('project:deploy:start', ['-o', 'nobody'], { cwd: root, dataDir })).reasons.join(), /no local login for nobody/);
  const outside = temp();
  assert.deepEqual((await verdict('project:deploy:start', ['-o', 'nobody'], { cwd: outside, dataDir })).reasons, []);
});

test('an access token as the target is read by its org ID, and never echoed', async () => {
  const { root, dataDir } = await makeKit();
  const result = await verdict('project:deploy:start', ['-o', `${ORG15}!AQ0abc.def`], { cwd: root, dataDir });
  assert.equal(result.reasons.length, 1);
  assert.doesNotMatch(result.reasons.join(), /AQ0abc/);
});

test('two target values: any bound one refuses', async () => {
  const { root, dataDir } = await makeKit();
  assert.equal((await verdict('project:deploy:start', ['-o', 'mine', '-o', 'common'], { cwd: root, dataDir })).reasons.length, 1);
});

test('quick deploy and --flags-dir are refused whenever the guard is awake; agent create --preview passes', async () => {
  const { root, dataDir } = await makeKit();
  assert.match((await verdict('project:deploy:quick', ['--job-id', '0Af1', '-o', 'mine'], { cwd: root, dataDir })).reasons.join(), /validation's cache/);
  assert.match((await verdict('project:deploy:start', ['--flags-dir', 'f', '-o', 'mine'], { cwd: root, dataDir })).reasons.join(), /--flags-dir/);
  assert.deepEqual((await verdict('agent:create', ['--preview', '-o', 'common'], { cwd: root, dataDir })).reasons, []);
  assert.equal((await verdict('agent:create', ['--spec', 's.yaml', '-o', 'common'], { cwd: root, dataDir })).reasons.length, 1);
});

test('unprotected commands are never refused, even against the common org', async () => {
  const { root, dataDir } = await makeKit();
  const retrieve = { id: 'project:retrieve:start', flags: {} };
  const result = await decide({ Command: retrieve, argv: ['-o', 'common'], cwd: root, dataDir, loadCore: () => fakeCore({ aliases, logins }) });
  assert.equal(result.awake, true);
  assert.deepEqual(result.reasons, []);
});

test('readFlags reads target-org exactly as oclif\'s parser does, for every spelling each command defines', async () => {
  const { Parser } = createRequire(join(CLI, 'package.json'))('@oclif/core');
  for (const [id, Command] of Object.entries(COMMANDS)) {
    const defs = { ...Command.baseFlags, ...Command.flags };
    const def = defs['target-org'];
    assert.ok(def, `${id} has --target-org`);
    const spellings = [['--target-org', 'X'], ['--target-org=X']];
    for (const long of (def.aliases ?? []).filter((a) => a.length > 1)) spellings.push([`--${long}`, 'X']);
    for (const char of [def.char, ...(def.charAliases ?? []), ...(def.aliases ?? []).filter((a) => a.length === 1)].filter(Boolean)) {
      spellings.push([`-${char}`, 'X'], [`-${char}X`]);
    }
    // oclif's own parser, with every side effect stripped (no org lookups, no defaults).
    const quiet = Object.fromEntries(Object.entries(defs).map(([name, d]) => [name, { ...d, parse: async (v) => v, default: undefined, required: false, dependsOn: undefined, exclusive: undefined, exactlyOne: undefined, relationships: undefined, deprecateAliases: false }]));
    for (const argv of spellings) {
      const mine = readFlags(Command, argv).find((flag) => flag.name === 'target-org')?.value;
      const theirs = (await Parser.parse(argv, { flags: quiet, args: {}, strict: false })).flags['target-org'];
      assert.equal(mine, 'X', `${id} ${argv.join(' ')} (sf-mp)`);
      assert.equal(theirs, 'X', `${id} ${argv.join(' ')} (oclif)`);
    }
  }
});

test('the legacy -u spelling is recognised where a command defines it', () => {
  const withU = Object.entries(COMMANDS).filter(([, C]) => ({ ...C.baseFlags, ...C.flags })['target-org']?.aliases?.includes('u'));
  for (const [id, Command] of withU) assert.equal(readFlags(Command, ['-u', 'common']).find((f) => f.name === 'target-org')?.value, 'common', id);
});

// ---- the listener ----

const fakeSet = (keys) => keys.map((key) => ({ type: { name: key.split(':')[0] }, fullName: key.slice(key.indexOf(':') + 1) }));

test('preDeployReasons: unmarked bound deploys stop, other orgs pass, the mark must match exactly', () => {
  const bound = new Set([ORG15]);
  assert.deepEqual(preDeployReasons({ orgId: OTHER, keys: ['ApexClass:A'], bound }), []);
  assert.match(preDeployReasons({ orgId: ORG, keys: ['ApexClass:A'], bound }).join(), /didn't come through `sf mp deploy`/);
  const mark = { orgId: ORG15, keys: ['ApexClass:A'] };
  assert.deepEqual(preDeployReasons({ orgId: ORG, keys: ['ApexClass:A'], bound, mark }), []);
  assert.match(preDeployReasons({ orgId: ORG, keys: ['ApexClass:A', 'ApexClass:B'], bound, mark }).join(), /differ from the ones/);
  const many = Array.from({ length: 26 }, (_, i) => `ApexClass:C${i}`);
  assert.match(preDeployReasons({ orgId: ORG, keys: many, bound, mark: { orgId: ORG15, keys: many } }).join(), /over the ceiling/);
  assert.match(preDeployReasons({ orgId: undefined, keys: [], bound, mark }).join(), /can't be identified/);
});

test('the listener on the real Lifecycle stops an unmarked deploy to the bound org before upload', async () => {
  const sf = core();
  watchDeploys(sf, new Set([ORG15]));
  const lifecycle = sf.Lifecycle.getInstance();
  await assert.rejects(lifecycle.emit('scopedPreDeploy', { componentSet: fakeSet(['ApexClass:A']), orgId: ORG }), /sf-mp stopped the deploy before upload/);
  await lifecycle.emit('scopedPreDeploy', { componentSet: fakeSet(['ApexClass:A']), orgId: OTHER });
  await withMarker({ orgId: ORG15, keys: setKeys(fakeSet(['ApexClass:A'])) }, () => lifecycle.emit('scopedPreDeploy', { componentSet: fakeSet(['ApexClass:A']), orgId: ORG }));
  let submitted = 0;
  await withMarker({ orgId: ORG15, keys: [], onSubmitting: async () => submitted++ }, () => lifecycle.emit('deployZipData', { zipSize: 1 }));
  assert.equal(submitted, 1);
  await assert.rejects(withMarker({ orgId: ORG15, keys: [], onSubmitting: async () => { throw new Error('disk full'); } }, () => lifecycle.emit('deployZipData', {})), /disk full/);
});

test('the protected list covers the commands the plan names', () => {
  for (const id of ['project:deploy:start', 'project:deploy:validate', 'project:deploy:quick', 'project:delete:source', 'project:reset:tracking', 'project:delete:tracking', 'apex:run', 'agent:activate', 'agent:deactivate', 'agent:publish:authoring-bundle', 'agent:create']) {
    assert.ok(PROTECTED.has(id), id);
  }
  for (const id of ['project:deploy:report', 'project:deploy:resume', 'project:deploy:cancel', 'project:retrieve:start']) assert.ok(!PROTECTED.has(id), id);
});

test('the default org is read from the project root, even from a nested folder', async () => {
  const { root, dataDir } = await makeKit();
  const nested = join(root, 'force-app', 'main', 'default');
  write(root, 'force-app/main/default/.keep', '');
  let projectPath;
  const core = { ...fakeCore({ aliases, logins }), ConfigAggregator: { create: async (options) => { projectPath = options.projectPath; return { getPropertyValue: () => 'common' }; } } };
  const result = await decide({ Command: command('project:deploy:start'), argv: ['--metadata', 'ApexClass:X'], cwd: nested, dataDir, loadCore: () => core });
  assert.equal(projectPath, root);
  assert.equal(result.reasons.length, 1, 'the bound default is refused');
});

test('opaque tokens with an 18-character prefix are read; JWTs and unreadable tokens are refused unechoed', async () => {
  const { root, dataDir } = await makeKit();
  const long = await verdict('project:deploy:start', ['-o', `${ORG}!AQabc.def`], { cwd: root, dataDir });
  assert.equal(long.reasons.length, 1);
  const outside = temp();
  const jwt = 'eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJzeW50aGV0aWMifQ.c2lnbmF0dXJl'; // synthetic, as public fixtures must be
  const refusedJwt = await verdict('project:deploy:start', ['-o', jwt], { cwd: outside, dataDir });
  assert.match(refusedJwt.reasons.join(), /JWT access token/);
  assert.doesNotMatch(refusedJwt.reasons.join(), /eyJ/);
  const odd = await verdict('project:deploy:start', ['-o', 'not!a-token'], { cwd: outside, dataDir });
  assert.match(odd.reasons.join(), /looks like a token/);
  assert.doesNotMatch(odd.reasons.join(), /not!a-token/);
});

