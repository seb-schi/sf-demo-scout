#!/usr/bin/env python3
"""Scout's read-only access to the knowledge Salesforce product teams publish on GitHub, such as an industry
cloud's setup notes, data model and troubleshooting.

The ledger (`assets/industry-sources.json`) names each source's exact repo, the commit the maintainer reviewed and the
paths worth reading. The generated index (`assets/industry-sources-index.json`) lists every file under those paths at
that commit, with its Git blob SHA. At task time this helper serves only those files: from a raw GitHub URL that names
the commit, checked against the blob SHA, and cached per commit. It never calls the GitHub API at task time, never
follows a redirect, and never executes, imports or evaluates what it fetches; the files are data. Only `build-index`,
the maintainer's review step, writes the index, through the maintainer's authenticated `gh`. Nothing here installs,
builds or runs anything from upstream."""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "assets" / "industry-sources.json"
INDEX = ROOT / "assets" / "industry-sources-index.json"
# Salesforce-owned GitHub orgs a ledger repo may come from. An org on this list grants nothing by itself: only the exact
# repos the ledger names are read, at the commits it names.
OWNERS = frozenset(owner.lower() for owner in (
    "salesforce", "SalesforceLabs", "salesforce-misc", "forcedotcom", "SalesforceCommerceCloud", "SalesforceAIResearch",
    "heroku", "slackapi", "tableau", "mulesoft"))
TEXT_SUFFIXES = (".md", ".yaml", ".yml", ".json", ".mermaid", ".txt")
MAX_FILE = 1024 * 1024  # bytes per file
MAX_FILES = 40  # files per fetch
TIMEOUT = 30  # seconds per download
RAW = "https://raw.githubusercontent.com/{repo}/{commit}/{path}"
SOURCE_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,40}")
REPO = re.compile(r"([A-Za-z0-9][A-Za-z0-9-]{0,38})/([A-Za-z0-9._-]{1,100})")
SHA = re.compile(r"[0-9a-f]{40}")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class Refused(Exception):
    """A policy refusal, or a ledger or index that disagrees with itself: final, never retried another way."""


class HttpFailure(Exception):
    """GitHub answered with something other than the file: final."""


class TransportFailure(Exception):
    """No usable answer (network, TLS, timeout, a cut-off body): the other transport may try once."""


def clean_path(text):
    """A relative POSIX path (a trailing slash marks a prefix) with no empty, `.` or `..` segment; else None."""
    if not isinstance(text, str) or not text or text.startswith("/") or "\\" in text or "\0" in text:
        return None
    body = text[:-1] if text.endswith("/") else text
    if not body or any(part in ("", ".", "..") for part in body.split("/")):
        return None
    return text


def covered(path, prefixes):
    return any(path.startswith(prefix) if prefix.endswith("/") else path == prefix for prefix in prefixes)


def unique_keys(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("duplicate key %s" % key)  # a copy-pasted ledger or index entry
        data[key] = value
    return data


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique_keys)
    except (OSError, ValueError, UnicodeError):
        raise Refused("%s unreadable" % Path(path).name) from None


def text_field(entry, key):
    value = entry.get(key)
    return isinstance(value, str) and bool(value.strip())


def check_entry(ident, entry):
    if not SOURCE_ID.fullmatch(ident) or not isinstance(entry, dict):
        raise Refused("ledger entry %r malformed" % ident)
    match = REPO.fullmatch(entry.get("repo") if isinstance(entry.get("repo"), str) else "")
    if not match or match.group(1).lower() not in OWNERS:
        raise Refused("%s: repo isn't from a Salesforce-owned org on the allowlist" % ident)
    if not text_field(entry, "cloud"):
        raise Refused("%s: no cloud" % ident)
    if entry.get("state") == "known":
        if not text_field(entry, "why") or any(key in entry for key in ("commit", "paths")):
            raise Refused("%s: a known entry has a reason and no commit or paths" % ident)
    elif entry.get("state") == "read":
        paths = entry.get("paths")
        org_wide = entry.get("org_wide")
        if not (isinstance(entry.get("commit"), str) and SHA.fullmatch(entry["commit"])
                and isinstance(entry.get("reviewed"), str) and DATE.fullmatch(entry["reviewed"])
                and isinstance(paths, list) and paths and all(clean_path(p) for p in paths)
                and text_field(entry, "shape") and text_field(entry, "use")
                and isinstance(org_wide, list) and all(isinstance(s, str) and s.strip() for s in org_wide)):
            raise Refused("%s: a read entry needs a full commit, a review date, clean paths, shape, use and org_wide"
                          % ident)
    else:
        raise Refused("%s: state is neither read nor known" % ident)


