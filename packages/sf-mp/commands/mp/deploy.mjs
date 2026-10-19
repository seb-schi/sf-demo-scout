import { describeRecord, Flags, runGuarded, SfCommand, targetOrgFlag } from '../../src/command.mjs';
import { guardedDeploy } from '../../src/deploy.mjs';
import { realRuntime } from '../../src/runtime.mjs';

export default class MpDeploy extends SfCommand {
  static summary = 'Deploy named components to the common org through the guarded lane.';
  static description =
    'Takes the named components from HEAD (committed work only), checks the common org\'s copy against your baseline, keeps a backup, records the operation before anything is sent, deploys, then reads the result back. Refuses stale, unowned or over-wide deploys.';
  static examples = [
    '<%= config.bin %> <%= command.id %> --metadata ApexClass:InvoiceService --target-org common --dry-run',
    '<%= config.bin %> <%= command.id %> --metadata ApexClass:InvoiceService --metadata LightningComponentBundle:invoiceCard --target-org common',
  ];
  static flags = {
    'target-org': targetOrgFlag(),
    metadata: Flags.string({ char: 'm', summary: 'A component to deploy, as Type:Name. Repeat for more, at most 25.', multiple: true, required: true }),
    'dry-run': Flags.boolean({ summary: 'Validate only: a check-only deploy that changes nothing in the org.' }),
    steward: Flags.boolean({ summary: 'The steward route: also deploy the allow-listed types without a lane contract (CONTRACT.md §5).' }),
    'approved-by': Flags.string({ summary: 'An owner whose yes you have for a component they own (.mp/owners.yaml). Repeat for more owners.', multiple: true }),
  };

  async run() {
    const { flags } = await this.parse(MpDeploy);
    return runGuarded(this, async () => {
      const { record, exitCode } = await guardedDeploy({
        cwd: process.cwd(),
        values: flags.metadata,
        target: flags['target-org'],
        dryRun: flags['dry-run'],
        steward: flags.steward,
        approvedBy: flags['approved-by'] ?? [],
        runtime: realRuntime(),
        dataDir: this.config.dataDir,
        log: (message) => this.warn(message),
      });
      this.log(`Operation ${record.opId}: ${record.state}${record.checkOnly ? ' (check-only)' : ''}${record.jobId ? `, job ${record.jobId}` : ''}`);
      for (const reason of record.result?.reasons ?? []) this.log(`  - ${reason}`);
      for (const failure of record.result?.failures ?? []) this.log(`  - ${failure}`);
      if (record.note) this.log(`  ${record.note}`);
      process.exitCode = exitCode;
      return describeRecord(record);
    });
  }
}
