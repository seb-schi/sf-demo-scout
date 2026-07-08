# Setup — .zshrc Managed Block

Refresh `~/.zshrc` with the Scout-managed environment block (idempotent). Adds `~/.local/bin` to PATH if missing, rewrites the managed `# BEGIN SF-DEMO-SCOUT` … `# END SF-DEMO-SCOUT` block with current canonical values, sweeps Scout-owned keys that escaped the block (including the retired `MAX_THINKING_TOKENS` — swept out and never re-added; see below), and warns about legacy `ANTHROPIC_MODEL`.

```bash
ZSHRC="$HOME/.zshrc"
touch "$ZSHRC"
ZSHRC_BEFORE_HASH=$(shasum "$ZSHRC" | awk '{print $1}')

# Ensure ~/.local/bin is on PATH — Anthropic's CC installer puts the
# `claude` binary there. Append once, outside the managed block, so SE
# overrides aren't clobbered. Idempotent.
if ! grep -q 'PATH="\$HOME/.local/bin' "$ZSHRC" 2>/dev/null; then
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$ZSHRC"
fi

python3 - "$ZSHRC" <<'PYEOF'
import re, sys
path = sys.argv[1]
BEGIN = "# BEGIN SF-DEMO-SCOUT"
END = "# END SF-DEMO-SCOUT"
KEYS = [
    "CLAUDE_CODE_MAX_OUTPUT_TOKENS",
    "MAX_THINKING_TOKENS",
    # Model-profile pins: swept as out-of-block stragglers so a loose
    # legacy export no longer collapses the terminal /model picker. NOT in
    # BLOCK_LINES — Scout strips these, never re-adds them (Scout is out of
    # model selection; SE picks via /model). Reverses 2026-06-02's removal.
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
]
BLOCK_LINES = [
    BEGIN,
    "# Managed by Scout plugin — do not edit. Refreshed on first-run setup.",
    "export CLAUDE_CODE_MAX_OUTPUT_TOKENS=16384",
    END,
]

with open(path) as f:
    lines = f.readlines()

key_re = re.compile(r'^\s*export\s+(' + '|'.join(re.escape(k) for k in KEYS) + r')\s*=')
legacy_re = re.compile(r'^# \[sf-demo-scout \d{4}-\d{2}-\d{2}\] superseded by managed block: ')

in_block = False
out = []
for line in lines:
    stripped = line.rstrip('\n')
    if stripped == BEGIN:
        in_block = True
        out.append(line); continue
    if stripped == END:
        in_block = False
        out.append(line); continue
    if not in_block and key_re.match(line):
        continue
    if legacy_re.match(line):
        continue
    out.append(line)

cleaned = []
skip = False
for line in out:
    stripped = line.rstrip('\n')
    if stripped == BEGIN:
        skip = True
        continue
    if stripped == END:
        skip = False
        continue
    if not skip:
        cleaned.append(line)

while cleaned and cleaned[-1].strip() == "":
    cleaned.pop()

body = "".join(cleaned)
if body and not body.endswith("\n"):
    body += "\n"
body += "\n" + "\n".join(BLOCK_LINES) + "\n"

with open(path, "w") as f:
    f.write(body)
PYEOF

ZSHRC_AFTER_HASH=$(shasum "$ZSHRC" | awk '{print $1}')
if [ "$ZSHRC_BEFORE_HASH" = "$ZSHRC_AFTER_HASH" ]; then
  echo "ZSHRC_UNCHANGED"
else
  echo "ZSHRC_MODIFIED"
fi

if grep -qE '^\s*export\s+ANTHROPIC_MODEL\s*=' "$ZSHRC" 2>/dev/null; then
  echo "ANTHROPIC_MODEL_PRESENT"
fi
```

If `ANTHROPIC_MODEL_PRESENT`, surface a one-line warning:

> "⚠️ Found legacy `ANTHROPIC_MODEL` in your `~/.zshrc` — this is not a Claude Code variable. Remove it manually."

## Done

Return to the dispatching prompt. Pass back `ZSHRC_UNCHANGED` or `ZSHRC_MODIFIED` (and optional `ANTHROPIC_MODEL_PRESENT`) so `done.md` can compose the right closing note.
