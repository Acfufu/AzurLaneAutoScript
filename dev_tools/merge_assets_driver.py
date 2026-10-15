#!/usr/bin/env python3
"""Semantic 3-way merge driver for ALAS asset registry files.

Why this exists: the integration line (Joxos seed) rewrote every
``module/*/assets.py`` — not just formatting: collapsed per-locale dicts to
single tuples where locales agree, replaced placeholder asset paths with
real ones. Upstream keeps its verbose format and edits/appends entries for
new game content. A textual merge conflicts on virtually every entry line,
and even whole-line AST equality is useless because our rewrite changed the
trees. So the driver merges per SYMBOL, and for ``Call``-shaped entries
(Button(...)/Template(...)) per KWARG field:

- ours (integration line) supplies the entry's shape (function, kwarg set,
  order) and wins every field it deliberately changed;
- theirs (upstream) field changes land onto ours's shape (a coordinate fix
  replaces the coordinate value only);
- a field changed semantically on BOTH sides is a real clash — the entry is
  emitted as standard conflict markers and the driver exits 1 (the weekly
  workflow then opens a PR for a human);
- brand-new upstream symbols are appended verbatim at the end;
- entries deleted upstream stay deleted unless we modified them;
- non-Call entries (or unparseable lines) fall back to whole-line logic
  keyed on full-AST equality.

Merged Call entries are re-rendered with ``ast.unparse`` — canonical
formatting, not our historical style; ``dev_tools/dedup_assets.py``
regenerates these files anyway.

Wire-up (one-time per clone; the sync workflow does the same in CI):

    git config merge.alas-assets.driver \\
        "python3 dev_tools/merge_assets_driver.py %O %A %B"

and via .gitattributes:  ``module/*/assets.py merge=alas-assets``

Self-test: ``python3 dev_tools/merge_assets_driver.py --selftest``

Stdlib only. Exit 0 = merged (result in %A), exit 1 = conflict markers.
"""

import ast
import re
import sys
from pathlib import Path

# NAME = <rhs> — asset symbols are C-esque identifiers; rhs must parse as a
# standalone expression, otherwise the line is treated as context.
ENTRY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(\S.*?)\s*$")


def parse(text):
    """Return (order, entries).

    order: list of ("entry", sym) / ("line", raw) in file order.
    entries: sym -> (node, dump, raw_line). First definition wins.
    node: the parsed RHS ast node (None when unparseable).
    """
    order, entries = [], {}
    for raw in text.splitlines(keepends=True):
        m = ENTRY_RE.match(raw.rstrip("\n"))
        sym = node = dump = None
        if m:
            try:
                node = ast.parse(m.group(2), mode="eval").body
                dump = ast.dump(node)
            except (SyntaxError, ValueError, MemoryError, RecursionError):
                pass
            sym = m.group(1)
        if sym is None or node is None:
            order.append(("line", raw))
        else:
            if sym in entries:
                continue  # duplicate definition: first wins
            order.append(("entry", sym))
            entries[sym] = (node, dump, raw)
    return order, entries


def _call_kwargs(node):
    """{kwarg: dump} when node is a Call with keyword-only args, else None."""
    if not isinstance(node, ast.Call) or node.args:
        return None
    out = {}
    for kw in node.keywords:
        if kw.arg is None:  # **kwargs — bail out
            return None
        out[kw.arg] = ast.dump(kw.value)
    return out


def _kwarg_nodes(node):
    return {kw.arg: kw.value for kw in node.keywords}


def _normalize(node):
    """Semantic canonical form: a dict whose values are all identical IS that
    value — the integration line's collapse transform (per-locale dicts for
    single-locale assets become plain tuples/strings). Comparing normalized
    forms stops format divergence from masquerading as a content change."""
    if isinstance(node, ast.Dict) and node.values:
        norms = [_normalize(v) for v in node.values]
        first = ast.dump(norms[0])
        if all(ast.dump(n) == first for n in norms):
            return norms[0]
    return node


