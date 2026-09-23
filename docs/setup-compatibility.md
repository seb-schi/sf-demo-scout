# Setup compatibility and reviewed defaults

For the 2026-09-23 Claude/Codex audit, host selection, DX packaging correction,
and verification limits, see [MCP host compatibility](mcp-host-compatibility.md).
The provider defaults below remain unchanged. The historical Claude syntax
applies only when Claude is the active host.

Reviewed 2026-09-17 against the official Claude Code
[setup documentation](https://code.claude.com/docs/en/setup) and
[MCP documentation](https://code.claude.com/docs/en/mcp), plus npm's
[`npm root`](https://docs.npmjs.com/cli/v11/commands/npm-root/) and
[`package.json`](https://docs.npmjs.com/cli/v11/configuring-npm/package-json/)
documentation.

## Documented syntax and behavior

Claude Code supports MCP registration commands with user scope and HTTP or
local-process transports. Its MCP list is a status view, not a complete
configuration inventory: WebSocket servers and some rejected entries may be
omitted. Scout therefore treats failed, malformed, unsupported, nonmatching,
or ambiguous list output as inconclusive. It does not auto-create a replacement.
The read-only list call has a 10-second bound. This avoids hanging setup while
allowing the client time to health-check several remote services; slower checks
degrade to unknown and require an SE to inspect `/mcp`.

The setup refresh updates a CLI through npm only after the current npm global
root, package metadata, declared bin, and active resolved executable all agree.
Native, standalone, shadowed, malformed, and unverifiable installations remain
unchanged. Scout does not choose an updater until ownership is established.

Fresh installation uses a Bash-only bootstrap because Python may not exist yet.
It accepts a selected Node, Python, or Salesforce CLI only after a successful,
complete version probe. Existing invalid tools are left untouched rather than
replaced with a competing runtime. Only a missing executable permits the
existing Homebrew or npm route, and installer exit 0 is followed by a fresh
probe of the selected executable before setup continues. Python support remains
major 3, version 3.9 or newer; Homebrew's current `python3` alias is used instead
of forcing a minor release. This follows Homebrew's reviewed
[runtime guidance](https://docs.brew.sh/Language-Runtimes-and-Packages)
(2026-09-17). The offline checks do not establish actual Python 3.9 runtime
compatibility; that floor has static review plus local Python 3.10 parsing only.

## Historical Scout deployment defaults

These values were observed in prior Scout deployments and are offered for an
explicit SE choice. They are not universal provider compatibility guarantees:

Provenance: retained from Scout commit `4ccd050`, in the three provider
fragments under `prompts/setup/`. This review did not revalidate those live
endpoints, OAuth registrations, or adaptor deployments.

- Slack: `https://mcp.slack.com/mcp`, OAuth client id
  `188160004832.9210129962818`, callback port `3118`.
- Google Workspace: DevBar `mcp-adaptor`, server `google_workspace`, provider
  `google-workspace-rw`.
- Salesforce Docs:
  `https://salesforce-docs-76258744c9d7.herokuapp.com/api/mcp`.

Registration and transport state never establish authentication or required
tool capability. Scout discovers tools at the point of use and requires the
first needed call to succeed before treating the provider as usable, with an honest degraded path when tools are
unavailable, failed, or require authentication.

Salesforce DX MCP remains the existing unpinned `npx -y @salesforce/mcp`
declaration. Batch 8a did not perform a provider acceptance test and does not
claim or invent a tested package pin.

## Review triggers and limits

The Scout maintainers own these reviewed defaults. Re-review the official
sources and rerun the offline ownership/status fixtures when a provider default,
Claude MCP list format, npm package metadata shape, setup CLI behavior, or
supported CLI version changes. Changes to a provider, launcher, endpoint, auth
flow, or required tool also require a provider-specific capability acceptance
check before making compatibility claims.

The offline fixtures validate Scout's conservative parsing and no-write
behavior. They do not validate live credentials, provider reachability,
published tools, npm registry availability, or end-to-end provider capability.
