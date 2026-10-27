from fastapi import APIRouter

from module.webui.api.models import OkResponse, RemoteStatusResponse

router = APIRouter(tags=["remote"])


@router.get("/remote/status", response_model=RemoteStatusResponse)
def remote_status():
    from module.webui.remote_access import RemoteAccess

    return {
        "alive": RemoteAccess.is_alive(),
        "state": RemoteAccess.get_state(),
        "entry_point": RemoteAccess.get_entry_point(),
    }


@router.post("/remote/start", response_model=OkResponse, response_model_exclude_none=True)
def remote_start():
    from module.webui.remote_access import ParseError, start_remote_access_service

    # An unconfigured/malformed SSHServer raised ParseError uncaught and
    # surfaced as HTTP 500 instead of an honest ok:false (audit L2).
    try:
        start_remote_access_service()
    except ParseError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True}


@router.post("/remote/stop", response_model=OkResponse, response_model_exclude_none=True)
def remote_stop():
    from module.webui.remote_access import RemoteAccess

    RemoteAccess.kill_ssh_process()
    return {"ok": True}
