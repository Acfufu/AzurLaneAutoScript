from typing import Any

from fastapi import APIRouter

from module.config.utils import filepath_args, read_file
from module.webui.api.models import SchemaResponse

router = APIRouter(tags=["schema"])


def _instance_server(instance: str) -> str:
    """Resolve an instance's server from its Emulator.PackageName (audit M8:
    select options used to be resolved as CN for every instance, so a value
    picked from CN options could silently fall back to option[0] on read
    for a non-CN server)."""
    from module.config.deep import deep_get
    from module.config.server import to_server
    from module.config.utils import filepath_config
    from module.webui.api.helpers import instance_mod

    mod = instance_mod(instance)
    raw = read_file(filepath_config(instance, mod)) if mod else read_file(filepath_config(instance))
    package = deep_get(raw, "Alas.Emulator.PackageName", "") or ""
    return to_server(package)


@router.get("/schema/{mod_name}", response_model=SchemaResponse)
def get_schema(mod_name: str = "alas", instance: str | None = None):
    from module.config.server import to_server

    menu = read_file(filepath_args("menu", mod_name))
    # args.json is generated as {task: {group: {arg: {...}}}}; the annotation
    # states the shape the generator guarantees.
    args: dict[str, Any] = read_file(filepath_args("args", mod_name))
    # Resolve server-specific select options, mirroring the legacy
    # AlasGUI.set_group() behavior. Server comes from the instance being
    # edited when the frontend passes one, else cn (no instance context).
    if instance:
        server = _instance_server(instance)
    else:
        server = to_server("cn")
    for _task, groups in args.items():
        for _group_name, argv in groups.items():
            for _arg_name, arg_dict in argv.items():
                if arg_dict.get("type") != "select":
                    continue
                options = arg_dict.get("option", [])
                server_options = arg_dict.get(f"option_{server}")
                if isinstance(server_options, list) and server_options:
                    options = server_options
                arg_dict["option"] = options
                if len(options) == 1:
                    only = options[0]
                    if only in arg_dict.get("option_bold", []):
                        arg_dict["type"] = "state"
    return {"menu": menu, "args": args}
