#!/usr/bin/env python3
"""Build cards: one card per finished task, which the builder can share in a Slack channel of their choice, and a
monthly summary of counts.

On by default; `cards off` stops them. Each finished task's handover ends with the card's exact text, made from the
build's facts, and one question: share it, with a line of the builder's own? Nothing is posted without that yes,
and Scout posts through the host's own Slack tool. Scout never estimates time itself: the time saved is only ever
the builder's own estimate. It keeps no telemetry. A card the builder doesn't share stays on this machine.

Never in a card: org or customer names, org IDs, usernames, record values, file names or paths. The index maps a hash
of the task record's path to its card, and records the card's file before the card is written, so a task never
gets a second card, even after an interrupted save.

Each subcommand prints one JSON object. Exit 0 done; 2 usage; 3 refused (with a reason); 4 a local file couldn't be
read or written (it's kept as it is).

Files live outside the workspace, in `$SCOUT_FEEDBACK_DIR`, else `~/.config/sf-demo-scout/feedback/`:
- `settings.json`: cards on or off, and the channel the builder shares in
- `index.json`: a hash of each task record's path, and its card's file
- `cards/YYYY-MM/card-YYYYMMDD-HHMM-<6 hex>.json`
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import statistics
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import scout_portable  # noqa: E402
    import scout_history  # noqa: E402
    from scout_report_repair import RepairError, decode  # noqa: E402
    from scout_text import ORDER, category, unseen  # noqa: E402
except ImportError:
    print(json.dumps({"reason": "card helper dependencies unavailable"}))
    raise SystemExit(4)

ROOT = Path(__file__).resolve().parents[1]
HOSTS = ("claude", "codex", "cursor", "unknown")
HOST_NAMES = {"claude": "Claude Code", "codex": "Codex", "cursor": "Cursor"}
STATES = ("offered", "answered", "posting", "shared")
RATINGS = ("good", "ok", "poor")
KINDS = ("hours", "unknown", "none", "time_lost")
PRODUCTS = ("Sales", "Service", "Marketing", "Commerce", "Data 360", "Agentforce", "Industries", "Platform")
DISPOSITIONS = ("applied", "already_satisfied", "failed", "blocked", "unverified", "omitted")
CHECKED_WORDS = {"applied": "applied", "already_satisfied": "already there", "failed": "failed", "blocked": "blocked",
                 "unverified": "unverified", "omitted": "skipped"}
CARD_KEYS = {"schema", "card_id", "created_at", "scout_version", "host", "state", "rating", "time_saved",
             "categories", "products", "dispositions", "logbook", "comment", "previewed"}
COMMENT_LIMIT = 500
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ORG_URL = re.compile(r"(?i)\b[\w-]+(?:\.[\w-]+)*\.(?:salesforce|force|visualforce|site)\.com\b")
TOKEN = re.compile(r"\b[0-9A-Za-z]{15}(?:[0-9A-Za-z]{3})?\b")
CHANNEL = re.compile(r"^#?([a-z0-9][a-z0-9._-]{0,79})$")
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
CARD_FILE = re.compile(r"^card-\d{8}-\d{4}-[0-9a-f]{6}\.json$")
SLOT = re.compile(r"^cards/\d{4}-(0[1-9]|1[0-2])/card-\d{8}-\d{4}-[0-9a-f]{6}\.json$")


class Refused(Exception):
    """Exit 3: nothing was written."""


class Unreadable(Exception):
    """Exit 4: a local file couldn't be read or written; it's kept as it is."""


# --- files ------------------------------------------------------------------------------------------------------

def folder() -> Path:
    configured = os.environ.get("SCOUT_FEEDBACK_DIR")
    return Path(configured) if configured else Path.home() / ".config" / "sf-demo-scout" / "feedback"


def read_json(path: Path, empty):
    if not path.exists():
        return empty
    try:
        value = decode(path.read_bytes())
    except (OSError, ValueError, UnicodeError, RepairError, RecursionError) as error:
        raise Unreadable("unreadable, kept as it is: %s" % path) from error
    if not isinstance(value, type(empty)):
        raise Unreadable("unexpected shape, kept as it is: %s" % path)
    return value


def private(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass


def write_atomic(path: Path, value, *, exclusive=False) -> None:
    """A temp file beside the target, then a rename; `exclusive` raises FileExistsError rather than replace a file."""
    private(path.parent)
    temporary = path.with_name(".%s.%s.tmp" % (path.name, secrets.token_hex(4)))
    try:
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        if exclusive:
            os.link(temporary, path)
        else:
            scout_portable.replace(temporary, path)
    except FileExistsError:
        raise
    except OSError as error:
        raise Unreadable("couldn't write %s: %s" % (path, error.strerror or error)) from error
    finally:
        if temporary.exists():
            temporary.unlink()


def file_stamp(path: Path):
    try:
        info = path.stat()
    except FileNotFoundError:
        return None
    return info.st_mtime_ns, info.st_size


def mutate(path: Path, empty, change):
    """Read, change and write one file under its lock, so a second Scout's change is never lost."""
    private(path.parent)
    for _ in range(40):
        try:
            with scout_portable.lock(path.with_name(path.name + ".lock")):
                before = file_stamp(path)
                value = read_json(path, empty)
                result = change(value)
                if file_stamp(path) != before:  # an editor saved it meanwhile: keep theirs
                    raise Unreadable("%s changed while Scout was updating it; nothing was overwritten, try again"
                                     % path)
                write_atomic(path, value)
                return result
        except BlockingIOError:
            time.sleep(0.05)
        except OSError as error:
            raise Unreadable("couldn't lock %s: %s" % (path, error.strerror or error)) from error
    raise Unreadable("another Scout is updating %s; try again" % path)


