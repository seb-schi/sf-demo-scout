// Shared fixtures: temporary kit projects in real Git repos, and a fake org behind a runtime
// that uses the host's real source-deploy-retrieve for resolution. Only the transport is fake.
import { execFileSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';

// The sf on the PATH, unless SF_MP_CLI_ROOT names an install folder.
if (!process.env.SF_MP_CLI_ROOT) {
  const bin = realpathSync(execFileSync('sh', ['-c', 'command -v sf'], { encoding: 'utf8' }).trim());
  process.env.SF_MP_CLI_ROOT = dirname(dirname(bin));
}

const { realRuntime } = await import('../src/runtime.mjs');
const { componentFiles, hashFiles, readFiles } = await import('../src/hash.mjs');
const { updateRegistry } = await import('../src/kit.mjs');

export const ORG = '00D000000000042EAC'; // synthetic (all zeros, as public fixtures must be)
export const ORG15 = ORG.slice(0, 15);
export const OTHER = '00D000000000001AAA';

const temps = [];
export const temp = (prefix = 'sf-mp-test-') => {
  const dir = realpathSync(mkdtempSync(join(tmpdir(), prefix)));
  temps.push(dir);
  return dir;
};
export const cleanupTemps = () => temps.splice(0).forEach((dir) => rmSync(dir, { recursive: true, force: true }));

export const git = (cwd, ...args) => execFileSync('git', args, { cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();

export function write(root, path, text) {
  const target = join(root, ...path.split('/'));
  mkdirSync(dirname(target), { recursive: true });
  writeFileSync(target, text);
}

export const APEX_META = '<?xml version="1.0" encoding="UTF-8"?>\n<ApexClass xmlns="http://soap.sforce.com/2006/04/metadata">\n    <apiVersion>64.0</apiVersion>\n    <status>Active</status>\n</ApexClass>\n';
export const apexBody = (name, body = 'return 0;') => `public with sharing class ${name} {\n    public static Integer run() { ${body} }\n}\n`;
export const fieldXml = (name, type = 'Text', extra = '<length>80</length>') =>
  `<?xml version="1.0" encoding="UTF-8"?>\n<CustomField xmlns="http://soap.sforce.com/2006/04/metadata">\n    <fullName>${name}</fullName>\n    <label>${name}</label>\n    ${extra}\n    <type>${type}</type>\n</CustomField>\n`;
export const LWC_META = '<?xml version="1.0" encoding="UTF-8"?>\n<LightningComponentBundle xmlns="http://soap.sforce.com/2006/04/metadata">\n    <apiVersion>64.0</apiVersion>\n    <isExposed>false</isExposed>\n</LightningComponentBundle>\n';

/** A kit project in a fresh Git repo, bound to ORG, registered as the lane in its own data dir. */
export async function makeKit({ bind = ORG, register = true, commit = true } = {}) {
  const root = temp('sf-mp-kit-');
  const dataDir = temp('sf-mp-data-');
  git(root, 'init', '-q', '-b', 'main');
  git(root, 'config', 'user.name', 'Lane Captain');
  git(root, 'config', 'user.email', 'captain@example.com');
  git(root, 'config', 'commit.gpgsign', 'false');
  write(root, 'sfdx-project.json', JSON.stringify({ packageDirectories: [{ path: 'force-app', default: true }], sourceApiVersion: '64.0' }, null, 2));
  write(root, '.forceignore', '**/__tests__/**\n**/jsconfig.json\n');
  if (bind) {
    write(root, '.mp/config.json', JSON.stringify({ schema: 1, commonOrgId: bind, session: 'session-1', authority: 'lane', testLevel: 'NoTestRun', createdAt: '2026-10-18T00:00:00Z' }, null, 2));
    write(root, '.mp/.gitignore', 'journal/\nbaselines/\nmerge/\nbackups/\n');
  }
  if (register && bind) await updateRegistry(dataDir, (registry) => ({ orgs: { ...registry.orgs, [bind.slice(0, 15)]: { lane: root, boundAt: '2026-10-18T00:00:00Z' } } }));
  if (commit) commitAll(root, 'start');
  return { root, dataDir };
}

export function commitAll(root, message = 'change') {
  git(root, 'add', '-A');
  git(root, 'commit', '-q', '--allow-empty', '-m', message);
  return git(root, 'rev-parse', 'HEAD');
}

export const paths = {
  ApexClass: (name) => [`force-app/main/default/classes/${name}.cls`, `force-app/main/default/classes/${name}.cls-meta.xml`],
};

export function addApex(root, name, body) {
  write(root, `force-app/main/default/classes/${name}.cls`, apexBody(name, body));
  write(root, `force-app/main/default/classes/${name}.cls-meta.xml`, APEX_META);
}

export function addField(root, object, field, type, extra) {
  write(root, `force-app/main/default/objects/${object}/fields/${field}.field-meta.xml`, fieldXml(field, type, extra));
}

export function addLwc(root, name, extraFiles = {}) {
  const dir = `force-app/main/default/lwc/${name}`;
  write(root, `${dir}/${name}.js`, "import { LightningElement } from 'lwc';\nexport default class X extends LightningElement {}\n");
  write(root, `${dir}/${name}.html`, '<template><p>hi</p></template>\n');
  write(root, `${dir}/${name}.js-meta.xml`, LWC_META);
  for (const [file, text] of Object.entries(extraFiles)) write(root, `${dir}/${file}`, text);
}

const layoutDir = (type, name) =>
  type === 'ApexClass' ? 'classes' : type === 'LightningComponentBundle' ? `lwc/${name}` : type === 'CustomField' ? `objects/${name.split('.')[0]}/fields` : 'other';

/** A fake common org: Map key -> { files: [{ key, bytes }], lastModifiedBy, lastModifiedDate }. */
export class FakeOrg {
  constructor(orgId = ORG) {
    this.orgId = orgId.slice(0, 15);
    this.components = new Map();
    this.jobs = new Map();
    this.requests = [];
    this.deploys = [];
    this.nextJob = 1;
  }
  put(key, files, who = 'Someone Else', when = '2026-10-18T00:00:00.000Z') {
    this.components.set(key, { files: files.map((f) => ({ key: f.key, bytes: Buffer.from(f.bytes) })), lastModifiedBy: who, lastModifiedDate: when });
  }
  /** Seeds the org with exactly what the project holds for these components. */
  async seedFrom(root, keys) {
    const { found } = await realRuntime().resolveSource(root, [join(root, 'force-app')], keys.map((key) => ({ key, type: key.split(':')[0], name: key.slice(key.indexOf(':') + 1) })), '64.0');
    for (const key of keys) this.put(key, found.get(key).files);
  }
}

/**
 * A runtime with the real SDR resolution and a fake transport. Options inject failures:
 * failRetrieve, failBeforeSubmit, failAfterSubmit, noJobId, failPoll, notDone, deployFails,
 * reformatOnDeploy (the org rewrites a file), concurrentChange (someone edits mid-deploy).
 */
export function fakeRuntime(org, options = {}) {
  const real = realRuntime();
  const calls = [];
  return {
    calls,
    async connect(target) {
      calls.push(['connect', target]);
      await options.onConnect?.();
      if (options.connectUser) return { orgId: org.orgId, username: options.connectUser, conn: { getApiVersion: () => '64.0' } };
      if (options.connectOrgId) return { orgId: options.connectOrgId.slice(0, 15), username: 'captain@example.com', conn: { getApiVersion: () => '64.0' } };
      return { orgId: org.orgId, username: 'captain@example.com', conn: { getApiVersion: () => '64.0' } };
    },
    async describe() {
      return { edition: 'Enterprise Edition', sandbox: false, trial: true, tracksSource: false, apiVersion: '64.0' };
    },
    resolveSource: (...args) => real.resolveSource(...args),
    sourceSet: (...args) => real.sourceSet(...args),
    async retrieve(c, entries, outDir) {
      calls.push(['retrieve', entries.map((e) => e.key), outDir]);
      if (options.failRetrieve?.(calls)) throw new Error('retrieve failed (injected)');
      await options.onRetrieve?.(calls);
      if (options.writeOutput) {
        // Like SDR: output lands in the folder after an await.
        await new Promise((done) => setTimeout(done, 20));
        mkdirSync(outDir, { recursive: true });
        writeFileSync(join(outDir, 'package.xml'), '<Package/>');
      }
      const out = new Map();
      for (const entry of entries) {
        const held = org.components.get(entry.key);
        if (options.unknown?.includes(entry.key)) out.set(entry.key, { state: 'unknown', problem: 'injected' });
        else if (!held) out.set(entry.key, { state: 'confirmed-absent' });
        else {
          const files = held.files.map((f) => ({ key: f.key, bytes: Buffer.from(f.bytes) }));
          const xmlKey = files.find((f) => f.key.endsWith('-meta.xml'))?.key ?? files[0].key;
          out.set(entry.key, { state: 'present', files, hash: hashFiles(files), xml: join('/fake-out/main/default', ...layoutDir(entry.type, entry.name).split('/'), xmlKey), lastModifiedBy: held.lastModifiedBy, lastModifiedDate: held.lastModifiedDate });
        }
      }
      return out;
    },
    async deploy(c, componentSet, apiOptions, mark) {
      calls.push(['deploy', mark.keys, apiOptions]);
      if (options.failBeforeSubmit) throw new Error('zip failed (injected)');
      options.beforeSubmit?.();
      await mark.onSubmitting();
      options.duringDeploy?.();
      options.afterSubmit?.();
      if (options.failAfterSubmit) throw new Error('socket hang up (injected)');
      const id = `0Af${String(org.nextJob++).padStart(12, '0')}`;
      org.requests.push({ id, status: 'Succeeded', checkOnly: apiOptions.checkOnly, createdDate: new Date().toISOString(), user: 'captain@example.com' });
      const applied = [];
      for (const component of componentSet.getSourceComponents().toArray()) {
        const key = `${component.type.name}:${component.fullName}`;
        let files = readFiles(componentFiles(component));
        if (options.reformatOnDeploy) files = files.map((f) => (f.key.endsWith('.cls') ? { ...f, bytes: Buffer.from(`${f.bytes}// org reformatted\n`) } : f));
        applied.push([key, files]);
      }
      const success = !options.deployFails;
      if (success && !apiOptions.checkOnly) for (const [key, files] of applied) org.put(key, files, 'Lane Captain', new Date().toISOString());
      if (options.concurrentChange) org.put(options.concurrentChange.key, options.concurrentChange.files, 'Setup User');
      org.jobs.set(id, { done: !options.notDone, status: options.notDone ? 'InProgress' : success ? 'Succeeded' : 'Failed', success, checkOnly: apiOptions.checkOnly });
      org.deploys.push({ id, checkOnly: apiOptions.checkOnly, keys: applied.map(([key]) => key) });
      return { id: options.noJobId ? undefined : id };
    },
    async poll(operation) {
      if (options.failPoll) throw new Error('ECONNRESET (injected)');
      const job = org.jobs.get(operation.id);
      return { done: job.done, status: job.status, success: job.success, checkOnly: job.checkOnly, runTestsEnabled: options.runTestsEnabled ?? true,
        testsRun: options.testsRun ?? 0, failures: job.success ? [] : ['ApexClass:X: injected failure'] };
    },
    async deployStatus(c, jobId) {
      const job = org.jobs.get(jobId);
      if (!job) throw new Error(`no job ${jobId}`);
      return { done: job.done, status: job.status, success: job.success, checkOnly: job.checkOnly, failures: [] };
    },
    async deployRequestsSince(c, username, since) {
      calls.push(['deployRequestsSince', username, since]);
      return (options.requests ?? org.requests).filter((request) => (request.user ?? 'captain@example.com') === username);
    },
  };
}

export const entry = (key) => ({ key, type: key.split(':')[0], name: key.slice(key.indexOf(':') + 1) });
