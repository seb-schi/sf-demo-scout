import { runGuarded, SfCommand } from '../../src/command.mjs';
import { status } from '../../src/status.mjs';

export default class MpStatus extends SfCommand {
  static summary = 'Show the multiplayer session: open operations, recent ones, baselines and uncommitted state.';
  static examples = ['<%= config.bin %> <%= command.id %>'];

  async run() {
    await this.parse(MpStatus);
    return runGuarded(this, async () => {
      const result = status({ cwd: process.cwd(), dataDir: this.config.dataDir });
      this.log(`Common org ${result.commonOrgId}, session ${result.session}, ${result.authority}, test level ${result.testLevel}`);
      this.log(result.thisCheckoutIsTheLane ? 'This checkout is the lane on this machine.' : `The lane on this machine is ${result.lane ?? 'not set (run sf mp init)'}.`);
      if (!result.open.length) this.log('No open operation.');
      for (const op of result.open) {
        this.log(op.unreadable ? `OPEN, unreadable slot for ${op.orgId}: ${op.unreadable}` : `OPEN ${op.opId}: ${op.state}, ${op.components.join(', ')}${op.jobId ? `, job ${op.jobId}` : ''} (process ${op.holder})`);
        if (op.note) this.log(`  ${op.note}`);
      }
      for (const op of result.recent) this.log(`  ${op.opId}: ${op.state ?? `unreadable (${op.unreadable})`}${op.checkOnly ? ' (check-only)' : ''}`);
      this.log(result.baselines.problem ? `Baselines: ${result.baselines.problem}` : `Baselines: ${result.baselines.total} (${Object.entries(result.baselines.counts).map(([k, v]) => `${v} ${k}`).join(', ') || 'none'})`);
      if (result.lastDeploy) this.log(`Last deploy: ${result.lastDeploy.revision.slice(0, 12)} (${result.lastDeploy.opId})`);
      if (result.uncommitted.length) this.log(`Not committed yet:\n  ${result.uncommitted.join('\n  ')}`);
      return result;
    });
  }
}
