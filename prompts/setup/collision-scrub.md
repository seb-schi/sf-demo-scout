# Setup — Collision Scrub

Detected old clone-install residue (both `.git/` and `install.sh` present in workspace). Scrub it before proceeding. Preserves SE data (`orgs/`, `.sf/`, `force-app/`, `sfdx-project.json`).

```bash
cd "$HOME/claude-projects/sf-demo-scout"
rm -rf .git
rm -f install.sh
rm -rf .claude
echo "COLLISION_SCRUBBED"
```

Surface to SE:

> "Detected old clone-install residue — removed `.git/`, `install.sh`, and `.claude/`. Your `orgs/` data and Salesforce project structure are preserved. Proceeding with fresh setup."

After scrub, return to the orchestrator — it will dispatch to `fresh-install.md` next.
