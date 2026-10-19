// The guard's first line. oclif calls prerun for every command of every installed plugin, after
// resolving aliases and topic permutations and before the command parses its flags or runs.
//
// The one rule here: refuse only through context.error(…, { exit: 2 }). oclif swallows a plain
// throw from a hook and runs the command anyway (tested: a thrown error never stops the command). Everything that can fail
// runs inside the try below, so a guard failure becomes a refusal for protected commands and
// leaves every other command alone.
import { decide, PROTECTED, refusalSuggestion, watchDeploys } from '../src/guard.mjs';
import { core, setCliRoot } from '../src/host.mjs';

export default async function prerun(options) {
  const { Command, argv = [], config, context } = options;
  let reasons = [];
  try {
    setCliRoot(config?.root);
    const verdict = await decide({ Command, argv, cwd: process.cwd(), dataDir: config?.dataDir, loadCore: core });
    if (verdict.awake) watchDeploys(core(), verdict.bound);
    reasons = verdict.reasons;
  } catch (error) {
    if (PROTECTED.has(Command?.id)) {
      reasons = [`the multiplayer guard couldn't check this command (${error?.message ?? error}), so it refuses it`];
    }
  }
  if (!reasons.length) return;

  const message = `sf-mp blocked ${Command?.id}:\n  - ${reasons.join('\n  - ')}`;
  // oclif prints a hook failure through its top-level handler, which has no JSON mode, so give
  // --json callers (most AI agents) a parseable error on stdout as well.
  if (argv.includes('--json')) {
    try {
      const json = { status: 2, name: 'MpGuardBlocked', message, exitCode: 2, commandName: Command?.id, data: { reasons } };
      process.stdout.write(`${JSON.stringify(json, null, 2)}\n`);
    } catch {
      // The refusal below never depends on this output.
    }
  }
  context.error(message, { exit: 2, code: 'MpGuardBlocked', suggestions: [refusalSuggestion] });
}
