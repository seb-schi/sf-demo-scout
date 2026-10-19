import { Flags, runGuarded, SfCommand, targetOrgFlag } from '../../src/command.mjs';
import { realRuntime } from '../../src/runtime.mjs';
import { guardedValidate } from '../../src/validate.mjs';

export default class MpValidate extends SfCommand {
  static summary = 'Validate source against the common org: a check-only deploy that runs the tests you name.';
  static description =
    'For teams whose promotions run on Lifecycle Center: checks a delivery against the common org before it is merged. The deploy is always check-only, so the org never changes. It runs the named Apex tests (or none, for source without Apex), and it counts as validated only if the platform reports that the tests ran.';
  static examples = [
    '<%= config.bin %> <%= command.id %> --source-dir .scout/candidate --tests InvoiceServiceTest --target-org common',
    '<%= config.bin %> <%= command.id %> --source-dir .scout/candidate --no-tests --target-org common',
  ];
  static flags = {
    'target-org': targetOrgFlag(),
    'source-dir': Flags.string({ char: 'd', summary: 'The folder of source files to validate.', required: true }),
    tests: Flags.string({ char: 't', summary: 'An Apex test class to run. Repeat for more.', multiple: true }),
    'no-tests': Flags.boolean({ summary: 'Run no tests: only for source without Apex.' }),
  };

  async run() {
    const { flags } = await this.parse(MpValidate);
    return runGuarded(this, async () => {
      const result = await guardedValidate({
        cwd: process.cwd(),
        target: flags['target-org'],
        sourceDir: flags['source-dir'],
        tests: flags.tests ?? [],
        noTests: flags['no-tests'],
        runtime: realRuntime(),
        dataDir: this.config.dataDir,
      });
      this.log(`${result.validated ? 'Validated' : 'Not validated'}: ${result.components.length} components, ${result.testsRun} tests run${result.jobId ? `, job ${result.jobId}` : ''}`);
      for (const failure of result.failures) this.log(`  - ${failure}`);
      process.exitCode = result.validated ? 0 : 1;
      return result;
    });
  }
}
