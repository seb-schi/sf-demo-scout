// `sf mp init`: binds a Salesforce project to its common org and makes this checkout the org's
// lane on this machine. Re-running it on a second machine registers the lane there.
import { randomUUID } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { publishJsonExclusive } from './fsx.mjs';
import { gitRoot } from './git.mjs';
import { findKit, findSfProject, updateRegistry } from './kit.mjs';
import { readSlot } from './journal.mjs';
import { Refusal } from './lane.mjs';
import { OWNERS_TEMPLATE } from './owners.mjs';

const GITIGNORE = '# sf-mp: the lane\'s own state stays out of Git, so a branch switch can never revert a\n# baseline or hide an open operation (CONTRACT.md §2)\njournal/\nbaselines/\nmerge/\nbackups/\n';

const DEPLOY_ON_SAVE = /"salesforcedx-vscode-core\.push-or-deploy-on-save\.enabled"\s*:\s*true/;

/**
 * Editor settings that deploy on save: the project's, then VS Code's and Cursor's user settings. Those deploys call
 * Salesforce's libraries directly and never pass the CLI's guard. Read as text, since the files allow comments.
 */
function deployOnSave(root, env, home) {
  const userDirs = process.platform === 'darwin' ? [join(home, 'Library', 'Application Support')]
    : process.platform === 'win32' ? [env.APPDATA].filter(Boolean) : [env.XDG_CONFIG_HOME || join(home, '.config')];
  const files = [join(root, '.vscode', 'settings.json'), ...userDirs.flatMap((dir) => ['Code', 'Cursor'].map((app) => join(dir, app, 'User', 'settings.json')))];
  return files.filter((path) => {
    try {
      return DEPLOY_ON_SAVE.test(readFileSync(path, 'utf8'));
    } catch {
      return false;
    }
  });
}

/** Ways a tool on this machine can deploy outside the guard; on a lane and on a builder's guard alike. */
function bypassWarnings(root, env, home) {
  const warnings = [];
  if (env.SFDX_AUTO_DEPLOY && !/^(0|false|no|off)$/i.test(env.SFDX_AUTO_DEPLOY.trim())) warnings.push('SFDX_AUTO_DEPLOY is on: tools may deploy on save, outside the guard');
  for (const path of deployOnSave(root, env, home)) warnings.push(`${path} deploys on save (salesforcedx-vscode-core.push-or-deploy-on-save.enabled); that runs outside the guard, so switch it off`);
  return warnings;
}

/**
 * A builder's machine: guard the common org from every folder here, without a lane. In a kit project the org ID comes
 * from the committed .mp/config.json, so no login to the common org is needed. A team on Lifecycle Center keeps sf-mp
 * out of its repository, so there the org is named with --target-org and read from its login. Its captain's machine
 * binds with --lifecycle-captain, which is what lets sf mp validate run there; a builder's binding never does.
 */
async function guardOnly({ root, kit, target, lifecycleCaptain, runtime, dataDir, env, home }) {
  if (!kit && !target) throw new Refusal('--guard-only needs a kit project (with .mp/config.json), or the common org itself with --target-org');
  if (lifecycleCaptain && kit) throw new Refusal('--lifecycle-captain is for a team on Lifecycle Center, whose repository has no kit project (.mp/config.json)');
  const orgId = kit ? kit.orgId : (await runtime.connect(target)).orgId;
  await updateRegistry(dataDir, (registry) => {
    const before = registry.orgs[orgId];
    if (typeof before?.lane === 'string') throw new Refusal(`this machine is already the common org's lane (${before.lane}), which guards it too`);
    registry.orgs[orgId] = { role: 'guard', checkout: root, boundAt: new Date().toISOString(), ...(lifecycleCaptain ? { lifecycleCaptain: true } : {}) };
    return registry;
  });
  return {
    root,
    commonOrgId: kit ? kit.config.commonOrgId : orgId,
    session: kit?.config.session ?? null,
    testLevel: kit?.config.testLevel ?? null,
    lifecycleCaptain: Boolean(lifecycleCaptain),
    role: 'guard',
    created: [],
    warnings: bypassWarnings(root, env, home),
  };
}

