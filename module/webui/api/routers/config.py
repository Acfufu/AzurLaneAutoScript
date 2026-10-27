import glob
import json as _json
import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from module.config.utils import alas_instance, filepath_args, filepath_config, read_file, write_file
from module.webui.api.helpers import _save_config, _to_jsonable
from module.webui.api.models import ConfigListItem, ImportConfigRequest, OkResponse, SaveConfigResponse, SetValueRequest
from module.webui.setting import State

router = APIRouter(tags=["config"])


def _require_instance(config_name: str, *, write: bool) -> None:
    """Only real instances may be read or written (audit M10): an unknown
    name used to GET a full default config (HTTP 200) or POST a config file
    into existence — a ghost instance /status never lists. `template` stays
    readable but is never writable.
    """
    if config_name == "template":
        if write:
            raise HTTPException(status_code=403, detail="template is read-only")
        return
    if config_name not in alas_instance():
        raise HTTPException(status_code=404, detail=f"Instance {config_name} not found")


@router.get("/configs", response_model=list[ConfigListItem])
def configs_list():
    out = []
    for f in sorted(glob.glob("./config/*.json")):
        name = os.path.splitext(os.path.basename(f))[0]
        if name.startswith("template"):
            continue
        mtime = datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M:%S")
        out.append({"name": name, "modified": mtime})
    return out


@router.get("/config/{config_name}", response_model=dict[str, Any])
def get_config(config_name: str):
    _require_instance(config_name, write=False)
    config = State.config_updater.read_file(config_name)
    return _to_jsonable(config)


@router.post("/config/{config_name}", response_model=SaveConfigResponse)
def set_config(config_name: str, request: SetValueRequest):
    _require_instance(config_name, write=True)
    # request.value: {path.key: value} pairs, path joined by '.'
    modified = request.value
    args_schema: dict[str, Any] = read_file(filepath_args("args", "alas"))
    return _save_config(modified, config_name, args_schema)


@router.post("/config/{config_name}/import", response_model=OkResponse)
def import_config(config_name: str, request: ImportConfigRequest):
    _require_instance(config_name, write=True)
    write_file(filepath_config(config_name), request.config)
    return {"ok": True}


@router.get("/config/{config_name}/export")
def export_config(config_name: str):
    _require_instance(config_name, write=False)
    config = _to_jsonable(State.config_updater.read_file(config_name))
    content = _json.dumps(config, indent=2, ensure_ascii=False)
    return Response(
        content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{config_name}.json"'},
    )