def ledger(path=None):
    """The validated ledger's sources. A malformed ledger serves nothing."""
    data = load_json(path or LEDGER)
    if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("sources"), dict):
        raise Refused("ledger schema")
    for ident, entry in data["sources"].items():
        check_entry(ident, entry)
    return data["sources"]


def read_entry(ident, sources):
    entry = sources.get(ident)
    if entry is None:
        raise Refused("unknown source %s" % ident)
    if entry["state"] != "read":
        raise Refused("%s is listed as known, not read: %s" % (ident, entry["why"]))
    return entry


def files_for(ident, sources, index_path=None):
    """One read source's file table, {path: {"sha", "size"}}, after checking the index against the ledger: the same repo
    and full commit, every path inside the ledger's paths, text only, a valid blob SHA and size. Any disagreement serves
    nothing, and nothing at task time rewrites the index."""
    entry = read_entry(ident, sources)
    data = load_json(index_path or INDEX)
    table = data.get("sources") if isinstance(data, dict) and data.get("schema") == 1 else None
    item = table.get(ident) if isinstance(table, dict) else None
    if not isinstance(item, dict):
        raise Refused("%s has no reviewed index" % ident)
    if item.get("repo") != entry["repo"] or item.get("commit") != entry["commit"]:
        raise Refused("%s: the index is for another repo or commit than the ledger" % ident)
    files = item.get("files")
    if not isinstance(files, dict) or not files:
        raise Refused("%s: the index lists no files" % ident)
    for path, meta in files.items():
        if not (clean_path(path) and not path.endswith("/") and path.endswith(TEXT_SUFFIXES)
                and covered(path, entry["paths"])):
            raise Refused("%s: the index lists %s, outside the ledger's paths" % (ident, path))
        if not (isinstance(meta, dict) and SHA.fullmatch(str(meta.get("sha") or ""))
                and isinstance(meta.get("size"), int) and 0 <= meta["size"] <= MAX_FILE):
            raise Refused("%s: the index entry for %s is malformed" % (ident, path))
    return entry, files


def blob_sha(data):
    """Git's blob ID for these bytes: what the tree at the reviewed commit records for the file."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def cache_root():
    """The same root as `scout_metadata_experts`: SCOUT_CACHE_DIR moves it, and changes nothing about what's served."""
    return Path(os.environ.get("SCOUT_CACHE_DIR") or Path.home() / ".cache" / "sf-demo-scout")


def cache_file(entry, path):
    owner, name = entry["repo"].split("/")
    return cache_root().joinpath("industry", "%s__%s" % (owner, name), entry["commit"], *path.split("/"))


def write_atomic(target, data):
    """Publish the bytes whole or not at all; a failed write leaves no partial file behind."""
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=target.parent, prefix=".partial-", delete=False)
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, target)
    except BaseException:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # urllib then raises the 3xx as an HTTPError


def via_urllib(url, cap=MAX_FILE, timeout=TIMEOUT, scheme="https"):
    if not url.startswith(scheme + "://"):
        raise Refused("not an %s URL" % scheme)
    opener = urllib.request.build_opener(NoRedirect)
    request = urllib.request.Request(url, headers={"User-Agent": "sf-demo-scout"})
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.status != 200:
                raise HttpFailure("HTTP %d" % response.status)
            data = response.read(cap + 1)
            declared = response.headers.get("Content-Length", "")
            if declared.isdigit() and int(declared) != len(data) and len(data) <= cap:
                raise TransportFailure("the body was cut off")  # a bounded read returns short bodies silently
    except urllib.error.HTTPError as error:
        if 300 <= error.code < 400:
            raise Refused("redirected (HTTP %d); the source may have moved" % error.code) from None
        raise HttpFailure("HTTP %d" % error.code) from None
    except (urllib.error.URLError, OSError, http.client.HTTPException) as error:  # network, TLS, timeout, cut-off body
        raise TransportFailure(type(error).__name__) from None
    if len(data) > cap:
        raise Refused("larger than %d bytes" % cap)
    return data


