#!/usr/bin/env python3
"""
Regenerates community-profiles/index.json from whatever profile .json files
are actually in that folder. Run this after adding, editing, or removing a
community profile, before committing -- index.json is a generated manifest,
never hand-edited, so it can't drift out of sync with the real files.

The app's Community tab fetches only this small index.json first (to render
the card grid) and fetches an individual profile's full file only when the
user actually downloads it -- so this script keeps that manifest to just the
fields ProfileCard needs, not a copy of every tag.
"""
import json
import sys
from pathlib import Path

COMMUNITY_DIR = Path(__file__).resolve().parent.parent / "community-profiles"
INDEX_PATH = COMMUNITY_DIR / "index.json"
INDEX_FILE_VERSION = 1


def build_index():
    entries = []
    errors = []

    for path in sorted(COMMUNITY_DIR.glob("*.json")):
        if path.name == "index.json":
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            errors.append(f"{path.name}: unreadable/invalid JSON ({e})")
            continue

        if not isinstance(data, dict):
            errors.append(f"{path.name}: top level is not a JSON object")
            continue

        name = str(data.get("name", "")).strip()
        if not name:
            errors.append(f"{path.name}: missing required 'name' field")
            continue

        tags = data.get("tags")
        if not isinstance(tags, list):
            errors.append(f"{path.name}: missing/invalid 'tags' list")
            continue

        entries.append({
            "file": path.name,
            "name": name,
            "manufacturer": str(data.get("manufacturer", "")).strip(),
            "type": str(data.get("type", "")).strip(),
            "author": str(data.get("author", "")).strip(),
            "tag_count": len(tags),
            "created": data.get("created") or data.get("modified") or "",
        })

    entries.sort(key=lambda e: e["name"].lower())

    index = {"version": INDEX_FILE_VERSION, "profiles": entries}
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)
        f.write("\n")

    print(f"Wrote {INDEX_PATH} with {len(entries)} profile(s).")
    if errors:
        print("\nSkipped file(s) with problems:")
        for e in errors:
            print(f"  - {e}")
    return not errors


if __name__ == "__main__":
    sys.exit(0 if build_index() else 1)
