from fastapi import APIRouter

from module.webui.api.models import SchedulerResponse
from module.webui.process_manager import ProcessManager

router = APIRouter(tags=["scheduler"])


@router.get("/scheduler/{config_name}", response_model=SchedulerResponse)
def scheduler(config_name: str):
    from module.config.config import AzurLaneConfig

    # read_only: the webui must report the schedule as written on disk,
    # not as the scheduler loop's override() would coerce it (force-enable
    # and NextRun clamping are run policy, not display truth — audit H4).
    config = AzurLaneConfig(config_name, read_only=True)
    config.load()
    config.get_next_task()
    manager = ProcessManager.get_manager(config_name)
    alive = manager.alive
    pending = config.pending_task
    if alive and len(pending) >= 1:
        running = pending[:1]
        pending = pending[1:]
    else:
        running = []

    def dump(func):
        return {"command": func.command, "next_run": str(func.next_run)}

    return {
        "alive": alive,
        "running_func": manager.running_func if alive else None,
        "running": [dump(f) for f in running],
        "pending": [dump(f) for f in pending],
        "waiting": [dump(f) for f in config.waiting_task],
    }
