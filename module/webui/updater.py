"""Update surfaces, per build type.

Installed (frozen) builds update by whole-release replacement: the backend
pulls the release list from the configured GitHub repository, downloads that
release's NSIS setup exe and runs it silently. The installer asks the
launcher to exit (`Alas.exe --quit`), replaces the program directory and
relaunches the app (`/R`).

Source checkouts update through git instead: this module fetches origin and
lists the commits a restart would apply; the tab's restart button asks the
launcher to pull + restart (POST /update/restart -> control_api request
file -> src/update_restart.rs watcher). The launcher owns the repo and
re-runs its startup setup (pull + sparse checkout + control patch) between
stop and start, so the restart IS the update.

The Update page branches on `mode` ("release" | "git") — both faces stay in
one view, only one is ever active.
"""

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests

from module.logger import logger

GITHUB_API = "https://api.github.com"
DEFAULT_REPO = "Acfufu/AzurLaneAutoScript"
# The installer must outlive this process: it replaces the files the backend
# is running from, so it runs detached instead of as a child.
_DETACHED = 0x0000_0008 | 0x0000_0200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

# Payload root (module/webui/updater.py -> module/webui -> module -> root).
# Pinned explicitly so git calls work regardless of process cwd.
_REPO_ROOT = str(Path(__file__).resolve().parents[2])


