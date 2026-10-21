"""Flow rule tables call owner methods that are inlined transcriptions of the
original handler loops. When upstream renames or removes a method/keyword, the
merge updates the live handler but not the inlined copy — the copy then raises
at runtime (regression: `_cn_agreement_present` kept `color_threshold=` after
upstream renamed the kwarg to `threshold=` on 2026-09-10, crashing every CN
login until 2026-10-21).

Pyright cannot see these calls (`ctx.owner` is deliberately `Any` — the flow
engine is domain-agnostic), so this test resolves every `ctx.owner.<method>()`
call in the flow-converted handler files against the real handler classes and
asserts the method exists and accepts the given arguments.
"""

import ast
import importlib
import inspect
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from module.base.base import ModuleBase

HANDLER_DIR = Path(__file__).resolve().parents[1] / "module" / "handler"

# Calls kept verbatim from upstream defensive code: the method lives on a mixin
# the runtime owner MAY mix in, guarded by `hasattr` at the call site — its
# presence on the static handler class is intentionally not guaranteed.
# {module_stem: {method: reason}}
DEFENSIVE_CALLS: dict[str, dict[str, str]] = {
    # upstream L123: `hasattr(self, "is_combat_loading") and self.is_combat_loading()`;
    # defined on Combat (module/combat/combat.py), mixed in only by combat tasks
    "enemy_searching": {"is_combat_loading": "hasattr-guarded Combat mixin call"},
}


def _flow_files() -> list[Path]:
    """Every handler module whose helpers bind `ctx.owner` — i.e. converted to
    the flow rule-table style. Extends itself as more modules are converted."""
    return sorted(
        p for p in HANDLER_DIR.glob("*.py") if "ctx.owner" in p.read_text(encoding="utf-8")
    )


def _owner_classes(module_name: str) -> list[type]:
    mod = importlib.import_module(module_name)
    return [
        obj
        for obj in vars(mod).values()
        if inspect.isclass(obj) and obj.__module__ == module_name and issubclass(obj, ModuleBase)
    ]


def _iter_owner_calls(tree: ast.AST) -> Iterator[tuple[ast.Call, str]]:
    """Yield (call, method_name) whose receiver is exactly `ctx.owner` — not
    `ctx.owner.device` / `ctx.owner.<timer>`, those surfaces are out of scope."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        recv = node.func.value
        if (
            isinstance(recv, ast.Attribute)
            and recv.attr == "owner"
            and isinstance(recv.value, ast.Name)
            and recv.value.id == "ctx"
        ):
            yield node, node.func.attr


def _lookup(classes: list[type], name: str) -> Any:
    for cls in classes:
        attr = getattr(cls, name, None)  # resolves the full MRO (mixins included)
        if attr is not None:
            return attr
    return None


@pytest.mark.parametrize("path", _flow_files(), ids=lambda p: p.stem)
def test_flow_owner_calls_match_handler(path: Path):
    module_name = f"module.handler.{path.stem}"
    classes = _owner_classes(module_name)
    assert classes, f"{module_name} defines no ModuleBase subclass; extend _owner_classes()"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    drifted: list[str] = []
    allowed = DEFENSIVE_CALLS.get(path.stem, {})
    for call, name in _iter_owner_calls(tree):
        if name in allowed:
            continue
        where = f"{path.name}:{call.lineno} ctx.owner.{name}()"
        attr = _lookup(classes, name)
        if attr is None:
            drifted.append(f"{where} — no such method on {classes[0].__name__} (renamed/removed upstream?)")
            continue
        if not callable(attr):
            drifted.append(f"{where} — resolves to non-callable {type(attr).__name__}")
            continue
        params = inspect.signature(attr).parameters
        if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
            continue  # accepts anything
        for kw in call.keywords:
            if kw.arg is not None and kw.arg not in params:
                drifted.append(f"{where} — no parameter {kw.arg!r} (signature: {list(params)})")
        positional = [a for a in call.args if not isinstance(a, ast.Starred)]
        if len(positional) > len(params):
            drifted.append(f"{where} — {len(positional)} positional args but signature has {len(params)}")

    assert not drifted, "flow transcription drifted from the live handler:\n" + "\n".join(drifted)
