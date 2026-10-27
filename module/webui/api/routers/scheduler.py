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
    # No `running` field: the old one held pending[:1] — the expiry-queue
    # head, not the executing task — and the overview fabricated a "current"
    # task from it, mislabeling after priority edits (audit M12). What is
    # actually executing is running_func; the queue stays whole in pending.
    def dump(func):
        return {"command": func.command, "next_run": str(func.next_run)}

    return {
        "alive": manager.alive,
        "running_func": manager.running_func if manager.alive else None,
        "pending": [dump(f) for f in config.pending_task],
        "waiting": [dump(f) for f in config.waiting_task],
    }