export async function init({ cwd, target, replaceLane = false, guardOnly: guardOnlyMode = false, lifecycleCaptain = false, runtime, dataDir, env = process.env, home = homedir() }) {
  const root = findSfProject(cwd);
  if (!root) throw new Refusal('run sf mp init inside a Salesforce project (a folder with sfdx-project.json)');
  let kit;
  try {
    kit = findKit(root);
  } catch (error) {
    throw new Refusal(error.message);
  }
  if (guardOnlyMode) return guardOnly({ root, kit, target, lifecycleCaptain, runtime, dataDir, env, home });
  if (lifecycleCaptain) throw new Refusal('--lifecycle-captain goes with --guard-only: a Lifecycle Center team has no lane');
  if (!target) throw new Refusal('pass the common org explicitly with --target-org; sf mp never falls back to a default org');
  const conn = await runtime.connect(target);
  if (kit && kit.orgId !== conn.orgId) throw new Refusal(`this kit project is bound to ${kit.config.commonOrgId}, but ${target} is ${conn.orgId}`);
  const info = await runtime.describe(conn);

  const created = [];
  if (!kit) {
    const config = {
      schema: 1,
      commonOrgId: conn.orgId,
      session: randomUUID(),
      authority: 'lane',
      testLevel: info.trial || info.sandbox ? 'NoTestRun' : 'RunLocalTests',
      createdAt: new Date().toISOString(),
    };
    if (!publishJsonExclusive(join(root, '.mp', 'config.json'), config)) throw new Refusal('another sf mp init wrote .mp/config.json just now; run it again');
    created.push('.mp/config.json');
    kit = findKit(root);
  }
  if (!existsSync(join(root, '.mp', 'owners.yaml'))) {
    writeFileSync(join(root, '.mp', 'owners.yaml'), OWNERS_TEMPLATE);
    created.push('.mp/owners.yaml');
  }
  if (!existsSync(join(root, '.mp', '.gitignore'))) {
    writeFileSync(join(root, '.mp', '.gitignore'), GITIGNORE);
    created.push('.mp/.gitignore');
  }

  // The binding decision and the old lane's slot check run under the registry lock, the same
  // critical section a deploy takes its slot in.
  await updateRegistry(dataDir, (registry) => {
    const before = registry.orgs[kit.orgId];
    // A guard-only entry holds no operation, so the lane replaces it directly.
    if (before && before.role !== 'guard' && before.lane !== root) {
      if (!replaceLane) throw new Refusal(`the common org already has a lane on this machine: ${before.lane}. Use that checkout, or move the lane here with --replace-lane`);
      const open = existsSync(before.lane) ? readSlot(before.lane, kit.orgId) : undefined;
      if (open) throw new Refusal(`the old lane ${before.lane} has an open operation; settle it there with sf mp reconcile first`);
    }
    registry.orgs[kit.orgId] = { lane: root, boundAt: new Date().toISOString() };
    return registry;
  });

  const warnings = [];
  if (!gitRoot(root)) warnings.push('this project isn\'t a Git repository yet; sf mp deploy needs committed work');
  warnings.push(...bypassWarnings(root, env, home));
  if (info.tracksSource) warnings.push('the common org tracks source; the guarded path works, but raw deploys there lose the listener backstop (untested there)');
  return {
    root,
    commonOrgId: kit.config.commonOrgId,
    session: kit.config.session,
    testLevel: kit.config.testLevel,
    org: { edition: info.edition, sandbox: info.sandbox, trial: info.trial, tracksSource: info.tracksSource },
    role: 'lane',
    lane: root,
    created,
    warnings,
  };
}
