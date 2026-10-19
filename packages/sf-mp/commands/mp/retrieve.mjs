import { Flags, runGuarded, SfCommand, targetOrgFlag } from '../../src/command.mjs';
import { guardedRetrieve } from '../../src/retrieve.mjs';
import { realRuntime } from '../../src/runtime.mjs';

export default class MpRetrieve extends SfCommand {
  static summary = 'Retrieve named components from the common org and record their baselines.';
  static description =
    'Retrieves into a fresh folder first. A component goes into your project only when your copy is missing or identical; a different copy is left untouched and the org\'s copy is saved under .mp/merge for you to merge. After merging and committing, run it again with --merged.';
  static examples = ['<%= config.bin %> <%= command.id %> --metadata ApexClass:InvoiceService --target-org common'];
  static flags = {
    'target-org': targetOrgFlag(),
    metadata: Flags.string({ char: 'm', summary: 'A component to retrieve, as Type:Name. Repeat for more, at most 25.', multiple: true, required: true }),
    merged: Flags.boolean({ summary: 'You merged the saved org copy into your copy and committed it: record that org version as your baseline.' }),
    steward: Flags.boolean({ summary: 'Also retrieve the steward route\'s allow-listed types (CONTRACT.md §5).' }),
  };

  async run() {
    const { flags } = await this.parse(MpRetrieve);
    return runGuarded(this, async () => {
      const result = await guardedRetrieve({ cwd: process.cwd(), values: flags.metadata, target: flags['target-org'], merged: flags.merged, steward: flags.steward, runtime: realRuntime(), dataDir: this.config.dataDir });
      for (const item of result.components) this.log(`${item.component}: ${item.outcome}. ${item.detail ?? ''}`.trim());
      if (result.components.some((item) => ['conflict', 'unknown', 'refused', 'deleted-in-org'].includes(item.outcome))) process.exitCode = 1;
      return result;
    });
  }
}
