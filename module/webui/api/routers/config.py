import glob
import json as _json
import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from module.config.deep import deep_set
from module.config.utils import alas_instance, filepath_args, filepath_config, read_file, write_file
from module.submodule.utils import MOD_DICT
from module.webui.api.helpers import _save_config, _to_jsonable, instance_mod, valid_instance_name
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


def _target_file(config_name: str) -> str:
    """File backing a config request: plain instances use config/{name}.json,
    mod instances (maa/fpy) config/{name}.{mod}.json (audit M9 — the webui
    used to read/write config/alas.json for every instance name, so editing
    a mod instance silently did nothing). Same discrimination as
    instance_mod: a plain file always wins over the bridge file."""
    mod = instance_mod(config_name)
    return filepath_config(config_name, mod) if mod else filepath_config(config_name)


@router.get("/configs", response_model=list[ConfigListItem])
def configs_list():
    # Report the same names /status does (audit M9: the file-derived
    # "alas.maa" used to disagree with the instance name "alas"). Unknown
    # dotted suffixes are not instances (backup files etc., audit L5).
    out: dict[str, str] = {}
    for f in sorted(glob.glob("./config/*.json")):
        base = os.path.splitext(os.path.basename(f))[0]
        name, _, suffix = base.partition(".")
        if name == "template":
            continue
        if suffix and suffix not in MOD_DICT:
            continue
        out.setdefault(name, datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M:%S"))
    return [{"name": name, "modified": modified} for name, modified in out.items()]


@router.get("/config/{config_name}", response_model=dict[str, Any])
def get_config(config_name: str):
    _require_instance(config_name, write=False)
    if instance_mod(config_name):
        # Mod configs are shown read-only (audit M9); serve the real file
        # instead of running the alas config migration over it.
        return _to_jsonable(read_file(_target_file(config_name)))
    config = State.config_updater.read_file(config_name)
    return _to_jsonable(config)


@router.post("/config/{config_name}", response_model=SaveConfigResponse)
def set_config(config_name: str, request: SetValueRequest):
    _require_instance(config_name, write=True)
    if instance_mod(config_name):
        raise HTTPException(status_code=403, detail=f"Mod instance {config_name} is read-only in the webui")
    # request.value: {path.key: value} pairs, path joined by '.'
    modified = request.value
    args_schema: dict[str, Any] = read_file(filepath_args("args", "alas"))
    return _save_config(modified, config_name, args_schema)


@router.post("/config/{config_name}/import", response_model=OkResponse)
def import_config(config_name: str, request: ImportConfigRequest):
    # Import may create OR overwrite an instance (restoring a backup is the
    # point); the UI confirms overwrites (audit M6). template stays
    # protected, names get the /instance/new validation, and the source
    # machine's emulator serial is not carried over (same as /instance/new).
    name = config_name.strip()
    if not name:
        raise HTTPException(status_code=404, detail="Empty name")
    if name == "template" or name.startswith("template"):
        raise HTTPException(status_code=403, detail="template is read-only")
    error = valid_instance_name(name)
    if error is not None:
        raise HTTPException(status_code=404, detail=error)
    if instance_mod(name):
        raise HTTPException(status_code=403, detail=f"Mod instance {name} is read-only in the webui")
    config = request.config
    deep_set(config, "Alas.Emulator.Serial", "")
    write_file(_target_file(name), config)
    return {"ok": True}


@router.get("/config/{config_name}/export")
def export_config(config_name: str):
    _require_instance(config_name, write=False)
    if instance_mod(config_name):
        config = _to_jsonable(read_file(_target_file(config_name)))
    else:
        config = _to_jsonable(State.config_updater.read_file(config_name))
    content = _json.dumps(config, indent=2, ensure_ascii=False)
    return Response(
        content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{config_name}.json"'},
    )
