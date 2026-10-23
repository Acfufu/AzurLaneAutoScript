"""Scenario tests for the R1 campaign stub-drift gate.

Each test builds a throwaway git repository: a base commit where every map
is a full ``.py`` definition, an "ours" line that stubbed ``campaign_10_1``
and deleted ``campaign_9_5`` (map layer moved to YAML), and an upstream line
that still maintains full ``.py`` maps. The gate runs with explicit revs and
the exit code is asserted. Scenarios mirror the risk register entry R1:
stub hit, deleted-file hit, empty round, and logic-only round.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "dev_tools" / "check_campaign_stub_drift.py"

FULL_MAP = "MAP = CampaignMap('X')\nMAP.shape = 'G6'\n"
FULL_MAP_FIXED = "MAP = CampaignMap('X')\nMAP.shape = 'H6'\n"
STUB_ONLY = "class Campaign(CampaignBase):\n    def battle_0(self):\n        return True\n"
LOGIC_ONLY = "class CampaignBase:\n    def handle(self):\n        return True\n"


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


def commit_all(repo: Path, message: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-m", message)


def write(repo: Path, name: str, text: str | None) -> None:
    path = repo / "campaign" / name
    if text is None:
        path.unlink(missing_ok=True)
    else:
        path.write_text(text)


def init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "campaign").mkdir(parents=True)
    git(repo, "init", "-b", "master")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "test")
    write(repo, "campaign_10_1.py", FULL_MAP + STUB_ONLY)
    write(repo, "campaign_9_5.py", FULL_MAP + STUB_ONLY)
    write(repo, "campaign_base.py", LOGIC_ONLY)
    commit_all(repo, "base: full .py maps everywhere")
    # Ours: map layer leaves .py — 10-1 stubbed, 9-5 deleted.
    write(repo, "campaign_10_1.py", STUB_ONLY)
    write(repo, "campaign_9_5.py", None)
    commit_all(repo, "ours: convert maps to YAML")
    return repo


def upstream_round(repo: Path, edits: dict[str, str | None]) -> None:
    """Branch `upstream` off the base commit applying the given file edits."""
    git(repo, "branch", "upstream", "master~1")
    git(repo, "checkout", "-q", "upstream")
    for name, text in edits.items():
        write(repo, name, text)
    commit_all(repo, "upstream round")
    git(repo, "checkout", "-q", "master")


def run_gate(repo: Path, head: str, ours: str, theirs: str) -> int:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--head", head, "--ours", ours, "--theirs", theirs],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.stderr == "", result.stderr
    return result.returncode


def test_upstream_map_fix_on_stub_is_a_hit(tmp_path: Path) -> None:
    """The core scenario: upstream fixes a map that lives in a stub here.
    A clean textual merge would silently drop it — the gate must go red."""
    repo = init_repo(tmp_path)
    upstream_round(repo, {"campaign_10_1.py": FULL_MAP_FIXED + STUB_ONLY})
    assert run_gate(repo, "master", "master", "upstream") == 1


def test_upstream_edit_on_deleted_map_is_a_hit(tmp_path: Path) -> None:
    """Files we deleted outright are hits too when the upstream round edits
    them: the fix needs converting into our YAML layer."""
    repo = init_repo(tmp_path)
    upstream_round(repo, {"campaign_9_5.py": FULL_MAP_FIXED + STUB_ONLY})
    assert run_gate(repo, "master", "master", "upstream") == 1


def test_logic_only_round_is_clean(tmp_path: Path) -> None:
    """Upstream edits with no map definition are exactly the changes our
    stubs want to absorb; the gate stays green so the sync auto-pushes."""
    repo = init_repo(tmp_path)
    upstream_round(repo, {"campaign_base.py": LOGIC_ONLY + "    # tuned\n"})
    assert run_gate(repo, "master", "master", "upstream") == 0


def test_empty_round_is_clean(tmp_path: Path) -> None:
    """No upstream changes at all (already synced): green, and the stdout
    report mentions zero campaign .py changes."""
    repo = init_repo(tmp_path)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--head", "master", "--ours", "master", "--theirs", "master~1"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "0 upstream campaign .py changes" in result.stdout