def via_curl(url, cap=MAX_FILE, timeout=TIMEOUT, proto="=https"):
    """curl uses the system trust store, which a machine's Python may lack (a corporate CA). `-q` must come first, so
    no `.curlrc` can add redirects or outputs; there's no `-L`."""
    curl = shutil.which("curl")
    if not curl:
        raise TransportFailure("curl not found")
    with tempfile.TemporaryDirectory(prefix="scout-industry-") as folder:
        body = Path(folder) / "body"
        command = [curl, "-q", "--silent", "--show-error", "--fail", "--proto", proto, "--max-time", str(timeout),
                   "--max-filesize", str(cap), "--output", str(body), "--write-out", "%{http_code}", url]
        try:
            result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                    errors="replace", timeout=timeout + 10)  # curl's messages may not be UTF-8
        except (OSError, subprocess.SubprocessError) as error:
            raise TransportFailure(type(error).__name__) from None
        code = result.stdout.strip()[-3:]
        if code.startswith("3"):
            raise Refused("redirected (HTTP %s); the source may have moved" % code)
        if result.returncode == 63:
            raise Refused("larger than %d bytes" % cap)
        if result.returncode == 22 or (code.isdigit() and code not in ("000", "200")):
            raise HttpFailure("HTTP %s" % code)
        if result.returncode != 0 or code != "200" or not body.is_file():
            raise TransportFailure("curl exit %d" % result.returncode)
        data = body.read_bytes()
    if len(data) > cap:
        raise Refused("larger than %d bytes" % cap)
    return data


def download(url, cap=MAX_FILE):
    """urllib first; only a transport failure falls back to curl. Refusals and HTTP failures are final."""
    try:
        return via_urllib(url, cap)
    except TransportFailure:
        return via_curl(url, cap)


def cached(target, sha):
    try:
        data = target.read_bytes()
    except OSError:
        return None
    return data if blob_sha(data) == sha else None  # an edited or partial cache file is refetched


def fetch(ident, paths, sources, index_path=None, downloader=None):
    """(token lines, exit code) for these paths of one read source. Every path is checked before anything downloads."""
    entry, files = files_for(ident, sources, index_path)
    if not paths:
        raise Refused("no path given")
    if len(paths) > MAX_FILES:
        raise Refused("more than %d files in one call" % MAX_FILES)
    for path in paths:
        if path not in files:
            raise Refused("%s isn't in %s's reviewed index" % (path, ident))
    lines, worst = [], 0
    for path in paths:
        meta, target = files[path], cache_file(entry, path)
        if cached(target, meta["sha"]) is not None:
            lines.append("INDUSTRY_FILE %s" % target)
            continue
        url = RAW.format(repo=entry["repo"], commit=entry["commit"], path=urllib.parse.quote(path))
        try:
            data = (downloader or download)(url, MAX_FILE)
            if blob_sha(data) != meta["sha"]:
                raise HttpFailure("the content doesn't match the reviewed commit")
            write_atomic(target, data)
        except Refused as error:
            lines.append("INDUSTRY_SOURCE_REFUSED %s %s: %s" % (ident, path, error))
            worst = max(worst, 2)
            continue
        except (HttpFailure, TransportFailure, OSError) as error:
            lines.append("INDUSTRY_SOURCE_UNREACHABLE %s %s: %s" % (ident, path, str(error) or type(error).__name__))
            worst = max(worst, 3)
            continue
        lines.append("INDUSTRY_FILE %s" % target)
    return lines, worst


