import { Flags, runGuarded, SfCommand, targetOrgFlag } from '../../src/command.mjs';
import { init } from '../../src/init.mjs';
import { realRuntime } from '../../src/runtime.mjs';

export default class MpInit extends SfCommand {
  static summary = 'Bind this Salesforce project to its common org, and make this checkout the org\'s lane on this machine.';
  static description =
    'Writes .mp/config.json (the binding, the session and the test level), an .mp/owners.yaml template and .mp/.gitignore, and registers the org on this machine so the guard protects it from every folder. Run it again on another machine to register the lane there.';
  static examples = ['<%= config.bin %> <%= command.id %> --target-org common'];
  static flags = {
    'target-org': targetOrgFlag({ required: false }),
    'replace-lane': Flags.boolean({ summary: 'Move the org\'s lane on this machine to this checkout.' }),
    'guard-only': Flags.boolean({ summary: 'Guard the common org on this machine without making it a lane (a builder\'s machine). In a kit project it needs no login to the common org; elsewhere, name the org with --target-org.' }),
    'lifecycle-captain': Flags.boolean({ summary: 'With --guard-only and --target-org: this machine is the captain of a team on Lifecycle Center, so sf mp validate may check deliveries against that org here.' }),
  };

  async run() {
    const { flags } = await this.parse(MpInit);
    return runGuarded(this, async () => {
      const result = await init({ cwd: process.cwd(), target: flags['target-org'], replaceLane: flags['replace-lane'], guardOnly: flags['guard-only'], lifecycleCaptain: flags['lifecycle-captain'], runtime: realRuntime(), dataDir: this.config.dataDir });
      if (result.role === 'guard') {
        this.log(`This machine now guards the common org ${result.commonOrgId}; it isn't a lane, so sf refuses writes to that org here.`);
        if (result.lifecycleCaptain) this.log('It\'s the Lifecycle Center captain\'s machine for that org, so sf mp validate checks deliveries against it here.');
        this.log('Editors deploy outside sf: keep deploy-on-save off, and keep your own org (never the common org) as this project\'s default org.');
        for (const warning of result.warnings) this.warn(warning);
        return result;
      }
      this.log(`Bound to ${result.commonOrgId} (${result.org.edition}${result.org.trial ? ', trial' : ''}${result.org.sandbox ? ', sandbox' : ''}); test level ${result.testLevel}.`);
      this.log(`This checkout is the lane on this machine: ${result.lane}`);
      if (result.created.length) this.log(`Created ${result.created.join(', ')}; commit them.`);
      for (const warning of result.warnings) this.warn(warning);
      return result;
    });
  }
}
