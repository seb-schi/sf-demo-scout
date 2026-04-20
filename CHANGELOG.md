# Changelog

All notable changes to SF Demo Scout.
Compare your last `update.sh` date against section headers to see what you missed.

## 2026-04-20

### Added
- Platform restriction auto-detection from EntityDefinition flags (sparring warns before speccing)
- Data shape validation before spec writing (checks sample records, lookup population, filterability)
- Lessons maintenance prompt — offers trim review when lessons file exceeds 25 lines
- Docs fallback via FieldDefinition when Salesforce Docs search returns no results

### Changed
- Update mechanism is now `update.sh` (nuke-and-reinstall) — replaces incremental git pull
- Lessons files moved to `orgs/` so they persist across updates
- Audit flow enumeration is data-driven (GROUP BY) instead of hardcoded object list
- Scout sparring split into smaller on-demand files for faster context loading

### Fixed
- MCP server timeout on first launch (package now pre-cached during install)
- Stale SF CLI causing MCP failures (install.sh now auto-updates CLI)
- Incorrect EntityDefinition flag (IsCreatable → IsEverCreatable)

## 2026-04-19

### Added
- Audit split into 3 parallel sub-agents — handles large orgs without hitting output caps
- Queues and picklist value additions now deployable autonomously (no SE gate)
- Agentforce smoke testing via `sf agent preview` after deployment
- Industry object auto-detection in audit (Health Cloud, FSC, Insurance, Manufacturing)
- Platform & data model research stage runs before scenario proposal

### Changed
- Audit prompts rewritten for accuracy (correct SOQL fields, Tooling API fallbacks)
- Expanded automation scope — fewer items on SE Manual Checklist

### Fixed
- Session startup org detection failing on pretty-printed JSON
- Audit silent truncation on large orgs (now uses count-first approach)
- Audit falsely reporting "no agents" when GenAiPlanners exist

## 2026-04-18

### Added
- Salesforce Docs MCP integration — feature verification during sparring, error diagnosis during building
- Docs consultation decision tree (targeted lookups, not ambient)
- Sub-agent orchestrator architecture — Opus orchestrates, Sonnet executes deployment phases

### Changed
- Sub-agent prompts no longer inject full skill file contents (10-20K tokens saved per run)
- Spec template gains Release Notes & Citations section
- Change log template gains Docs Consulted section

## 2026-04-17

### Added
- `/sync-skills` command — pull latest external skills from manifest
- Skill manifest (`.claude/skills-manifest.yaml`) as single source of truth for external skills

### Fixed
- `/switch-org` writing to global scope instead of local (caused MCP to read wrong org)

## 2026-04-16

### Added
- Generating skills from AFV library (custom-field, custom-object, permission-set)
- Sub-agent output validation with structured JSON and recovery gates

## 2026-04-15

### Added
- Claude Code auto-installation in `install.sh` (fully self-contained setup)

### Changed
- Skill folders no longer use underscore prefix
- Model gates simplified to markdown blockquotes

## 2026-04-14

### Added
- Permission allow-rules in settings (targeted, persistent, no SE action needed)
- Agentforce as first-class category in sparring
- Iteration path in scout-sparring (lighter discovery for targeted changes to existing demos)

### Changed
- Session startup displays active org, username, and connection status automatically
- Org identity read dynamically from `sf config` — no manual CLAUDE.md editing
- Heavy skill loads deferred to on-demand (faster session startup)

### Fixed
- Stale command references and HLS/DACH hardcoding removed
- Logging anti-pattern — all bookkeeping now completes before "done" signal

### Removed
- Manual org configuration in CLAUDE.md
- Web tools (incompatible with Bedrock)