def build_index(ident, sources, index_path=None, gh=None):
    """The maintainer's step: list the files under the ledger's paths at its commit, with blob SHAs, from the
    authenticated GitHub tree. It refuses a truncated tree or a path that matches nothing, and replaces the index
    atomically, so a failure keeps the old one. Returns the number of files."""
    entry = read_entry(ident, sources)
    gh = gh or shutil.which("gh")
    if not gh:
        raise Refused("build-index needs the maintainer's authenticated gh")
    try:
        result = subprocess.run([gh, "api", "repos/%s/git/trees/%s?recursive=1" % (entry["repo"], entry["commit"])],
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
        tree = json.loads(result.stdout) if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        tree = None
    if not isinstance(tree, dict) or not isinstance(tree.get("tree"), list):
        raise Refused("%s: the tree at %s couldn't be read" % (ident, entry["commit"]))
    if tree.get("truncated") is not False:
        raise Refused("%s: GitHub returned a truncated tree" % ident)
    files = {}
    for node in tree["tree"]:
        path = node.get("path") if isinstance(node, dict) else None
        if not isinstance(node, dict) or node.get("type") != "blob" or node.get("mode") == "120000" \
                or not clean_path(path) or not path.endswith(TEXT_SUFFIXES) or not covered(path, entry["paths"]):
            continue  # folders, submodules and symlinks (a link's raw text isn't its target's content) never count
        if not SHA.fullmatch(str(node.get("sha") or "")) or not isinstance(node.get("size"), int):
            raise Refused("%s: the tree entry for %s is malformed" % (ident, path))
        if node["size"] > MAX_FILE:
            raise Refused("%s: %s is larger than %d bytes; narrow the ledger's paths" % (ident, path, MAX_FILE))
        files[path] = {"sha": node["sha"], "size": node["size"]}
    unmatched = [p for p in entry["paths"] if not any(covered(f, [p]) for f in files)]
    if unmatched:
        raise Refused("%s: ledger paths match no text file at the commit: %s" % (ident, ", ".join(unmatched)))
    target = Path(index_path or INDEX)
    current = load_json(target) if target.exists() else {"schema": 1, "sources": {}}
    table = current.get("sources") if isinstance(current, dict) else None
    if not isinstance(table, dict):
        raise Refused("the existing index is malformed; fix or remove it first")
    kept = {key: value for key, value in table.items() if key != ident and sources.get(key, {}).get("state") == "read"}
    kept[ident] = {"repo": entry["repo"], "commit": entry["commit"], "files": dict(sorted(files.items()))}
    try:
        write_atomic(target, (json.dumps({"schema": 1, "sources": kept}, indent=1, sort_keys=True) + "\n").encode())
    except OSError as error:
        raise Refused("couldn't write the index (%s); the previous index is unchanged" % error) from None
    return len(files)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="every source: id, cloud, state, and its use note or why it isn't read")
    sub = commands.add_parser("show", help="one read source's full entry")
    sub.add_argument("source")
    sub = commands.add_parser("index", help="a read source's reviewed file paths")
    sub.add_argument("source")
    sub.add_argument("--under", default="", help="only paths under this prefix")
    sub = commands.add_parser("fetch", help="fetch reviewed files into the cache and print their local paths")
    sub.add_argument("source")
    sub.add_argument("paths", nargs="+")
    sub = commands.add_parser("build-index", help="maintainer only: regenerate one source's index at its commit")
    sub.add_argument("source")
    args = parser.parse_args(argv)
    try:
        sources = ledger()
        if args.command == "list":
            print(json.dumps([{"id": key, "cloud": e["cloud"], "state": e["state"],
                               **({"use": e["use"]} if e["state"] == "read" else {"why": e["why"]})}
                              for key, e in sources.items()], ensure_ascii=False))
        elif args.command == "show":
            entry = read_entry(args.source, sources)
            files_for(args.source, sources)  # a source whose index disagrees isn't offered at all
            print(json.dumps({"id": args.source, **{k: entry[k] for k in ("cloud", "repo", "commit", "reviewed",
                                                                         "shape", "paths", "use", "org_wide")}},
                             ensure_ascii=False))
        elif args.command == "index":
            entry, files = files_for(args.source, sources)
            print(json.dumps({"id": args.source, "repo": entry["repo"], "commit": entry["commit"],
                              "files": sorted(p for p in files if p.startswith(args.under))}, ensure_ascii=False))
        elif args.command == "fetch":
            lines, code = fetch(args.source, args.paths, sources)
            print("\n".join(lines))
            return code
        else:
            print("INDUSTRY_INDEX_BUILT %s %d files" % (args.source, build_index(args.source, sources)))
    except Refused as error:
        print("INDUSTRY_SOURCE_REFUSED %s" % error)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
