import json, os, tempfile

FIX = {
    "mcp__Salesforce_DX__*":   "mcp__plugin_sf-demo-scout_Salesforce_DX__*",
    "mcp__Salesforce_Docs__*": "mcp__plugin_sf-demo-scout_Salesforce_Docs__*",
}
TARGETS = [
    os.path.expanduser("~/claude-projects/sf-demo-scout/.claude/settings.json"),
    os.path.expanduser("~/.claude/settings.json"),
]

total = 0
for path in TARGETS:
    if not os.path.exists(path):
        continue
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"MCP_PREFIX_SKIP {os.path.basename(path)}: {e}")
        continue
    if not isinstance(data, dict):
        continue
    perms = data.get("permissions")
    if not isinstance(perms, dict):
        continue

    changed = 0
    for key in ("allow", "deny", "ask"):
        lst = perms.get(key)
        if not isinstance(lst, list):
            continue
        out = []
        for entry in lst:
            new = FIX.get(entry, entry)
            if new != entry:
                changed += 1
            if new not in out:
                out.append(new)
        perms[key] = out

    if not changed:
        continue
    try:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".settings.", suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
        total += changed
        print(f"MCP_PREFIX_FIXED {os.path.basename(path)}: {changed}")
    except Exception as e:
        print(f"MCP_PREFIX_WRITE_FAILED {os.path.basename(path)}: {e}")

if total == 0:
    print("MCP_PREFIX_OK")