def settings(value: dict) -> dict:
    if value and value.get("schema") != 1:
        raise Unreadable("card settings have an unknown schema, kept as they are: %s" % (folder() / "settings.json"))
    value.setdefault("schema", 1)
    value.setdefault("cards", "on")
    value.setdefault("channel", None)
    return value


def now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def month_of(moment: datetime.datetime) -> str:
    return moment.strftime("%Y-%m")


def previous_month(moment: datetime.datetime) -> str:
    return month_of(moment.replace(day=1) - datetime.timedelta(days=1))


def scout_version() -> str:
    try:
        version = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError):
        version = None
    return version if isinstance(version, str) and re.fullmatch(r"\d+\.\d+\.\d+", version) else "unknown"


def task_hash(task: str) -> str:
    return hashlib.sha256(os.path.normcase(os.path.realpath(task)).encode("utf-8")).hexdigest()


# --- cards ------------------------------------------------------------------------------------------------------

def products_from(raw) -> list:
    products = json.loads(raw) if isinstance(raw, str) else raw or []
    if not isinstance(products, list) or any(product not in PRODUCTS for product in products):
        raise Refused("products come from this list only: " + ", ".join(PRODUCTS))
    return [product for product in PRODUCTS if product in products]


def new_card(record: dict, host: str, logbook: bool, products: list, created: datetime.datetime,
             card_id: str) -> dict:
    dispositions = dict.fromkeys(DISPOSITIONS, 0)
    built = {}
    for item in record["items"]:
        disposition = item.get("disposition")
        dispositions[disposition if disposition in DISPOSITIONS else "unverified"] += 1
        kind = category(item["type"])
        built[kind] = built.get(kind, 0) + 1
    return {"schema": 1, "card_id": card_id, "created_at": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "scout_version": scout_version(), "host": host, "state": "offered", "rating": None, "time_saved": None,
            "categories": {name: built[name] for name in ORDER if name in built}, "products": products,
            "dispositions": dispositions, "logbook": bool(logbook), "comment": None, "previewed": None}


def matches(pattern: str, value) -> bool:
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def valid_time(saved) -> bool:
    if saved is None:
        return True
    if not isinstance(saved, dict) or saved.get("kind") not in KINDS or not set(saved) <= {"kind", "hours"}:
        return False
    if "hours" not in saved:
        return saved["kind"] != "hours"
    hours = saved["hours"]
    return saved["kind"] in ("hours", "time_lost") and type(hours) in (int, float) and 0 < hours <= 200


def counts(value, names) -> bool:
    return isinstance(value, dict) and all(name in names and type(count) is int and count >= 0
                                           for name, count in value.items())


