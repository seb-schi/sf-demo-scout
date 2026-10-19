import { describeRecord, Flags, runGuarded, SfCommand, targetOrgFlag } from '../../src/command.mjs';
import { reconcile } from '../../src/reconcile.mjs';
import { realRuntime } from '../../src/runtime.mjs';

export default class MpReconcile extends SfCommand {
  static summary = 'Settle the common org\'s open operation. Never redeploys.';
  static description =
    'With a job ID it reads the job\'s final status; without one it looks for the job by its DeployRequest. An operation that never got past its intent settles as never submitted. Anything it can\'t tell, the steward settles with --settle and a note.';
  static examples = [
    '<%= config.bin %> <%= command.id %> --target-org common',
    '<%= config.bin %> <%= command.id %> --target-org common --settle failed --note "Deployment Status shows nothing ran"',
  ];
  static flags = {
    'target-org': targetOrgFlag(),
    settle: Flags.string({ summary: 'Settle by hand, after checking the org: success or failed.', options: ['success', 'failed'] }),
    note: Flags.string({ summary: 'What you checked, recorded with a settlement by hand.' }),
    'holder-stopped': Flags.boolean({ summary: 'You\'ve made sure the operation\'s own process has stopped (needed when sf mp can\'t tell).' }),
  };

  async run() {
    const { flags } = await this.parse(MpReconcile);
    return runGuarded(this, async () => {
      const result = await reconcile({ cwd: process.cwd(), target: flags['target-org'], settleAs: flags.settle, note: flags.note, holderStopped: flags['holder-stopped'], runtime: realRuntime(), dataDir: this.config.dataDir });
      this.log(`${result.outcome}${result.detail ? `: ${result.detail}` : ''}`);
      if (result.record?.note) this.log(`  ${result.record.note}`);
      if (['needs-steward', 'still-running', 'unresolved'].includes(result.outcome)) process.exitCode = 1;
      return { ...result, record: result.record ? describeRecord(result.record) : undefined };
    });
  }
}