def _merge_field(b, o, t):
    """3-way one field by NORMALIZED AST dump. None = absent.
    Returns (node, clash) — node is the winner in normalized form."""
    bn = _normalize(b) if b is not None else None
    on = _normalize(o) if o is not None else None
    tn = _normalize(t) if t is not None else None
    bd = ast.dump(bn) if bn is not None else None
    od = ast.dump(on) if on is not None else None
    td = ast.dump(tn) if tn is not None else None
    ours_changed = od != bd
    theirs_changed = td != bd
    if not theirs_changed:
        return on, False
    if not ours_changed:
        return tn, False
    return (on, False) if od == td else (on, True)


def _merge_call(base_node, ours_node, theirs_node, sym):
    """Field-level merge of three Call nodes. Returns (line, clashed)."""
    bkw, okw, tkw = _call_kwargs(base_node), _call_kwargs(ours_node), _call_kwargs(theirs_node)
    if bkw is None or okw is None or tkw is None:
        return None  # shape not supported — caller falls back
    ours_vals = _kwarg_nodes(ours_node)
    base_vals = _kwarg_nodes(base_node)
    theirs_vals = _kwarg_nodes(theirs_node)
    merged, clashed = {}, False
    for name, oval in ours_vals.items():
        value, clash = _merge_field(base_vals.get(name), oval, theirs_vals.get(name))
        if clash:
            clashed = True
        merged[name] = (value, oval)
    if clashed:
        return None  # real semantic clash — caller emits markers
    parts = ", ".join(f"{name}={ast.unparse(value)}" for name, (value, _oval) in merged.items())
    return f"{sym} = {ours_node.func.id}({parts})\n"


def _entry_line(sym, base, ours, theirs, stats, out):
    """Merge one symbol; append line(s) to out."""
    onode, odump, oline = ours[sym]
    if sym not in base:  # new on our side — keep
        out.append(oline)
        return
    bnode, bdump, _ = base[sym]
    ours_changed = odump != bdump
    if sym not in theirs:  # deleted upstream
        if ours_changed:
            out.append(oline)  # we modified it, keep ours over deletion
        else:
            stats["deleted"] += 1  # respect upstream deletion
        return
    tnode, tdump, tline = theirs[sym]
    theirs_changed = tdump != bdump
    if not theirs_changed:
        out.append(oline)
        return
    # theirs touched this symbol: try the field-level merge first
    field_merged = _merge_call(bnode, onode, tnode, sym)
    if field_merged is not None:
        out.append(field_merged)
        stats["theirs"] += 1
        return
    # fall back to whole-line: identical trees keep ours, else markers
    if ours_changed and odump != tdump:
        stats["conflicts"] += 1
        out.append(f"<<<<<<< ours (integration)\n{oline}=======\n{tline}>>>>>>> theirs (upstream)\n")
    else:
        out.append(oline if ours_changed else tline)
        stats["theirs"] += 0 if ours_changed else 1


def resolve(base_text, ours_text, theirs_text):
    """Return (merged_text, stats_dict). Conflict markers bump 'conflicts'."""
    base_order, base = parse(base_text)
    ours_order, ours = parse(ours_text)
    theirs_order, theirs = parse(theirs_text)

    out, stats = [], {"theirs": 0, "added": 0, "deleted": 0, "conflicts": 0}

    for kind, key in ours_order:
        if kind == "line":
            out.append(key)
        else:
            _entry_line(key, base, ours, theirs, stats, out)

    # brand-new upstream symbols, appended in upstream's own order
    seen = set(ours)
    for kind, key in theirs_order:
        if kind == "entry" and key not in seen and key not in base:
            out.append(theirs[key][2])
            stats["added"] += 1

    return "".join(out), stats