def _run_git(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    """Run git against the payload repo; captures output, never raises."""
    return subprocess.run(
        ["git", "-C", _REPO_ROOT, *args], capture_output=True, text=True, timeout=timeout
    )


class Updater:
    def __init__(self):
        self.state = "idle"  # idle | refreshing | ready | failed | installing
        self.error: str | None = None
        self.releases: list[dict] = []
        self.install: dict | None = None  # {version, stage, progress}
        # git updater (source checkouts)
        self.git_state = "idle"  # idle | fetching | ready | failed
        self.git_error: str | None = None
        self.git_commits: list[dict] = []  # [{sha, date, message}] pending on restart
        self._lock = threading.Lock()

    # ---------- configuration ----------

    @property
    def repo(self) -> str:
        return (os.environ.get("ALAS_UPDATE_REPO") or DEFAULT_REPO).strip().strip("/")

    @property
    def branch(self) -> str:
        try:
            from module.webui.setting import State

            return getattr(State.deploy_config, "Branch", None) or "master"
        except Exception:  # deploy config unreadable — fall back to the default branch
            return "master"

    @staticmethod
    def current_version() -> str:
        """Frozen builds: version.txt next to the sidecar executable.
        Source checkouts: git HEAD (short sha + date) — the honest "version"
        of a git-managed tree; "dev" only when even git fails."""
        if not getattr(sys, "frozen", False):
            try:
                head = _run_git(["log", "-1", "--pretty=format:%h %ad", "--date=short"], timeout=10)
                if head.returncode == 0 and head.stdout.strip():
                    return head.stdout.strip()
            except Exception:
                logger.exception("git HEAD resolve failed")
            return "dev"
        root = os.path.dirname(os.path.abspath(sys.executable))
        path = os.path.join(root, "version.txt")
        try:
            with open(path, encoding="utf-8") as f:
                return f.read().strip() or "dev"
        except OSError:
            return "dev"

    @staticmethod
    def is_installed_build() -> bool:
        return bool(getattr(sys, "frozen", False))

    # ---------- update checks ----------

    def refresh(self):
        """Dispatch by build type: git fetch for source checkouts, release
        list for frozen installs. Runs on a router worker thread."""
        if not self.is_installed_build():
            self.git_refresh()
            return
        with self._lock:
            if self.state == "installing":
                return
            self.state = "refreshing"
            self.error = None
        try:
            url = f"{GITHUB_API}/repos/{self.repo}/releases?per_page=30"
            resp = requests.get(
                url, timeout=20, headers={"Accept": "application/vnd.github+json", "User-Agent": "alas"}
            )
            resp.raise_for_status()
            releases = []
            for rel in resp.json():
                releases.append(
                    {
                        "tag": rel["tag_name"],
                        "name": rel.get("name") or rel["tag_name"],
                        "body": (rel.get("body") or "")[:2000],
                        "date": rel.get("published_at") or "",
                        "prerelease": bool(rel.get("prerelease")),
                        "assets": [
                            {
                                "name": a["name"],
                                "size": a.get("size", 0),
                                "url": a["browser_download_url"],
                            }
                            for a in rel.get("assets", [])
                        ],
                    }
                )
            with self._lock:
                self.releases = releases
                self.state = "ready"
        except Exception as e:
            logger.exception("Fetch releases failed")
            with self._lock:
                self.state = "failed"
                self.error = str(e)

    def status(self) -> dict:
        with self._lock:
            return {
                "current": self.current_version(),
                "repo": self.repo,
                "mode": "release" if self.is_installed_build() else "git",
                "state": self.state,
                "error": self.error,
                "releases": self.releases,
                "installing": self.install,
                "git": {
                    "branch": self.branch,
                    "state": self.git_state,
                    "error": self.git_error,
                    "commits": self.git_commits,
                },
            }

    # ---------- git updater (source checkouts) ----------

    def git_refresh(self):
        """Fetch origin and list the commits a launcher restart would apply.
        Read-only: this never touches the working tree — the launcher owns
        all mutations (startup pull, restart-with-update)."""
        with self._lock:
            self.git_state = "fetching"
            self.git_error = None
        try:
            branch = self.branch
            fetch = _run_git(["fetch", "origin", branch])
            if fetch.returncode != 0:
                raise RuntimeError(fetch.stderr.strip() or "git fetch failed")
            log = _run_git(
                [
                    "log",
                    "--pretty=format:%h\x1f%ad\x1f%s",
                    "--date=short",
                    f"HEAD..origin/{branch}",
                ]
            )
            if log.returncode != 0:
                raise RuntimeError(log.stderr.strip() or "git log failed")
            commits = []
            for line in log.stdout.splitlines():
                if not line.strip():
                    continue
                parts = line.split("\x1f", 2)
                if len(parts) == 3:
                    commits.append({"sha": parts[0], "date": parts[1], "message": parts[2]})
            with self._lock:
                self.git_commits = commits
                self.git_state = "ready"
            logger.info(f"git update check: {len(commits)} new commit(s) on origin/{branch}")
        except Exception as e:
            logger.exception("Git update check failed")
            with self._lock:
                self.git_state = "failed"
                self.git_error = str(e)

    # ---------- install ----------

    def start_install(self, tag: str) -> str | None:
        """Start an install worker; returns an error string if refused."""
        with self._lock:
            if self.state == "installing":
                return "An install is already in progress"
            release = next((r for r in self.releases if r["tag"] == tag), None)
        if release is None:
            return f"Release {tag} not found, refresh the list first"
        threading.Thread(target=self._install_worker, args=(release,), daemon=True).start()
        return None

    def _install_worker(self, release: dict):
        with self._lock:
            self.state = "installing"
            self.install = {"version": release["tag"], "stage": "preparing", "progress": 0}
            self.error = None
        try:
            self._install(release)
        except Exception as e:
            logger.exception("Release install failed")
            with self._lock:
                self.state = "failed"
                self.error = str(e)
                self.install = None

    def _install(self, release: dict):
        if not self.is_installed_build():
            raise RuntimeError("Installing a release requires the installed desktop build")

        tmp = os.path.join(os.environ.get("TEMP", "."), "alas-update", release["tag"])
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp, exist_ok=True)

        setup_asset = next(
            (a for a in release["assets"] if a["name"].lower().endswith(".exe") and "setup" in a["name"].lower()), None
        )
        if setup_asset is None:
            raise RuntimeError(
                "Release has no setup exe (this build updates through the NSIS installer; "
                "a portable zip has to be unpacked by hand)"
            )

        def _progress(stage: str, done: int, total: int):
            frac = 0 if not total else min(done / total, 1.0)
            with self._lock:
                if self.install is not None:
                    self.install["stage"] = stage
                    self.install["progress"] = round(frac * 100)

        setup_path = self._download(setup_asset, os.path.join(tmp, setup_asset["name"]), lambda d, t: _progress("downloading installer", d, t))

        # Stop the bot first: it writes into config/ and log/ under the data
        # directory, and the installer replaces the program directory.
        self._stop_tasks()

        # Let the launcher hand the app over. The installer runs as a
        # separate process and must survive this backend going away - which is
        # why it is started detached and this process exits right after.
        with self._lock:
            if self.install is not None:
                self.install["stage"] = "installing"
                self.install["progress"] = 100
        logger.info(f"Running installer {setup_path} /S /R")
        subprocess.Popen(
            [setup_path, "/S", "/R"],
            close_fds=True,
            creationflags=_DETACHED if os.name == "nt" else 0,
        )

    @staticmethod
    def _download(asset: dict, path: str, progress) -> str:
        logger.info(f"Downloading {asset['name']} ({asset.get('size', 0)} bytes)")
        # A mirror (proxy-friendly CDN) can be set for networks where
        # github.com is slow; the release list keeps coming from the API.
        base = (os.environ.get("ALAS_UPDATE_MIRROR") or "").rstrip("/")
        url = f"{base}/{asset['name']}" if base else asset["url"]
        with requests.get(url, stream=True, timeout=60, headers={"User-Agent": "alas"}) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length") or asset.get("size") or 0)
            done = 0
            with open(path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1 << 16):
                    if chunk:
                        f.write(chunk)
                        done += len(chunk)
                        progress(done, total)
        return path

    @staticmethod
    def _stop_tasks():
        from module.webui.process_manager import ProcessManager

        running = []
        for manager in ProcessManager._processes.values():
            if manager.alive:
                running.append(manager)
                manager.stop()
        deadline = time.time() + 30
        while running and time.time() < deadline:
            running = [m for m in running if m.alive]
            time.sleep(0.5)


updater = Updater()
