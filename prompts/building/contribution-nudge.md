# Contribution Nudge — Capture for the Community

Read + executed by `/scout-building` **Step 7**, as the final beat AFTER the
command-level "tinker with your demo" closing note. Cartridge-conditional and
silent by default: it fires only when an installed knowledge cartridge covers
this org's industry AND the build actually produced something reusable.

**Why this lives in Scout, not the cartridge.** A conforming knowledge cartridge
(e.g. the LS Booster Pack) ships its own contribution nudge inside its passive
skills — an offer to capture a trap/recipe at the end of a session. But those
skills stay dormant inside a `/scout-building` session: Scout follows its own
close sequence and never activates a passive cartridge skill mid-flow. So the
nudge never reaches an SE who just built a cartridge-covered demo *with Scout*.
This fragment is the write-direction twin of `prompts/sparring/knowledge-cartridge.md`
(the read seam) — same structural detection, fired from Scout's own close.

**Dependency direction (do not invert):** Scout reads the cartridge's published
contract to decide WHETHER to fire; it names no cartridge for that decision. The
offer text names `/ls-contribute` because the LS Booster Pack is the only
cartridge today and owns that command. If a second cartridge ever ships a
capture command under a different name, revisit — do not add a hardcoded
cartridge dependency for the fire decision.

## Step 1 — Discover conforming cartridges (cheap; always runs)

Same discovery as the read seam. A **conforming knowledge cartridge** is an
installed plugin whose cache version dir contains BOTH `INTEGRATING.md` and
`KNOWLEDGE-INDEX.md` at its root (latest version dir per plugin):

```bash
for KIDX in $(find "$HOME/.claude/plugins/cache" -name KNOWLEDGE-INDEX.md 2>/dev/null); do
  DIR=$(dirname "$KIDX")
  [ -f "$DIR/INTEGRATING.md" ] && echo "$DIR"
done | sort -V | awk -F/ '{ key=$(NF-1); ver=$NF; latest[key]=$0 } END { for (k in latest) print latest[k] }'
```

If NO conforming cartridge is found: emit nothing, STOP this fragment. This is
the common case on a machine with no cartridge installed — zero ceremony.

## Step 2 — Match this build's industry against each cartridge's Coverage

Each conforming cartridge declares a machine-readable **Coverage** block near the
top of its `KNOWLEDGE-INDEX.md`:

```
## Coverage
industry: <human name, e.g. Life Sciences>
signals:
  namespaces: [<managed-package namespaces, e.g. lsc4ce>]
  objects: [<distinctive EntityDefinition API names, if any>]
```

Unlike the sparring read seam (which matches against a fresh audit), the build
session already carries the industry signal in the spec Scout deployed from:
- the spec's **`Industry vertical:`** line (Customer Context section), and
- any managed/industry **namespaces** in the spec's **Platform Constraints**
  block (`namespace=<...>` entries) and the managed/industry object API names
  named there.

**Match = the cartridge's declared `industry` matches the spec's Industry
vertical, OR the cartridge's declared `namespaces`/`objects` overlap the
namespaces/objects in the spec's Platform Constraints.** Match on any signal
overlap; do not require all.

- **No cartridge matches** → STOP this fragment. Proceed silently — do NOT tell
  the SE a cartridge is missing or that one would help. (Same no-nag discipline
  as the read seam: Scout can't tell "no cartridge exists" from "exists but not
  installed," and nagging about an uninstallable pack is noise. A Manufacturing
  demo on a machine with only the LS cartridge installed hits this branch and
  stays silent.)
- **A cartridge matches** → Step 3.

## Step 3 — Reusability gate (fire only on a real trap/recipe)

A nudge on every routine build trains SEs to ignore it. Fire ONLY when this
build actually produced something worth another SE reusing — judged from the
change log Scout just wrote (Step 6) and what happened this session:

- **Fire** when the build included a genuine **trap** (a fix or workaround for a
  product limitation or a non-obvious config/build gotcha) OR a reusable
  **recipe** (a slick component, a non-obvious data pattern, a multi-component /
  Agentforce topology whose value is its shape).
- **Do NOT fire** on a vanilla "deployed the spec as written" run with no
  non-obvious problem solved and nothing reusable beyond the spec itself. STOP
  silently.

When in doubt, lean toward NOT firing — a missed nudge costs nothing; a noisy
one erodes every future nudge.

## Step 4 — Offer once (never assume, never recurring)

If Steps 1–3 all passed, emit exactly one offer as a short standalone beat, then
drop it:

> 💡 **This looks worth sharing with the team.** You worked out something
> reusable here that the next SE building on this [industry] cartridge would
> want — want me to capture it with `/ls-contribute` so it lands in the shared
> library, credited to you?

Substitute `[industry]` with the matched cartridge's declared `industry`. One
offer, at the close, only when Steps 1–3 fired. If the SE declines or ignores
it, drop it — never re-prompt, never make it a gate, never block the session
close. The capture skill itself (the cartridge's `/ls-contribute`) owns the
actual draft/scrub/transport flow; this fragment only surfaces the door.

## After this fragment

The `/scout-building` session is complete. This fragment adds an offer only when
a cartridge matches and the build was reusable; it changes no gating and blocks
nothing. On any build with no matching cartridge, or a routine spec deploy, it
is fully silent.
