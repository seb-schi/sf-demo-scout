# Scout MCP host compatibility

Source audit and fixes: 2026-09-23, version `2026.09.23-host-aware-mcp`.
This records source changes and their verification limits, not a claim that
an installed plugin or a live Salesforce connection has already been updated.

## Salesforce CLI and DX MCP are separate

`scout-setup` installs the Salesforce CLI (`sf`) on the machine when missing.
That CLI works independently of Scout. Setup also offers to pre-cache
`@salesforce/mcp`, a separate adapter. Scout's plugin manifest declares the
adapter under `Salesforce_DX` and each host launches its own process through
`npx -y @salesforce/mcp`. There is no shared machine-wide MCP connection.

The original `Salesforce DX` key dates to Scout's May 21 scaffold (`6f25550`).
Claude normalizes the space to an underscore in published tool names; the
observed Codex `0.155.0-alpha.16.3` rejects the original identifier before the
MCP handshake. Renaming the declaration preserves the spelling of Claude's
existing permission references without changing the executable, arguments,
toolsets, or org-selection behavior.

## Audit coverage and corrections

The audit covered server declarations, tool/permission references, setup and
repair scripts, startup evidence, discovery, Showtime, handovers, and vendored
skill MCP references across the source tree. Vendored `sf agent mcp` material
describes Salesforce-hosted agent servers, not this client registration, and
was left intact. Human-facing “Salesforce DX” labels remain readable.

| Surface | Finding | Correction |
|---|---|---|
| Plugin manifest | Space in `Salesforce DX` rejected by Codex | Portable `Salesforce_DX` identifier; packaging test checks all JSON MCP declarations |
| Setup diagnostics | Always ran Claude's CLI | Explicit host selection, Codex JSON parsing, conservative unknown state, filtered output |
| DX setup | Pre-cache could be mistaken for readiness | Separate DX diagnostic and session tool discovery |
| Slack/Google discovery, Showtime, handover | Claude `Connected` grep gated other hosts | Required capabilities are discovered in the active session; CLI status is diagnostic |
| Lookup and audit plugin-root resolution | Read Claude's installed-plugin registry; audit workers could guess a cached version | Resolve from the active plugin context and pass an absolute root to workers; unresolved roots stay not-ready |
| Tool names and model selectors | Claude spellings treated as universal | Shared host contract preserves Claude permission metadata; other hosts discover their own callable tools and use their own delegation/model settings |
| Startup | Checked Claude credentials and reused Claude MCP evidence | Host-gated credentials/cache; Codex policy check runs in the current project and persists no raw listing |
| Startup failures | Any non-connected Slack row suggested authentication | Distinct authentication, disabled, failed, pending, unknown, and not-observed states |
| Workspace setup/verification | Required or wrote `.claude/settings.json` | Explicit `--host codex` handles common Salesforce artifacts without touching either host's settings |
| Setup repairs | Claude updates/settings/shell repairs could run from Codex | Host-scoped steps; MCP-prefix repair requires explicit `--host claude` |
| Maintainer uninstall | Could imply removing Codex while deleting Claude's files | Explicit `--host claude` required; Codex uses its own plugin controls |
| Docs denial | Managed Baseline prevents the current registration | Report policy denial and policy ID; preserve registration for administrator review |

Claude's existing `mcp__plugin_sf-demo-scout_Salesforce_DX__*` references are
intentional. Changing them to guessed Codex prefixes would introduce another
compatibility bug. Runtime callers now resolve the published operation and its
actual schema. A worker must check its own tool exposure before use.

## Diagnostic contract

Run from the same project directory as the active task:

```bash
python3 /absolute/path/to/scout/scripts/setup-mcp-status.py --host codex salesforce-dx
python3 /absolute/path/to/scout/scripts/setup-mcp-status.py --host codex salesforce-docs
```

Supported providers are `salesforce-dx`, `salesforce-docs`, `slack`, and `google`.
`--host claude` selects Claude. `--host unknown` performs no CLI probe. Hook
auto-detection accepts explicit `SCOUT_HOST` or a single unambiguous
`CODEX_THREAD_ID`/`CLAUDECODE=1` signal; conflicting or absent signals are unknown.
It never chooses whichever CLI happens to be installed.

Output keeps registration, transport, host, policy, reason, and tools separate.
Codex `enabled` means configuration is permitted, not that startup, transport,
authentication, or tool discovery succeeded. All CLI-only results retain
`tools=unknown`. Missing CLI/list entries do not establish absence, especially
for host-managed connectors. Unknown failure text is not echoed. A recognized
managed denial retains only its reason category and UUID policy ID; headers,
arguments, environment values, arbitrary URLs, and raw stderr are never printed.

The local source helper was exercised against the currently installed plugin:
it correctly reported DX as `invalid_server_name` and Docs as
`policy=blocked reason=managed_requirements`. That verifies diagnosis of the
existing installation, not startup of the renamed source declaration.

## Verification and release acceptance

Offline regressions cover both CLI adapters, ambiguous/unsupported hosts,
missing CLI, timeout/failed/malformed output, policy versus user disablement,
alias/signature matching, secret-free output, current-project probing, enabled
registrations with unknown runtime readiness, cross-host cache isolation,
Claude-only repair guards, and Codex workspace preservation. Prompt contracts
check that operational callers do not bring back Claude-only list gates.

Run the full suite from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests -v
```

Observed validation for this change:

- All 15 MCP/host/guard tests and all 8 packaging tests pass.
- The initial full run executed 361 tests: 360 passed, with an intermittent
  failure in an unchanged CLI ownership/update test. The release recheck also
  executed 361 tests: 356 passed, with four failures and one error across five
  test methods. Four affected methods are in the unchanged
  `test_setup.CliRefreshScriptTests`: ownership probing returned
  `*_OWNERSHIP_UNVERIFIED` before the expected test scenario, including one
  missing synthetic npm-call log. These outcomes skip installation safely.
  The fifth was `test_late_cache_publication_failure_discards_all_probe_evidence`:
  its initial startup fixture timed out before reaching the cache-failure check.
- A targeted recheck of those five methods passed four, including the startup
  check. `test_all_historical_cli_outcomes` still failed in two different
  synthetic Claude subcases with `CLAUDE_CLI_OWNERSHIP_UNVERIFIED`. The CLI
  ownership/update scripts and these updater tests are unchanged. The full
  suite is not claimed green; no guard or assertion was weakened for release.
- Bash syntax and `git diff --check` pass. Startup fixtures use a three-second
  ordinary probe budget to avoid unrelated one-second fixture timeouts; the
  deliberate five-second sleep still tests timeout cleanup. Production probe
  timeouts are unchanged.

Before claiming live compatibility after release:

1. Install the updated release through each host's normal plugin flow and start
   a fresh session. Do not hand-edit an installed cache as a lasting fix.
2. Verify effective policy for the resulting `Salesforce_DX` registration, then
   startup and required published tools. Test Claude permission references too.
3. Perform one necessary read-only DX call against an explicitly selected,
   authorized demo org in each host. A listing or pre-cache is insufficient.
4. Have workspace support review the existing Docs name and endpoint against
   the effective policy. Source changes cannot grant that approval.

No endpoint migration, credential repair, policy change, or full Claude/Codex
workflow parity is claimed by the offline tests.

References: [Claude plugin MCP naming](https://code.claude.com/docs/en/mcp#plugin-provided-mcp-servers)
and [Codex managed requirements](https://learn.chatgpt.com/docs/enterprise/managed-configuration).
