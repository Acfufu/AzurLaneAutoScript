#!/usr/bin/env python3
"""R1 red line: upstream edits landing on campaign .py files whose map layer
this fork moved out of .py (into YAML + ``.legacy_snapshot``).

Why this exists: static-chapter ``campaign/**/*.py`` files are 11-line
battle-logic stubs here; the map data lives in YAML. Upstream still maintains
the full ``.py`` file, so a textual merge can succeed cleanly while dropping
or garbling upstream's map fix — the silent-drift class documented as risk R1
in ``docs/risk-register.md``. This gate runs in the sync workflow after the
merge and before the bot pushes.

A file is a hit when the upstream round (merge-base → theirs) touched it via
add/modify, the upstream version still defines a map (contains
``CampaignMap(``), and our merged tree does NOT (stub or file gone). New
upstream events pass by construction: they merge in wholesale, so our tree
carries the full definition too.

Run from the repo root right after ``git merge upstream/master``:

    uv run python dev_tools/check_campaign_stub_drift.py

Defaults assume HEAD is the fresh merge commit (``HEAD^1`` = our master,
``upstream/master`` = theirs). Override the revs for local rehearsal of past
merges. Stdlib only. Exit 0 = clean, exit 1 = hits listed on stdout.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

MAP_MARKER = "CampaignMap("


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def blob(rev: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{rev}:{path}"], capture_output=True, text=True, check=False
    )
    return result.stdout if result.returncode == 0 else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--head", default="HEAD", help="merged result (default: HEAD)")
    parser.add_argument("--ours", default="HEAD^1", help="our side before the merge")
    parser.add_argument("--theirs", default="upstream/master", help="upstream tip")
    args = parser.parse_args()

    base = git("merge-base", args.ours, args.theirs).strip()
    changed = git(
        "diff", "--name-only", "--diff-filter=AM", base, args.theirs, "--", "campaign"
    ).splitlines()
    py_files = [p for p in changed if p.endswith(".py")]

    hits: list[str] = []
    for path in py_files:
        theirs = blob(args.theirs, path)
        if theirs is None or MAP_MARKER not in theirs:
            continue  # upstream doesn't define a map in this file (logic-only)
        ours = blob(args.head, path)
        if ours is not None and MAP_MARKER in ours:
            continue  # our side still carries the full .py definition
        hits.append(path)

    if hits:
        print("R1 campaign stub-drift: this upstream round touches .py files whose")
        print("map layer this fork moved to YAML. Auto-push is blocked; convert the")
        print("upstream change (docs/upstream-sync.md) and land it via PR:")
        for path in sorted(hits):
            print(f"  {path}")
        return 1

    print(f"R1 clean: {len(py_files)} upstream campaign .py changes, none on converted files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
