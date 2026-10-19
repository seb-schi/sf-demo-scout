// The prerun hook's fail-closed boundary with injected faults, and the abort lint.
// Its own file: it points the host at a broken CLI root, which must not leak into other tests.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { after, test } from 'node:test';
import { cleanupTemps, makeKit, ORG15, temp, write } from './helpers.mjs';

const prerun = (await import('../hooks/prerun.mjs')).default;
const { setCliRoot } = await import('../src/host.mjs');
const { updateRegistry } = await import('../src/kit.mjs');

const CLI = process.env.SF_MP_CLI_ROOT;
after(() => {
  setCliRoot(CLI);
  cleanupTemps();
});

class Refused extends Error {}

/** Runs the hook like oclif does; returns the context.error call, or undefined when it let the command run. */
async function run(id, argv, { cwd, dataDir, root = CLI }) {
  const calls = [];
  const context = { error: (message, options) => { calls.push({ message, options }); throw new Refused(message); } };
  const previous = process.cwd();
  process.chdir(cwd);
  const write = process.stdout.write;
  process.stdout.write = () => true;
  try {
    await prerun({ Command: { id, flags: { 'target-org': { char: 'o', type: 'option' } } }, argv, config: { root, dataDir }, context });
  } catch (error) {
    if (!(error instanceof Refused)) throw error;
  } finally {
    process.stdout.write = write;
    process.chdir(previous);
  }
  return calls[0];
}

test('an invalid .mp/config.json refuses protected commands and leaves the rest alone', async () => {
  const { root, dataDir } = await makeKit();
  write(root, '.mp/config.json', '{ not json');
  const refusal = await run('project:deploy:start', ['-o', 'anything'], { cwd: root, dataDir });
  assert.equal(refusal.options.exit, 2);
  assert.match(refusal.message, /couldn't check this command \(\.mp\/config\.json is unreadable/);
  assert.equal(await run('org:list', [], { cwd: root, dataDir }), undefined);
  write(root, '.mp/config.json', JSON.stringify({ schema: 1, commonOrgId: 'nope', session: 's', authority: 'lane', testLevel: 'NoTestRun' }));
  assert.match((await run('apex:run', [], { cwd: root, dataDir })).message, /commonOrgId must be an org ID/);
});

test('a broken registry refuses protected commands from any folder', async () => {
  const anywhere = temp();
  const dataDir = temp();
  write(dataDir, 'sf-mp/bound-orgs.json', '[1, 2');
  assert.match((await run('project:deploy:start', ['-o', 'x'], { cwd: anywhere, dataDir })).message, /registry .* is unreadable/);
  assert.equal(await run('project:retrieve:start', ['-o', 'x'], { cwd: anywhere, dataDir }), undefined);
});

test('a host library that won\'t load refuses protected commands and leaves the rest alone', async () => {
  const { root, dataDir } = await makeKit();
  const broken = temp();
  const refusal = await run('project:deploy:start', ['-o', 'x'], { cwd: root, dataDir, root: broken });
  assert.equal(refusal.options.exit, 2);
  assert.match(refusal.message, /couldn't check this command/);
  assert.equal(await run('org:display', ['-o', 'x'], { cwd: root, dataDir, root: broken }), undefined);
  setCliRoot(CLI);
});

test('dormant: no kit project and no registry means the hook does nothing at all', async () => {
  const plain = temp();
  write(plain, 'sfdx-project.json', '{"packageDirectories":[{"path":"force-app"}]}');
  assert.equal(await run('project:deploy:start', ['-o', 'x'], { cwd: plain, dataDir: temp() }), undefined);
});

test('a refusal goes through context.error with exit 2, and prints parseable JSON for --json', async () => {
  const anywhere = temp();
  const dataDir = temp();
  await updateRegistry(dataDir, () => ({ orgs: { [ORG15]: { lane: '/x', boundAt: 'x' } } }));
  const out = [];
  const writeOut = process.stdout.write;
  const calls = [];
  const previous = process.cwd();
  process.chdir(anywhere);
  process.stdout.write = (chunk) => out.push(String(chunk)) && true;
  try {
    await prerun({
      Command: { id: 'project:deploy:quick', flags: {} },
      argv: ['--json'],
      config: { root: CLI, dataDir },
      context: { error: (message, options) => { calls.push(options); throw new Refused(message); } },
    }).catch((error) => { if (!(error instanceof Refused)) throw error; });
  } finally {
    process.stdout.write = writeOut;
    process.chdir(previous);
  }
  assert.deepEqual(calls.map((c) => c.exit), [2]);
  const json = JSON.parse(out.join(''));
  assert.equal(json.name, 'MpGuardBlocked');
  assert.equal(json.exitCode, 2);
});

test('lint: the hook aborts only through context.error(…, { exit: 2 }), inside its boundary', () => {
  const source = readFileSync(join(import.meta.dirname, '..', 'hooks', 'prerun.mjs'), 'utf8');
  const code = source.replace(/\/\/.*$/gm, '');
  assert.doesNotMatch(code, /\bthrow\b/, 'a plain throw from prerun is swallowed by oclif');
  assert.doesNotMatch(code, /process\.exit/, 'process.exit skips oclif');
  const calls = code.match(/context\.error\([^;]*\)/gs) ?? [];
  assert.equal(calls.length, 1);
  assert.match(calls[0], /exit:\s*2/);
  const tryBlock = code.slice(code.indexOf('try {'), code.indexOf('} catch'));
  assert.match(tryBlock, /await decide\(/, 'every check runs inside the try');
  assert.match(tryBlock, /watchDeploys\(/);
});
