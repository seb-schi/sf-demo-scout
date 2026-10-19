// The guard. It protects the bound common org, and only that org: writes to any other org, such
// as a builder's own sandbox, pass untouched, so sf-skills, Scout and other tools keep working
// there even from inside a kit project.
//
// Two lines of defence inside the `sf` process:
//   1. prerun refuses protected commands whose target is a bound org, before they run.
//   2. A scopedPreDeploy listener sees the exact component set and org of every source-format
//      deploy in the process, and stops any deploy to a bound org that `sf mp deploy` didn't
//      mark, before the zip is built or uploaded.
//
// Cooperative threat model: this catches accidents and AI agents following generic advice.
// It doesn't resist someone who sets out to bypass it.
import { readFlags } from './flags.mjs';
import { org15 } from './ids.mjs';
import { boundOrgs, findKit, readRegistry } from './kit.mjs';
import { resolveTarget } from './target.mjs';

export const CEILING = 25;

// Canonical command IDs: oclif resolves aliases and topic permutations to these before prerun.
export const PROTECTED = new Map([
  ['project:deploy:start', 'write'],
  ['project:deploy:validate', 'write'],
  ['project:delete:source', 'write'],
  ['project:reset:tracking', 'write'],
  ['project:delete:tracking', 'write'],
  ['apex:run', 'write'],
  ['agent:activate', 'write'],
  ['agent:deactivate', 'write'],
  ['agent:publish:authoring-bundle', 'write'],
  ['agent:create', 'agent-create'],
  // Quick deploy takes its org from the validation's cache entry, ahead of any flag, and emits
  // no scopedPreDeploy event, so neither line can check it.
  ['project:deploy:quick', 'always'],
]);

const ROUTE = 'Deploy named components through `sf mp deploy --metadata Type:Name --target-org <org>`; anything else on the common org goes to the steward.';

/**
 * The guard's verdict for one command: { awake, bound, reasons }. Dormant (awake: false) unless
 * cwd is in a kit project or this machine has bound orgs. Throws when the kit config or the
 * registry is unreadable; the caller fails closed for protected commands.
 */
export async function decide({ Command, argv = [], cwd, dataDir, loadCore }) {
  const kit = findKit(cwd);
  const registry = readRegistry(dataDir);
  const bound = boundOrgs(kit, registry);
  if (!bound.size) return { awake: false, reasons: [] };

  const id = Command?.id;
  const kind = PROTECTED.get(id);
  if (!kind) return { awake: true, bound, reasons: [] };
  if (kind === 'always') {
    return { awake: true, bound, reasons: [`${id} can't be checked by the multiplayer guard, because it takes its org from the validation's cache; deploy again instead`] };
  }

  const flags = readFlags(Command, argv);
  const has = (name) => flags.some((flag) => flag.name === name);
  if (kind === 'agent-create' && has('preview')) return { awake: true, bound, reasons: [] };
  if (has('flags-dir')) {
    return { awake: true, bound, reasons: [`--flags-dir adds flags only after the multiplayer guard has checked ${id}; pass the flags directly`] };
  }

  const core = loadCore();
  const values = flags.filter((flag) => flag.name === 'target-org').map((flag) => flag.value);
  const targets = values.length
    ? await Promise.all(values.map((value) => resolveTarget({ value: value === true ? '' : value, cwd, core })))
    : [await resolveTarget({ value: undefined, cwd, core })];
  const reasons = [];
  for (const target of targets) {
    if (target.unresolved) {
      // Outside a kit project an unresolvable target can't be deployed to anyway; a token can.
      if (kit || target.token) reasons.push(`the multiplayer guard can't tell which org ${id} targets (${target.unresolved}), so it might be the common org`);
    } else if (bound.has(target.orgId)) {
      reasons.push(`${id} would write to the common org (${target.label}) outside the kit`);
    }
  }
  return { awake: true, bound, reasons };
}

export const refusalSuggestion = ROUTE;

// ---- The in-memory marker and the scopedPreDeploy listener ----

// Set only by `sf mp deploy`, in memory, so no shell command, env var or flag can fake it.
const MARKER = Symbol.for('sf-mp.guarded-deploy');
const PRE_DEPLOY_ID = 'sf-mp#scopedPreDeploy';
const ZIP_ID = 'sf-mp#deployZipData';

export const componentKey = (component) => `${typeof component.type === 'string' ? component.type : component.type?.name}:${component.fullName}`;
export const setKeys = (componentSet) => [...new Set(Array.from(componentSet, componentKey))].sort();

/** Runs fn with the marker set: { orgId, keys, onSubmitting }. */
export async function withMarker(mark, fn) {
  globalThis[MARKER] = mark;
  try {
    return await fn();
  } finally {
    delete globalThis[MARKER];
  }
}

export function preDeployReasons({ orgId, keys, bound, mark }) {
  const id = org15(orgId);
  if (id && !bound.has(id)) return [];
  const reasons = [];
  if (!id) reasons.push(`the deploy's org (${orgId}) can't be identified`);
  if (!mark) reasons.push('a deploy to the common org didn\'t come through `sf mp deploy`');
  else {
    if (org15(mark.orgId) !== id) reasons.push(`the deploy goes to ${orgId}, not the org \`sf mp deploy\` checked (${mark.orgId})`);
    if (mark.keys.length !== keys.length || mark.keys.some((key, i) => key !== keys[i])) {
      reasons.push('the deploy\'s components differ from the ones `sf mp deploy` inspected');
    }
  }
  if (keys.length > CEILING) reasons.push(`${keys.length} components is over the ceiling of ${CEILING}`);
  return reasons;
}

/** Registers the listeners once per process; repeated calls with the same IDs are no-ops. */
export function watchDeploys(core, bound) {
  const lifecycle = core.Lifecycle.getInstance();
  lifecycle.on(
    'scopedPreDeploy',
    async ({ componentSet, orgId }) => {
      const reasons = preDeployReasons({ orgId, keys: setKeys(componentSet), bound, mark: globalThis[MARKER] });
      if (reasons.length) {
        throw new core.SfError(`sf-mp stopped the deploy before upload:\n  - ${reasons.join('\n  - ')}`, 'MpGuardPreDeployAbort');
      }
    },
    PRE_DEPLOY_ID
  );
  // SDR emits deployZipData just before it sends the deploy. `sf mp deploy` records `submitting`
  // here; if that record can't be written, throwing stops the deploy before anything is sent.
  lifecycle.on(
    'deployZipData',
    async () => {
      const mark = globalThis[MARKER];
      if (mark?.onSubmitting) await mark.onSubmitting();
    },
    ZIP_ID
  );
}
