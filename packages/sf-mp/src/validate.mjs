// `sf mp validate`: a check-only deploy into a common org that runs the tests you name.
//
// For teams on Salesforce's Lifecycle Center, where promotions deploy server-side: the captain
// checks a delivery's tests against the common org before merging it. It runs only where that org
// is bound as a Lifecycle Center captain's (sf mp init --guard-only --lifecycle-captain), never on a
// builder's guard or a lane. A validation can't change
// the org. checkOnly is fixed below and no flag reaches it, the guard still refuses quick deploy
// (which could turn a validation into a deploy), and a validation that ran none of the tests it
// was asked for doesn't count as validated. `ranNone` says when the platform proved that case:
// the deploy succeeded check-only with tests enabled, ran none of them, and nothing failed
// (measured on 19 Oct in some orgs, at every test level, through the sf CLI too).
import { existsSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
import { CEILING, setKeys } from './guard.mjs';
import { boundOrgs, findKit, readRegistry } from './kit.mjs';
import { Refusal } from './lane.mjs';

const APEX = /^(ApexClass|ApexTrigger):/;
const CLASS_NAME = /^[A-Za-z][A-Za-z0-9_]*$/;
const FIXED = { checkOnly: true, rollbackOnError: true, ignoreWarnings: false, rest: false, purgeOnDelete: false };

/** Runs the validation. Throws Refusal when nothing was sent. */
export async function guardedValidate({ cwd, target, sourceDir, tests = [], noTests = false, runtime, dataDir }) {
  if (!target) throw new Refusal('pass --target-org explicitly; sf mp never falls back to a default org');
  if (!sourceDir) throw new Refusal('pass --source-dir: the folder of source files to validate');
  const dir = resolve(cwd, sourceDir);
  if (!existsSync(dir) || !statSync(dir).isDirectory()) throw new Refusal(`${sourceDir} isn't a folder`);
  if (noTests === tests.length > 0) throw new Refusal('pass --tests <ApexClass> (repeat for more), or --no-tests for source without Apex');
  const names = tests.filter((name) => !CLASS_NAME.test(name));
  if (names.length) throw new Refusal(`not an Apex class name: ${names.join(', ')}`);

  const conn = await runtime.connect(target);
  const registry = readRegistry(dataDir);
  if (!boundOrgs(findKit(cwd), registry).has(conn.orgId)) {
    throw new Refusal(`${target} isn't a common org on this machine; sf project deploy validate works there without sf-mp`);
  }
  if (registry.orgs[conn.orgId]?.lifecycleCaptain !== true) {
    throw new Refusal(`only a Lifecycle Center team's captain validates against ${target}, and this machine isn't bound as one (sf mp init --guard-only --target-org ${target} --lifecycle-captain; Scout's start does it for the captain)`);
  }
  const { componentSet } = await runtime.sourceSet(dir);
  const keys = setKeys(componentSet);
  if (!keys.length) throw new Refusal(`no components under ${sourceDir}`);
  if (keys.length > CEILING) throw new Refusal(`${keys.length} components is over the ceiling of ${CEILING}`);
  if (noTests && keys.some((key) => APEX.test(key))) throw new Refusal('the source holds Apex, so it needs tests: pass --tests');

  const apiOptions = noTests ? { ...FIXED, testLevel: 'NoTestRun' } : { ...FIXED, testLevel: 'RunSpecifiedTests', runTests: [...tests] };
  const operation = await runtime.deploy(conn, componentSet, apiOptions, { orgId: conn.orgId, keys, onSubmitting: async () => {} });
  const outcome = await runtime.poll(operation);
  const ranTests = noTests || outcome.testsRun > 0;
  const ranNone = !noTests && outcome.done && outcome.success && outcome.checkOnly && outcome.runTestsEnabled
    && outcome.testsRun === 0 && !(outcome.failures ?? []).length;
  return {
    validated: Boolean(outcome.done && outcome.success && outcome.checkOnly && ranTests),
    checkOnly: true,
    components: keys,
    tests: noTests ? [] : [...tests],
    testsRun: outcome.testsRun ?? 0,
    ranNone: Boolean(ranNone),
    jobId: operation?.id ?? null,
    status: outcome.status ?? null,
    failures: ranTests ? outcome.failures ?? [] : [...(outcome.failures ?? []), 'the platform ran none of the named tests'],
  };
}
