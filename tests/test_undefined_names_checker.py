"""Unit tests for dev_tools/check_undefined_names.py.

Synthesizes the ruff-JSON findings (the checker's input contract) against
small star-import trees in tmp_path, with the checker's ROOT monkeypatched
there so absolute module specs resolve inside the test tree. The scenarios
mirror the production incident class: a name used inside a function body that
no explicit import lists and no star-import source exports.
"""

import sys

import pytest

sys.path.insert(0, ".")

from dev_tools import check_undefined_names as checker


def finding(file, row, code, name):
    """One ruff-JSON finding, minimal fields the classifier reads."""
    message = {
        "F405": f"`{name}` may be undefined, or defined from star imports: module.bundle",
        "F821": f"`{name}` is not defined",
    }[code]
    return {"code": code, "filename": str(file), "location": {"row": row}, "message": message}


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A consumer file star-importing bundle.py; checker ROOT -> tmp_path."""
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    consumer = tmp_path / "consumer.py"
    bundle = tmp_path / "bundle.py"

    def write_consumer(names=""):
        consumer.write_text(
            "from bundle import *  # noqa: F403\n" + names, encoding="utf-8"
        )

    write_consumer()
    return tmp_path, consumer, bundle, write_consumer


def test_star_name_in_bundle_is_legit(tree):
    _, consumer, bundle, _ = tree
    bundle.write_text("GOOD = 1\n", encoding="utf-8")
    violations, legit, _ = checker.classify([finding(consumer, 3, "F405", "GOOD")])
    assert violations == []
    assert legit == 1


def test_star_name_absent_everywhere_is_confirmed(tree):
    _, consumer, bundle, _ = tree
    bundle.write_text("OTHER = 1\n", encoding="utf-8")
    violations, _, _ = checker.classify([finding(consumer, 3, "F405", "color_mask")])
    assert len(violations) == 1
    assert violations[0]["name"] == "color_mask"
    assert "bundle.py" in violations[0]["why"]


def test_f821_is_always_a_violation(tree):
    _, consumer, _, _ = tree
    violations, _, _ = checker.classify([finding(consumer, 3, "F821", "nope")])
    assert len(violations) == 1
    assert "no star import" in violations[0]["why"]


def test_chained_star_supplies_name(tree):
    _, consumer, bundle, _ = tree
    (tree[0] / "bundle2.py").write_text("DEEP = 1\n", encoding="utf-8")
    bundle.write_text("from bundle2 import *\n", encoding="utf-8")
    violations, legit, _ = checker.classify([finding(consumer, 3, "F405", "DEEP")])
    assert violations == []
    assert legit == 1


def test_dunder_all_restricts_exports(tree):
    _, consumer, bundle, _ = tree
    bundle.write_text("__all__ = ['A']\nA = 1\nB = 2\n", encoding="utf-8")
    violations, legit, _ = checker.classify([
        finding(consumer, 3, "F405", "A"),
        finding(consumer, 4, "F405", "B"),
    ])
    assert [v["name"] for v in violations] == ["B"]
    assert legit == 1


def test_underscore_private_is_not_star_exported(tree):
    _, consumer, bundle, _ = tree
    bundle.write_text("_PRIVATE = 1\n", encoding="utf-8")
    violations, _, _ = checker.classify([finding(consumer, 3, "F405", "_PRIVATE")])
    assert len(violations) == 1


def test_unresolvable_source_is_conservatively_allowed(tree):
    _, consumer, _, _ = tree
    # consumer stars a bundle that does not exist on disk
    violations, _, unresolved = checker.classify([finding(consumer, 3, "F405", "anything")])
    assert violations == []
    assert unresolved == 1


def test_module_exports_relative_spec(tmp_path):
    """Relative star imports inside a package resolve to its directory."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "bundle.py").write_text("X = 1\n", encoding="utf-8")
    src = checker.resolve_module_path(".bundle", relative_to=pkg / "mod.py")
    assert src == pkg / "bundle.py"
    assert "X" in checker.module_exports(src)
