#!/bin/bash

ZSHRC="${SCOUT_ZSHRC_OVERRIDE:-$HOME/.zshrc}"

ZSHRC_STATUS=$(PYTHONDONTWRITEBYTECODE=1 python3 -B - "$ZSHRC" <<'PYEOF'
import os, re, sys, shutil, subprocess, tempfile

path = sys.argv[1]
BEGIN = "# BEGIN SF-DEMO-SCOUT"
END = "# END SF-DEMO-SCOUT"
# Keys Scout used to export and now sweeps as out-of-block stragglers (never
# re-added). Retired output-length knobs + the model-profile pins.
KEYS = [
    "CLAUDE_CODE_MAX_OUTPUT_TOKENS",
    "MAX_THINKING_TOKENS",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
]
BLOCK_LINES = [
    BEGIN,
    "# Managed by Scout plugin — do not edit. Refreshed on first-run setup.",
    "# Scout sets no shell environment variables (output-length knob retired 2026-07-27).",
    END,
]
PATH_LINE = 'export PATH="$HOME/.local/bin:$PATH"'


def emit(tok):
    print(tok)


# SINGLE delimiter recognition, used in validation AND both rewrite passes so they
# can never disagree (R1). Exact-marker contract: the line minus its trailing
# newline must equal the marker exactly — no whitespace tolerance.
def is_marker(line, marker):
    return line.rstrip("\n") == marker


# Validator honors the SCOUT_ZSH_BIN test seam, then a real `zsh`, then /bin/zsh.
zsh = os.environ.get("SCOUT_ZSH_BIN") or shutil.which("zsh") or ("/bin/zsh" if os.path.exists("/bin/zsh") else None)
if not zsh:
    emit("ZSHRC_VALIDATOR_UNAVAILABLE")
    sys.exit(0)


def syntax_ok(p):
    # Parse-check only (-n), skipping rc files (-f). Never sources the file.
    # A missing/unusable validator binary raises -> None (treated as unavailable).
    try:
        r = subprocess.run([zsh, "-f", "-n", p],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return r.returncode == 0
    except Exception:
        return None


# (1) Classify the path: symlink BEFORE missing-file (R2). os.path.exists follows
# links, so a dangling link would otherwise look like an absent regular file and
# get its target created.
if os.path.islink(path):
    target = os.path.realpath(path)
    if not os.path.exists(target):
        emit("ZSHRC_SYMLINK_BROKEN")
        sys.exit(0)
    with open(path) as f:
        original = f.read()
    missing = False
elif os.path.exists(path):
    with open(path) as f:
        original = f.read()
    missing = False
else:
    original = ""
    missing = True

# (3) Original syntax gate — before any mutation. Empty first-install is valid.
if not missing:
    ok = syntax_ok(path)
    if ok is None:
        emit("ZSHRC_VALIDATOR_UNAVAILABLE")
        sys.exit(0)
    if not ok:
        emit("ZSHRC_ORIGINAL_INVALID")
        sys.exit(0)

# (4) Marker-structure gate — SAME recognition as the passes below.
lines = original.splitlines()
# Reject marker-shaped lines with trailing spaces/tabs even when BOTH are
# malformed; otherwise they look like the zero-marker first-install case.
if any(l.rstrip(" \t") in (BEGIN, END) and l not in (BEGIN, END) for l in lines):
    emit("ZSHRC_MARKERS_INVALID")
    sys.exit(0)
begins = [i for i, l in enumerate(lines) if is_marker(l, BEGIN)]
ends = [i for i, l in enumerate(lines) if is_marker(l, END)]
valid_markers = (
    (len(begins) == 0 and len(ends) == 0) or
    (len(begins) == 1 and len(ends) == 1 and begins[0] < ends[0])
)
if not valid_markers:
    emit("ZSHRC_MARKERS_INVALID")
    sys.exit(0)

# (5) Compute new content in memory. Pass 1: strip out-of-block KEY stragglers +
# legacy superseded-comment lines.
src = original.splitlines(keepends=True)
key_re = re.compile(r'^\s*export\s+(' + '|'.join(re.escape(k) for k in KEYS) + r')\s*=')
legacy_re = re.compile(r'^# \[sf-demo-scout \d{4}-\d{2}-\d{2}\] superseded by managed block: ')

in_block = False
out = []
for line in src:
    if is_marker(line, BEGIN):
        in_block = True
        out.append(line)
        continue
    if is_marker(line, END):
        in_block = False
        out.append(line)
        continue
    if not in_block and key_re.match(line):
        continue
    if legacy_re.match(line):
        continue
    out.append(line)

# Pass 2: remove the existing managed block entirely (SAME recognition).
cleaned = []
skip = False
for line in out:
    if is_marker(line, BEGIN):
        skip = True
        continue
    if is_marker(line, END):
        skip = False
        continue
    if not skip:
        cleaned.append(line)

# Ensure the PATH line is present (outside the block). Append once if absent.
body_text = "".join(cleaned)
if not re.search(r'^\s*export\s+PATH="\$HOME/\.local/bin', body_text, re.M):
    if body_text and not body_text.endswith("\n"):
        body_text += "\n"
    body_text += PATH_LINE + "\n"
    cleaned = body_text.splitlines(keepends=True)

# Trim trailing blank lines, then append the fresh managed block.
while cleaned and cleaned[-1].strip() == "":
    cleaned.pop()
body = "".join(cleaned)
if body and not body.endswith("\n"):
    body += "\n"
body += "\n" + "\n".join(BLOCK_LINES) + "\n"

if body == original:
    emit("ZSHRC_UNCHANGED")
    sys.exit(0)

# (6)+(7) Stage beside the real target, syntax-check, back up, atomic replace.
# Symlink: preserve the link, replace the resolved target in place.
write_target = os.path.realpath(path) if os.path.islink(path) else path
target_dir = os.path.dirname(write_target) or "."
tmp = None
try:
    fd, tmp = tempfile.mkstemp(prefix=".scout-zshrc.", dir=target_dir)
    with os.fdopen(fd, "w") as f:
        f.write(body)
    ok = syntax_ok(tmp)
    if ok is None:
        os.unlink(tmp)
        emit("ZSHRC_VALIDATOR_UNAVAILABLE")
        sys.exit(0)
    if not ok:
        os.unlink(tmp)
        emit("ZSHRC_RESULT_REJECTED")
        sys.exit(0)
    if os.path.exists(write_target):
        shutil.copy2(write_target, write_target + ".scout-bak-zshrc")
        os.chmod(tmp, os.stat(write_target).st_mode & 0o777)
    else:
        os.chmod(tmp, 0o644)
    os.replace(tmp, write_target)
    emit("ZSHRC_MODIFIED")
except Exception as e:
    if tmp and os.path.exists(tmp):
        try:
            os.unlink(tmp)
        except Exception:
            pass
    emit("ZSHRC_WRITE_FAILED: %s" % e)
    sys.exit(0)
PYEOF
)

# Map the transactional status to (a) the orchestrator token the done step reads
# (ZSHRC_MODIFIED / ZSHRC_UNCHANGED — every skip/reject is "nothing changed") and
# (b) an SE-facing diagnostic. The model shows any SCOUT_ZSHRC_DIAG line to the SE.
case "$ZSHRC_STATUS" in
  ZSHRC_MODIFIED)
    echo "ZSHRC_MODIFIED" ;;
  ZSHRC_UNCHANGED)
    echo "ZSHRC_UNCHANGED" ;;
  ZSHRC_MARKERS_INVALID)
    echo "ZSHRC_UNCHANGED"
    echo "SCOUT_ZSHRC_DIAG: Scout found malformed \`# BEGIN/END SF-DEMO-SCOUT\` markers in your ~/.zshrc (missing, reversed, duplicated, nested, or not an exact match). Left the file byte-for-byte unchanged. Fix or delete both marker lines, then re-run /scout-setup." ;;
  ZSHRC_ORIGINAL_INVALID)
    echo "ZSHRC_UNCHANGED"
    echo "SCOUT_ZSHRC_DIAG: pre-existing shell syntax error in your ~/.zshrc — Scout shell repair skipped (Scout did NOT cause this). Fix the syntax and re-run /scout-setup; the rest of setup continued." ;;
  ZSHRC_RESULT_REJECTED)
    echo "ZSHRC_UNCHANGED"
    echo "SCOUT_ZSHRC_DIAG: the proposed Scout shell edit was rejected — applying it would have produced invalid zsh (likely a multi-line export Scout can't safely rewrite). Left your ~/.zshrc unchanged." ;;
  ZSHRC_SYMLINK_BROKEN)
    echo "ZSHRC_UNCHANGED"
    echo "SCOUT_ZSHRC_DIAG: ~/.zshrc is a symlink whose target is missing — left untouched." ;;
  ZSHRC_VALIDATOR_UNAVAILABLE)
    echo "ZSHRC_UNCHANGED"
    echo "SCOUT_ZSHRC_DIAG: couldn't find a \`zsh\` validator to safely syntax-check the shell file — skipped the managed-block refresh this run (no unchecked write attempted)." ;;
  ZSHRC_WRITE_FAILED*)
    echo "ZSHRC_UNCHANGED"
    echo "SCOUT_ZSHRC_DIAG: ${ZSHRC_STATUS} — original preserved." ;;
  *)
    echo "ZSHRC_UNCHANGED"
    echo "SCOUT_ZSHRC_DIAG: unexpected zshrc-refresh status: ${ZSHRC_STATUS}" ;;
esac

if grep -qE '^\s*export\s+ANTHROPIC_MODEL\s*=' "$ZSHRC" 2>/dev/null; then
  echo "ANTHROPIC_MODEL_PRESENT"
fi