def main(argv):
    if "--selftest" in argv:
        return selftest()
    if len(argv) != 4:
        print(__doc__)
        return 2
    base = Path(argv[1]).read_text(encoding="utf-8", errors="surrogateescape")
    ours = Path(argv[2]).read_text(encoding="utf-8", errors="surrogateescape")
    theirs = Path(argv[3]).read_text(encoding="utf-8", errors="surrogateescape")
    merged, stats = resolve(base, ours, theirs)
    Path(argv[2]).write_text(merged, encoding="utf-8", errors="surrogateescape")
    print(
        f"merge-assets: took-theirs={stats['theirs']} added={stats['added']} "
        f"deleted={stats['deleted']} conflicts={stats['conflicts']} ({argv[2]})"
    )
    return 1 if stats["conflicts"] else 0


def selftest():
    cases = [
        # (name, base, ours, theirs, expect_conflicts, expect_contains, expect_not_contains)
        (
            "format-only-rewrite-yields-to-upstream-edit",
            # ours only reformats (AST-identical to base) while upstream edits
            # coords: theirs wins whole-line — values must update, format
            # converges back to upstream for touched entries.
            "A = Button(area=(1, 2, 3, 4))\n",
            "A = Button(area=(1,2,3,4))\n",
            "A = Button(area=(1, 2, 5, 4))\n",
            0,
            ["A = Button(area=(1, 2, 5, 4))"],
            [],
        ),
        (
            "upstream-new-symbol-appended",
            "A = X(1)\n",
            "A = X(1)\n",
            "A = X(1)\nB = X(2)\n",
            0,
            ["B = X(2)"],
            [],
        ),
        (
            "upstream-deletion-respected",
            "A = X(1)\nB = X(2)\n",
            "A = X(1)\nB = X(2)\n",
            "A = X(1)\n",
            0,
            [],
            ["B = X"],
        ),
        (
            "ours-deletion-beats-upstream-edit",
            "A = X(1)\nB = X(2)\n",
            "A = X(1)\n",
            "A = X(1)\nB = X(9)\n",
            0,
            [],
            ["B = X"],
        ),
        (
            "semantic-clash-conflicts",
            "A = X(1)\n",
            "A = X(2)\n",
            "A = X(3)\n",
            1,
            ["<<<<<<< ours", ">>>>>>> theirs"],
            [],
        ),
        (
            "same-change-both-sides-keeps-ours",
            "A = X(1)\n",
            "A = X(9)  # ours fmt\n",
            "A = X(9)\n",
            0,
            ["A = X(9)  # ours fmt"],
            [],
        ),
        (
            "field-merge-theirs-coord-onto-ours-shape",
            # base: dict file placeholder; ours collapsed + real path;
            # theirs edits area only. Result: theirs's (normalized) area,
            # ours's file (itself collapsed by _normalize), ours's kwarg order.
            "A = Button(area={'cn': (1, 2, 3, 4)}, file={'cn': './cn.png'})\n",
            "A = Button(area=(1,2,3,4), file={'cn': './real/cn.png'})\n",
            "A = Button(area={'cn': (9, 2, 3, 4)}, file={'cn': './cn.png'})\n",
            0,
            ["A = Button(area=(9, 2, 3, 4), file='./real/cn.png')"],
            [],
        ),
        (
            "field-clash-same-kwarg-conflicts",
            "A = Button(area=(1, 2, 3, 4))\n",
            "A = Button(area=(5, 2, 3, 4))\n",
            "A = Button(area=(9, 2, 3, 4))\n",
            1,
            ["<<<<<<< ours (integration)"],
            [],
        ),
        (
            "multiline-context-taken-from-ours",
            "import os\nA = X(1)\n",
            "import os\nA = X(1)  # tweaked\n",
            "import sys\nA = X(1)\n",
            0,
            ["import os", "A = X(1)  # tweaked"],
            ["import sys"],
        ),
    ]
    failed = 0
    for name, b, o, t, want_conflicts, contains, not_contains in cases:
        merged, stats = resolve(b, o, t)
        ok = stats["conflicts"] == want_conflicts
        ok = ok and all(s in merged for s in contains)
        ok = ok and all(s not in merged for s in not_contains)
        if not ok:
            failed += 1
            print(f"FAIL {name}: stats={stats}\n---\n{merged}---")
    print(f"selftest: {len(cases) - failed}/{len(cases)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