def valid_preview(seen) -> bool:
    """What the builder was last shown: the post's digest and the channel it would go to."""
    return seen is None or (isinstance(seen, dict) and set(seen) == {"text", "channel"}
                            and matches(r"[0-9a-f]{16}", seen["text"])
                            and (seen["channel"] is None or matches(r"#[a-z0-9][a-z0-9._-]{0,79}", seen["channel"])))


def valid(card) -> bool:
    """The fixed schema, so the summary counts only cards it can read the same way."""
    if not isinstance(card, dict) or set(card) != CARD_KEYS:
        return False
    comment = card["comment"]
    return all((
        card["schema"] == 1 and type(card["schema"]) is int,
        matches(r"c-[0-9a-f]{6}", card["card_id"]),
        matches(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", card["created_at"]),
        matches(r"\d+\.\d+\.\d+|unknown", card["scout_version"]),
        card["host"] in HOSTS, card["state"] in STATES, card["rating"] in (None, *RATINGS),
        valid_time(card["time_saved"]),
        counts(card["categories"], ORDER),
        isinstance(card["products"], list) and all(name in PRODUCTS for name in card["products"]),
        counts(card["dispositions"], DISPOSITIONS) and set(card["dispositions"]) == set(DISPOSITIONS),
        type(card["logbook"]) is bool,
        comment is None or (isinstance(comment, str) and len(comment) <= COMMENT_LIMIT),
        valid_preview(card["previewed"]),
    ))


def comment_problem(comment: str):
    """Why the builder's words can't go on the card: the obvious identifiers. The model checks the rest first."""
    if len(comment) > COMMENT_LIMIT:
        return "a comment is at most %d characters" % COMMENT_LIMIT
    if unseen(comment):
        return "the comment contains characters a reader can't see"
    if EMAIL.search(comment):
        return "the comment contains an email address"
    if ORG_URL.search(comment):
        return "the comment contains an org address"
    for token in TOKEN.findall(comment):
        if re.match(r"(?:0|a\d)", token) and sum(character.isdigit() for character in token) >= 3:
            return "the comment contains what looks like a Salesforce record or org ID"
    return None


def card_text(card: dict) -> str:
    """The post, from the card's fixed fields and the builder's own answers: what was built, what Scout's
    read-backs found, and the builder's words. Nothing else."""
    items = sum(card["dispositions"].values())
    built = ", ".join("%s %d" % (name, card["categories"][name]) for name in ORDER if card["categories"].get(name))
    checked = ", ".join("%d %s" % (card["dispositions"][name], CHECKED_WORDS[name]) for name in DISPOSITIONS
                        if card["dispositions"].get(name))
    parts = ["Scout build card: %d task item%s%s." % (items, "" if items == 1 else "s",
                                                     " (%s)" % built if built else ""),
             "Scout's checks: %s." % (checked or "none")]
    if card["products"]:
        parts.append("Products: %s." % ", ".join(card["products"]))
    if card["logbook"]:
        parts.append("Built through a shared logbook.")
    saved = card["time_saved"]
    if saved:
        hours = saved.get("hours")
        parts.append({"hours": "Time saved, my estimate: about %g hours." % (hours or 0),
                      "unknown": "Time saved: I can't say.", "none": "Time saved: none.",
                      "time_lost": "It cost me time" + (", about %g hours." % hours if hours else ".")}[saved["kind"]])
    if card["rating"]:
        parts.append("How it went: %s." % {"good": "good", "ok": "OK", "poor": "poor"}[card["rating"]])
    if card["comment"]:
        parts.append("In my words: \u201c%s\u201d" % card["comment"])
    if card["host"] in HOST_NAMES:
        parts.append("(Scout %s on %s)" % (card["scout_version"], HOST_NAMES[card["host"]]))
    return " ".join(parts)


def card_slot(key: str, moment: datetime.datetime) -> str:
    """The task's card file. It goes into the index before the card is written, so an interrupted save can never
    give a task a second card: the next handover writes the card at the same place."""
    def change(index):
        if index and index.get("schema") != 1:
            raise Unreadable("the card index has an unknown schema, kept as it is")
        index.setdefault("schema", 1)
        tasks = index.setdefault("tasks", {})
        if not isinstance(tasks, dict):
            raise Unreadable("the card index is malformed, kept as it is")
        if not (isinstance(tasks.get(key), str) and SLOT.match(tasks[key])):
            tasks[key] = "cards/%s/card-%s-%s.json" % (month_of(moment), moment.strftime("%Y%m%d-%H%M"),
                                                       secrets.token_hex(3))
        return tasks[key]
    return mutate(folder() / "index.json", {}, change)


def card_path(task: str) -> Path:
    index = read_json(folder() / "index.json", {})
    relative = index.get("tasks", {}).get(task_hash(task)) if isinstance(index.get("tasks"), dict) else None
    path = folder() / relative if isinstance(relative, str) and SLOT.match(relative) else None
    if path is None or not path.exists():
        raise Refused("this task has no card")
    return path


def read_card(path: Path) -> dict:
    card = read_json(path, {})
    if not valid(card):
        raise Unreadable("the card is malformed, kept as it is: %s" % path.name)
    return card


# --- subcommands ------------------------------------------------------------------------------------------------

def cmd_cards(args) -> dict:
    def change(value):
        settings(value)["cards"] = args.switch
        return value["cards"]
    return {"cards": mutate(folder() / "settings.json", {}, change)}


def cmd_channel(args) -> dict:
    if args.clear:
        channel = None
    else:
        match = CHANNEL.match((args.set or "").strip())
        if not match:
            raise Refused("a Slack channel name is lower case letters, digits, dots, hyphens or underscores")
        channel = "#" + match[1]

    def change(value):
        settings(value)["channel"] = channel
        return channel
    return {"channel": mutate(folder() / "settings.json", {}, change)}


def cmd_settings(args) -> dict:
    return settings(read_json(folder() / "settings.json", {}))


def cmd_handover(args) -> dict:
    """The lines the handover ends with. With cards on, the task's card is saved first, then shown as it would be
    posted, with the share question."""
    choice = settings(read_json(folder() / "settings.json", {}))
    if choice["cards"] != "on":
        return {"lines": [], "card": None}
    products = products_from(args.products)
    try:
        record = scout_history.task_record(Path(args.task))
    except (OSError, UnicodeError, scout_history.BlockError, ValueError) as error:
        return {"lines": [], "card": None, "reason": "no card: the task record couldn't be read (%s)" % str(error)[:160]}
    moment = now()
    relative = card_slot(task_hash(args.task), moment)
    path = folder() / relative
    if path.exists():
        return {"lines": [], "card": {"state": "existing", "file": relative}}
    card = new_card(record, args.host, args.logbook, products, moment, "c-" + relative[-11:-5])
    card["previewed"] = {"text": digest(card_text(card)), "channel": choice["channel"]}
    try:
        write_atomic(path, card, exclusive=True)
    except FileExistsError:  # another session for this task wrote it a moment ago
        return {"lines": [], "card": {"state": "existing", "file": relative}}
    where = choice["channel"] or "a Slack channel (name it, and Scout remembers it)"
    return {"card": {"state": "offered", "card_id": card["card_id"]}, "channel": choice["channel"],
            "lines": ["Build card, as it would be posted: " + card_text(card),
                      "Share it in %s? Reply `share`, adding a line on how it went and, if you like, your own estimate "
                      "of the time it saved. Without a `share` it stays on this machine; `/scout cards off` stops "
                      "these cards." % where]}


def cmd_answer(args) -> dict:
    if args.rating is None and args.time_kind is None and args.comment is None and args.products is None:
        raise Refused("an answer gives a rating, a time answer, a comment or products")
    time_saved = None
    if args.time_kind is not None:
        if args.time_kind == "hours" and args.hours is None:
            raise Refused("an hours answer names the hours")
        if args.hours is not None and (args.time_kind not in ("hours", "time_lost") or not 0 < args.hours <= 200):
            raise Refused("hours go with \"hours\" or \"time_lost\", between a moment and 200")
        time_saved = {"kind": args.time_kind, **({"hours": args.hours} if args.hours is not None else {})}
    comment = " ".join(args.comment.split()) if args.comment else None
    if comment and comment_problem(comment):
        raise Refused(comment_problem(comment) + ": ask the builder to rephrase it, or save the card without it")
    products = products_from(args.products) if args.products is not None else None
    path = card_path(args.task)

    def change(card):
        if not valid(card):
            raise Unreadable("the card is malformed, kept as it is: %s" % path.name)
        if args.rating is not None:
            card["rating"] = args.rating
        if time_saved is not None:
            card["time_saved"] = time_saved
        if comment is not None:
            card["comment"] = comment
        if products is not None:
            card["products"] = products
        if card["state"] == "offered":
            card["state"] = "answered"
        return {"card_id": card["card_id"], "state": card["state"], "text": card_text(card)}

    return mutate(path, {}, change)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def channel_setting():
    return settings(read_json(folder() / "settings.json", {}))["channel"]


def post_digest(text: str, channel) -> str:
    """The post as approved: its exact text and the channel it goes to."""
    return hashlib.sha256(("%s\n%s" % (channel or "", text)).encode("utf-8")).hexdigest()[:16]


def cmd_share_text(args) -> dict:
    """The exact post, its channel and their digest, and whether each still matches the handover's preview. It
    writes nothing: the flags compare content with what the handover showed; they don't prove the builder saw it."""
    card = read_card(card_path(args.task))
    if card["state"] == "shared":
        raise Refused("this card was shared already; one post per card")
    if card["state"] == "posting":
        raise Refused("a post of this card may already be in %s: ask the builder to check. If it isn't there, "
                      "`not-posted` frees the card" % ((card["previewed"] or {}).get("channel") or "the channel"))
    channel = channel_setting()
    post, seen = card_text(card), card["previewed"] or {}
    return {"text": post, "channel": channel, "digest": post_digest(post, channel), "state": card["state"],
            "text_shown": seen.get("text") == digest(post),
            "channel_shown": channel is not None and seen.get("channel") == channel}


def cmd_posting(args) -> dict:
    """Right before the host's Slack tool sends the card: mark it as being posted, so a session that stops after
    the send can never post it again unasked. Only the text and channel the builder approved can go out: their
    digest, from `share-text`, must match the card as it is now."""
    path, channel = card_path(args.task), channel_setting()

    def change(card):
        if not valid(card):
            raise Unreadable("the card is malformed, kept as it is: %s" % path.name)
        if card["state"] not in ("offered", "answered"):
            raise Refused("this card is %s; only an unposted card can be posted" % card["state"])
        if not channel:
            raise Refused("no channel is saved: ask the builder where to share it, then run `channel --set`")
        post = card_text(card)
        if args.digest != post_digest(post, channel):
            raise Refused("this isn't the text and channel the builder approved: run `share-text`, show the builder "
                          "its text and channel, and post with its digest after their yes")
        card["state"] = "posting"
        return {"text": post, "channel": channel}

    return mutate(path, {}, change)


def settle(task, outcome):
    path = card_path(task)

    def change(card):
        if not valid(card):
            raise Unreadable("the card is malformed, kept as it is: %s" % path.name)
        if card["state"] != "posting":
            raise Refused("this card isn't being posted (it's %s)" % card["state"])
        answered = card["rating"] or card["time_saved"] or card["comment"]
        card["state"] = "shared" if outcome == "shared" else "answered" if answered else "offered"
        return card["state"]

    return {"state": mutate(path, {}, change)}


def cmd_shared(args) -> dict:
    """The host's Slack tool confirmed the post."""
    return settle(args.task, "shared")


def cmd_not_posted(args) -> dict:
    """The send failed, or the builder checked the channel and the post isn't there: the card is free again."""
    return settle(args.task, "not-posted")


def cmd_summary(args) -> dict:
    month = args.month or previous_month(now())
    if not MONTH.match(month):
        raise Refused("a month is YYYY-MM")
    cards, invalid = [], []
    directory = folder() / "cards" / month
    for path in sorted(directory.glob("*.json")) if directory.is_dir() else []:
        try:
            card = read_json(path, {})
        except Unreadable:
            card = None
        if CARD_FILE.match(path.name) and valid(card) and card["created_at"].startswith(month):
            cards.append(card)
        else:
            invalid.append(path.name)
    answered = [card for card in cards if card["state"] in ("answered", "posting", "shared")]
    ratings = {rating: sum(card["rating"] == rating for card in cards) for rating in RATINGS}
    kinds = {kind: sum((card["time_saved"] or {}).get("kind") == kind for card in cards) for kind in KINDS}
    hours = [card["time_saved"]["hours"] for card in cards if (card["time_saved"] or {}).get("kind") == "hours"]
    dispositions = {name: sum(card["dispositions"][name] for card in cards) for name in DISPOSITIONS}
    built = {name: sum(card["categories"].get(name, 0) for card in cards) for name in ORDER}
    products = {name: sum(name in card["products"] for card in cards) for name in PRODUCTS}
    tally = lambda field: {value: sum(card[field] == value for card in cards)
                           for value in sorted({card[field] for card in cards})}
    total = {"cards": len(cards), "answered": len(answered), "unanswered": len(cards) - len(answered),
             "shared": sum(card["state"] == "shared" for card in cards), "ratings": ratings, "time_answers": kinds,
             "hours_sum": round(sum(hours), 2), "hours_median": round(statistics.median(hours), 2) if hours else None,
             "hours_answers": len(hours), "dispositions": dispositions,
             "logbook": sum(card["logbook"] for card in cards), "hosts": tally("host"),
             "versions": tally("scout_version"), "built": {name: n for name, n in built.items() if n},
             "products": {name: n for name, n in products.items() if n}}
    listing = lambda values: ", ".join("%s %d" % pair for pair in values.items()) or "none"
    lines = ["Scout build-card summary, %s. Counts only, from the builder's own cards." % month,
             "Cards: %d offered, %d answered (%d shared), %d unanswered." % (
                 total["cards"], total["answered"], total["shared"], total["unanswered"]),
             "Ratings: good %d, OK %d, poor %d." % (ratings["good"], ratings["ok"], ratings["poor"])]
    if hours:
        lines.append("Respondent-estimated time saved: %g hours in total, median %g hours, over %d hour answers."
                     % (total["hours_sum"], total["hours_median"], len(hours)))
    else:
        lines.append("Respondent-estimated time saved: no hour answers.")
    lines += ["Other time answers: unknown %d, none %d, it cost time %d." % (kinds["unknown"], kinds["none"],
                                                                             kinds["time_lost"]),
              "Scout's checked results (its read-backs, not demo outcomes): %s." % ", ".join(
                  "%s %d" % (CHECKED_WORDS[name], count) for name, count in dispositions.items()),
              "Tasks through a shared logbook: %d of %d." % (total["logbook"], total["cards"]),
              "Task items by category: %s." % listing(total["built"]), "Products: %s." % listing(total["products"]),
              "Hosts: %s. Scout versions: %s." % (listing(total["hosts"]), listing(total["versions"]))]
    return {"month": month, "text": "\n".join(lines), "counts": total, "invalid_cards": invalid}


# --- the command line -------------------------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    cards = commands.add_parser("cards")
    cards.add_argument("switch", choices=("on", "off"))
    channel = commands.add_parser("channel")
    choice = channel.add_mutually_exclusive_group(required=True)
    choice.add_argument("--set")
    choice.add_argument("--clear", action="store_true")
    commands.add_parser("settings")
    handover = commands.add_parser("handover")
    handover.add_argument("--task", required=True)
    handover.add_argument("--host", required=True, choices=HOSTS)
    handover.add_argument("--logbook", action="store_true", help="the task went through a shared logbook")
    handover.add_argument("--products", help="the model's proposal, a JSON list from the fixed list")
    answer = commands.add_parser("answer")
    answer.add_argument("--task", required=True)
    answer.add_argument("--rating", choices=RATINGS)
    answer.add_argument("--time-kind", choices=KINDS)
    answer.add_argument("--hours", type=float)
    answer.add_argument("--comment")
    answer.add_argument("--products")
    for name in ("share-text", "posting", "shared", "not-posted"):
        commands.add_parser(name).add_argument("--task", required=True)
    commands.choices["posting"].add_argument("--digest", required=True, help="from `share-text`, for the text "
                                                                              "the builder approved")
    summary = commands.add_parser("summary")
    summary.add_argument("--month")
    args = parser.parse_args(argv)
    try:
        payload = globals()["cmd_" + args.command.replace("-", "_")](args)
    except Refused as error:
        print(json.dumps({"reason": str(error)}, ensure_ascii=False))
        return 3
    except Unreadable as error:
        print(json.dumps({"reason": str(error)}, ensure_ascii=False))
        return 4
    except json.JSONDecodeError:
        print(json.dumps({"reason": "a JSON argument is malformed"}))
        return 2
    print(json.dumps(payload, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    scout_portable.utf8_output()
    raise SystemExit(main())
