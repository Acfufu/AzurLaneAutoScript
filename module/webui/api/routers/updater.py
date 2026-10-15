import json
import threading
import time

from fastapi import APIRouter, Request

from module.logger import logger
from module.webui.api.helpers import _get_updater
from module.webui.api.models import OkResponse, UpdateInstallRequest

router = APIRouter(tags=["updater"])


@router.get("/update/status")
def update_status():
    return _get_updater().status()


@router.post("/update/refresh", response_model=OkResponse, response_model_exclude_none=True)
def update_refresh():
    def worker():
        try:
            _get_updater().refresh()
        except Exception as e:
            logger.exception(e)

    threading.Thread(target=worker, daemon=True).start()
    return {"ok": True}


@router.post("/update/install", response_model=OkResponse, response_model_exclude_none=True)
def update_install(body: UpdateInstallRequest):
    error = _get_updater().start_install(body.version)
    return {"ok": error is None, "error": error}


@router.post("/update/restart", response_model=OkResponse, response_model_exclude_none=True)
def update_restart(request: Request):
    """Ask the launcher to pull the payload and restart the backend (git mode).

    Signal channel is the control_api request file; the launcher's watcher
    consumes it and re-runs its startup setup between stop and start. Same
    localhost/lock gating as the scheduler control endpoints — with a webui
    password set, the PasswordGate middleware 401s this route anyway."""
    from module.webui.control_api import UPDATE_RESTART_REQUEST, _local_host, _locked

    if _locked() or not _local_host(request):
        return {"ok": False, "error": "locked"}
    error = None
    try:
        UPDATE_RESTART_REQUEST.parent.mkdir(parents=True, exist_ok=True)
        UPDATE_RESTART_REQUEST.write_text(
            json.dumps({"time": time.time()}), encoding="utf-8"
        )
    except OSError as e:
        logger.exception("update-restart request write failed")
        error = str(e)
    return {"ok": error is None, "error": error}
