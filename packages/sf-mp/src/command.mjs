// What the five `sf mp` commands share: the host's SfCommand (so --json and errors behave like
// every sf command) and one way of turning a refusal into exit code 2.
import { core, hostImport, setCliRoot } from './host.mjs';
import { Refusal } from './lane.mjs';

const { SfCommand, Flags } = await hostImport('@salesforce/sf-plugins-core');
export { Flags, SfCommand };

export const targetOrgFlag = ({ required = true } = {}) =>
  Flags.string({
    char: 'o',
    summary: 'The common org, as an alias or username. Required: sf mp never falls back to a default org.',
    required,
  });

/** Runs a command body; a Refusal becomes an SfError with exit code 2 (nothing was changed). */
export async function runGuarded(command, body) {
  setCliRoot(command.config.root);
  try {
    return await body();
  } catch (error) {
    if (error instanceof Refusal) {
      const failure = new (core().SfError)(error.message, 'MpRefused', [], 2);
      failure.setData?.({ reasons: error.reasons, ...error.data });
      throw failure;
    }
    throw error;
  }
}

export const describeRecord = (record) => ({
  opId: record.opId,
  state: record.state,
  checkOnly: record.checkOnly,
  steward: Boolean(record.steward),
  // Verified: a real deploy whose read-back matched. A settlement by hand says so itself.
  verified: record.verified ?? (['settled-success', 'reconciled-success'].includes(record.state) && !record.checkOnly),
  components: record.components,
  jobId: record.jobId ?? null,
  result: record.result ?? null,
  readback: record.readback ?? null,
  note: record.note ?? null,
});
