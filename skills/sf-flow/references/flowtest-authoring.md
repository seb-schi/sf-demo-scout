# FlowTest authoring and failure diagnosis

Use this reference for eligible FlowTest metadata. Callers own authorization, required test names, version acceptance, activation, and rollback. A test failure never authorizes replacing that gate or expanding the permitted tooling.

## Schema and API applicability

The [FlowTest Metadata API reference](https://developer.salesforce.com/docs/atlas.en-us.api_meta.meta/api_meta/meta_flowtest.htm) defines FlowTest from API 55.0, and `flowTestFlowVersions`, `testType`, and `InputVariable` from 66.0. These templates require **effective deployment API 66.0 or later**; Flow XML's `apiVersion` alone does not establish that. Confirm the target and deployment API without silently changing project settings. Do not copy fields marked 67.0 into a 66.0 deployment.

`FlowTest` has no `apiVersion` child. Its `flowApiName` names the Flow; its filename supplies the test identity. Use `flowTestFlowVersions/flowVersionNumber` for the intended version, then verify actual execution separately. `testPoints/elementApiName` anchors are `Start` and `Finish`. Input parameters use `leftValueReference`, `type`, and `value`, never per-field `name`. Trigger-record parameters reference `$Record` with the complete typed record in `sobjectValue`. An updated-record case needs initial and updated record parameters. Autolaunched inputs use the declared variable name and `InputVariable`. `elementReference` under **FlowTestReferenceOrValue** is reserved; this restriction does not define permitted condition `leftValueReference` resources.

The [Spring '26 metadata release notes](https://help.salesforce.com/s/articleView?id=release-notes.rn_api_meta.htm&language=en_US&release=260&type=5) independently identify version association, assertion type, and autolaunched inputs as additions. Check current target-specific documentation when extending beyond these examples.

## Choose and materialize a template

- [Record-triggered create](../assets/flowtests/record-triggered-create.flowTest-meta.xml): one typed `$Record` fixture and a business-field assertion.
- [Autolaunched input](../assets/flowtests/autolaunched-input.flowTest-meta.xml): a text input and a business-output assertion.

Save the selected file under `flowtests/<ExactTestApiName>.flowTest-meta.xml` in source format. Metadata API format instead uses `.flowtest`. Replace every `{{...}}` token. Serialize `TRIGGER_RECORD_JSON` as JSON including `attributes.type`, then XML-escape it once as element text. XML-escape all other text replacements too. Use synthetic values, known field API names, valid required fields, and fixed dates appropriate to the obligation. Avoid customer identifiers, guessed IDs, and implicit org defaults.

For example, a Task fixture can use `{"attributes":{"type":"Task"},"Subject":"Flow fixture","Status":"Not Started","Priority":"Normal"}` where those picklist values are valid. A before-save Flow that assigns Priority High should assert `$Record.Priority EqualTo High` at Finish. For an autolaunched Flow use an actual output such as `resultText`; do not copy `$Record` from a triggering example. Change the value child to the documented matching type when testing booleans, numbers, dates, or a record-valued input; a record input uses `sobjectValue`. Add separate named tests for distinct required behaviors.

A happy-path test needs a business outcome. `$Flow.FaultMessage IsNull=true` alone can pass when the requested work never happened. An additional fault assertion is optional and needs its own justified semantics. Give every assertion a distinct failure message. For intentional exclusion, assert the relevant unchanged state only when the target evaluates that resource for this fixture; do not assume Finish runs or declare exclusion untestable from an aggregate failure. Never invent `WasVisited`/`WasSet` syntax for a particular element solely because the enum exists.

## Supported shapes and execution

[Salesforce's automated Flow testing guide](https://help.salesforce.com/s/articleView?id=platform.automate_flow_test_record_data_cloud_triggered.htm&language=en_US&type=5) covers record-triggered, autolaunched, and Data Cloud-triggered flows; excludes delete triggers and asynchronous paths, and autolaunched callouts/waits. Verify the specific shape. These two templates do not establish a Data Cloud fixture recipe. Unsupported shapes need caller-approved alternative QA. A missing capability does not downgrade a required test. Isolated data-silo setup is a distinct API 66 feature that requires Apex setup; do not introduce it where Apex is outside scope. Tests can persist execution records even when business data is rolled back.

Use the [CLI Flow test reference](https://developer.salesforce.com/docs/platform/salesforce-cli-reference/guide/cli_reference_flow_run_test.html) and installed help to confirm available flags. `--class-names` takes **Flow names**, not FlowTest names. Prefer exact tests when the caller supplies required identities:

```bash
sf flow run test --tests MyFlow.Happy --tests MyFlow.Excluded --test-level RunSpecifiedTests --synchronous --target-org TARGET --json
```

Synchronous execution is limited to one Flow. Async execution returns a run identity; fetch terminal output using the supported `sf flow get test --test-run-id RUN_ID --target-org TARGET --json` path. An enqueue receipt is not a completed pass.

Distinguish three result surfaces. The [unified Test Runner API](https://help.salesforce.com/s/articleView?id=release-notes.rn_api_tooling_unified_testing.htm&language=en_US&release=258&type=5) supports Flow and Apex tests and can return a synchronous per-method `id` identifying an `ApexTestResult`; the response property is not literally `ApexTestResultId`. The public [FlowTestResult object reference](https://developer.salesforce.com/docs/atlas.en-us.object_reference.meta/object_reference/sforce_api_objects_flowtestresult.htm) describes Flow/test/version, result, and timing fields, without the Apex relationship fields. An API-66 **Tooling** describe and query observed during Scout qualification additionally exposed `ApexTestResultId` and `ApexTestQueueItemId`, including a synchronous Flow result with a real method-result ID and null queue ID. That observed projection is target-dependent: the [Tooling API reference](https://resources.docs.salesforce.com/latest/latest/en-us/sfdc/pdf/api_tooling.pdf) labels `FlowTestResult` reserved for internal use, so it is not a universal supported-field promise.

Before relying on that bridge, retain a fresh describe of the selected target/API surface and an exact query proving the method-result relationship (sync) or queue/result relationship (async). Do not infer a field from its presence on another API surface or org. Preserve actual returned identities without inventing a queue/run ID. FlowTestViewId, FlowVersionViewId/FlowVersionNumber, result and timestamps help identify a record, but a name/time match alone does not link it to this invocation. If the bridge is unavailable and no supported exact relationship is established, report the evidence gap and leave required validation incomplete; do not downgrade the Flow shape to unsupported or silently weaken correlation. Retain raw launch, terminal, describe and exact-version query receipts and apply the caller's complete required-test gate.

## Bounded diagnosis

1. **Execution/tool failure:** distinguish command readiness, schema, auth, and transport errors from an executed failed test. Preserve the actual receipt. An explicit host/tool/policy refusal stops that mutation; do not retry it through another tool. Routine work already authorized needs no new approval merely because it uses a different supported non-refused read operation.
2. **Missing evidence:** a null queue ID on a synchronous result, unavailable details, or empty coverage does not establish a Flow defect. Query only described correlation fields; keep the acceptance gap if exact attribution is unavailable.
3. **Fixture/assertion failure:** inspect the exact deployed test, input values, and individual assertion/path details where available. Change only the demonstrated fixture/assertion issue while retaining its behavioral obligation and Flow version. A combined assertion failure does not identify which condition failed.
4. **Flow defect:** change Flow logic only when the observed path/value contradicts the intended business behavior. Record the new version and rerun all required tests for that version before activation.

Before any retry, state the competing hypothesis, one changed variable, and the observation that would discriminate it. Keep the caller's attempt limit; absent one, allow at most one supported correction and one verification per failure class, then report the remaining gap. Never rerun unchanged tests hoping for Pass or automatically create a new Flow version for a test-only repair. An inconclusive exclusion case belongs in a separately authorized disposable-target experiment; it does not justify activating the original Flow or weakening its acceptance obligation.
