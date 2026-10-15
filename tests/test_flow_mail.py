"""The mail_enter flow must issue exactly the calls the loop used to.

`module/freebies/mail_white.py` no longer contains the `while 1:` loop behind
`_mail_enter`; it is flow data now (B3b). `legacy_mail_enter` below is the
pre-migration body verbatim, and both forms replay the same scenarios:

    legacy  = the loop as it was before the migration
    current = `_mail_enter_flow()` through the flow engine
    trace   = every device call, per frame

The scenarios encode the page the loop really runs on: `_mail_enter` starts on
page_main_white, where the mail page is entered through MAIL_ENTER_WHITE (the
white-UI branch of `ui_main_appear_then_click`), and the mail page then shows
MAIL_MANAGE, whose click leads to MAIL_BATCH_CLAIM ("Mail entered").

Two regression shapes are pinned here, both introduced by the migration and
found on 2026-10-16 (the Mail task sat on page_main_white logging
`state=s hit rule=manage ✓` until its timeout):

1. `_mail_manage_click` returned True unconditionally, so the `manage` rule
   reported "handled" on frames where MAIL_MANAGE was not on screen and
   nothing had been clicked. A `call_if` rule that handled stops rule
   evaluation for that frame (the original `if ...: continue`), so the
   `goto_mail` rule - the only thing that enters the mail page from
   page_main_white - never ran. A helper behind `call_if` must be truthy only
   when it acted.
2. `_mail_enter_end` dropped `owner._mail_enter_timeout` at the end of every
   check, so the timer behind the 0.6 s "wait GOTO_MAIN_WHITE timeout" exit
   was rebuilt from zero each frame and never accumulated. The legacy loop
   starts its timer once and never resets it (`Timer.start()` only starts), so
   an empty mailbox that shows neither MAIL_WHITE_EMPTY nor MAIL_MANAGE exits
   after 0.6 s - the flow version spun to its 60 s timeout instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import module.base.timer as timer_module
from dev_tools.flow_replay import Frame, Replay
from module.base.timer import Timer
from module.combat.assets import GET_ITEMS_1, GET_ITEMS_2
from module.freebies import mail_white
from module.freebies.assets import MAIL_BATCH_CLAIM, MAIL_MANAGE, MAIL_WHITE_EMPTY
from module.freebies.mail_white import _mail_enter_flow
from module.flow.runtime import run_flow, set_runtime
from module.ui.page import GOTO_MAIN_WHITE, page_mail
from module.ui.ui import UI


# --- the loop as it was before the migration ------------------------------


def legacy_mail_enter(owner, skip_first_screenshot=True):
    """Verbatim pre-migration body (`_mail_enter`, before the flow migration)."""
    owner.interval_clear([MAIL_MANAGE])
    timeout = Timer(0.6, count=1)
    has_mail = False
    while 1:
        if skip_first_screenshot:
            skip_first_screenshot = False
        else:
            owner.device.screenshot()

        # End
        if owner.appear(MAIL_BATCH_CLAIM, offset=(20, 20)):
            return True
        if owner.appear(MAIL_WHITE_EMPTY, offset=(20, 20)):
            return False
        if not has_mail and owner.appear(GOTO_MAIN_WHITE, offset=(20, 20)):
            timeout.start()
            if timeout.reached():
                return False

        # Click
        if owner.appear_then_click(MAIL_MANAGE, offset=(30, 30), interval=3):
            has_mail = True
            continue
        if owner.ui_main_appear_then_click(page_mail, offset=(30, 30), interval=3):
            continue
        if owner._handle_mail_reward():
            continue


def flow_mail_enter(owner, skip_first_screenshot=True):
    """The shipped wrapper: `MailWhite._mail_enter`'s body around the flow."""
    owner.interval_clear([MAIL_MANAGE])
    owner._mail_enter_timeout = None
    set_runtime(None)
    return bool(
        run_flow(
            _mail_enter_flow(),
            owner=owner,
            skip_first=skip_first_screenshot,
            params={"_mail_enter_result": False, "_mail_has_mail": False},
        )
    )


class MailReplay(Replay):
    """A Replay with the owner surface MailWhite's loop needs.

    `ui_main_appear_then_click` delegates to the production method, so the
    page links (page_main_white -> MAIL_ENTER_WHITE) are the real ones.
    """

    def ui_main_appear_then_click(self, page, offset=(30, 30), interval=3):
        return UI.ui_main_appear_then_click(self, page, offset=offset, interval=interval)

    def _handle_mail_reward(self):
        """The legacy method, verbatim (MailWhite._handle_mail_reward)."""
        if self.appear(GET_ITEMS_1, offset=(30, 30), interval=3):
            self.device.click(MAIL_BATCH_CLAIM)
            return True
        if self.appear(GET_ITEMS_2, offset=(30, 30), interval=3):
            self.device.click(MAIL_BATCH_CLAIM)
            return True
        return False


_FRAME_SECONDS = 0.25
_CLOCK_START = 10.0


class _Clock:
    now = _CLOCK_START


class ClockedReplay(MailReplay):
    """A replay whose wall clock advances one frame step per screenshot.

    The harness replays frames far faster than a device, so a scenario that
    reaches a `Timer` needs the clock to move with the frames - otherwise a
    0.6 s window would need thousands of frames and the outcome would depend
    on machine speed. Both sides read the same patched clock (see the
    `fake_clock` fixture), so the comparison stays honest.
    """

    class _Device(MailReplay._Device):
        def screenshot(self):
            super().screenshot()
            _Clock.now += _FRAME_SECONDS


@pytest.fixture(autouse=True)
def fake_clock(monkeypatch):
    monkeypatch.setattr(timer_module, "time", lambda: _Clock.now)
    _Clock.now = _CLOCK_START
    yield


# --- scenarios ------------------------------------------------------------

# page_main_white, then the mail page (MAIL_MANAGE after the entry click),
# then the batch-claim bar that ends the loop with "Mail entered".
MAIN_WHITE_THEN_MAIL = [
    {"present": ["MAIN_GOTO_CAMPAIGN_WHITE"]},
    {"present": ["MAIN_GOTO_CAMPAIGN_WHITE"]},
    {"present": ["MAIL_MANAGE", "GOTO_MAIN_WHITE"]},
    {"present": ["MAIL_MANAGE", "GOTO_MAIN_WHITE"]},
    {"present": ["MAIL_MANAGE", "MAIL_BATCH_CLAIM", "GOTO_MAIN_WHITE"]},
    {"present": ["MAIL_MANAGE", "MAIL_BATCH_CLAIM", "GOTO_MAIN_WHITE"]},
    {"present": ["MAIL_MANAGE", "MAIL_BATCH_CLAIM", "GOTO_MAIN_WHITE"]},
]

# The mail page turns out to be empty.
MAIN_WHITE_THEN_EMPTY_MAIL = [
    {"present": ["MAIN_GOTO_CAMPAIGN_WHITE"]},
    {"present": ["MAIN_GOTO_CAMPAIGN_WHITE"]},
    {"present": ["MAIL_WHITE_EMPTY", "GOTO_MAIN_WHITE"]},
    {"present": ["MAIL_WHITE_EMPTY", "GOTO_MAIN_WHITE"]},
    {"present": ["MAIL_WHITE_EMPTY", "GOTO_MAIN_WHITE"]},
]

# Empty mailbox with no placeholder and no manage button: the only way out is
# the 0.6 s GOTO_MAIN_WHITE timeout.
MAIN_WHITE_THEN_GOTO_TIMEOUT = [
    {"present": ["MAIN_GOTO_CAMPAIGN_WHITE"]},
    {"present": ["MAIN_GOTO_CAMPAIGN_WHITE"]},
    {"present": ["GOTO_MAIN_WHITE"]},
    {"present": ["GOTO_MAIN_WHITE"]},
    {"present": ["GOTO_MAIN_WHITE"]},
    {"present": ["GOTO_MAIN_WHITE"]},
    {"present": ["GOTO_MAIN_WHITE"]},
]

SCENARIOS = [MAIN_WHITE_THEN_MAIL, MAIN_WHITE_THEN_EMPTY_MAIL, MAIN_WHITE_THEN_GOTO_TIMEOUT]


def _run_pair(scenario, max_frames=30, replay_cls=ClockedReplay):
    """Replay one scenario through the legacy loop and the migrated flow.

    Both sides run against their own replay of the same frames, so the
    recognizers and the recorded call stream are identical. `replay_cls`
    exists so a test can hand the flow side a *broken* replay and see whether
    the comparison notices.
    """
    frames = [Frame.from_dict(f) for f in scenario]

    _Clock.now = _CLOCK_START
    legacy_owner = replay_cls(frames, max_frames=max_frames)
    legacy_result = legacy_mail_enter(legacy_owner)

    _Clock.now = _CLOCK_START
    flow_owner = replay_cls(frames, max_frames=max_frames)
    try:
        flow_result = flow_mail_enter(flow_owner)
    except RuntimeError as e:
        # The loop never ended within max_frames (what the deadlock looks
        # like once the stand-in world stops advancing on its own).
        flow_result = f"<{e}>"
    return legacy_owner, legacy_result, flow_owner, flow_result


def _differences(old: Replay, old_result, new: Replay, new_result) -> list[str]:
    problems = []
    for index in range(max(len(old.calls), len(new.calls))):
        left = old.calls[index].as_tuple() if index < len(old.calls) else None
        right = new.calls[index].as_tuple() if index < len(new.calls) else None
        if left != right:
            problems.append(f"call #{index}: legacy {left} != flow {right}")
    if old_result != new_result:
        problems.append(f"result: legacy {old_result!r} != flow {new_result!r}")
    return problems


# --- tests ----------------------------------------------------------------


def test_mail_enter_migration_is_equivalent():
    old, old_result, new, new_result = _run_pair(MAIN_WHITE_THEN_MAIL)
    problems = _differences(old, old_result, new, new_result)
    assert problems == [], problems
    assert old_result is True and new_result is True
    # The call the first regression starved: entering the mail page from
    # page_main_white. Without it the loop never leaves the main page.
    assert [(c.frame, c.kind, c.name) for c in new.calls if c.name == "MAIL_ENTER_WHITE"] == [
        (0, "click", "MAIL_ENTER_WHITE")
    ]
    assert any(c.kind == "click" and c.name == "MAIL_MANAGE" for c in new.calls)
    assert [c.as_tuple() for c in new.calls] == [c.as_tuple() for c in old.calls]


def test_mail_enter_empty_mailbox_is_equivalent():
    old, old_result, new, new_result = _run_pair(MAIN_WHITE_THEN_EMPTY_MAIL)
    problems = _differences(old, old_result, new, new_result)
    assert problems == [], problems
    assert old_result is False and new_result is False
    assert any(c.kind == "click" and c.name == "MAIL_ENTER_WHITE" for c in new.calls)


def test_mail_enter_goto_main_white_timeout_is_equivalent():
    """The second regression: the 0.6 s timeout must still fire."""
    old, old_result, new, new_result = _run_pair(MAIN_WHITE_THEN_GOTO_TIMEOUT)
    problems = _differences(old, old_result, new, new_result)
    assert problems == [], problems
    assert old_result is False and new_result is False


def _manage_always_handled(ctx, args=None, **kw):
    """Regression shape 1: report handled whether or not anything happened."""
    if ctx.owner.appear_then_click(MAIL_MANAGE, offset=(30, 30), interval=3):
        ctx.params["_mail_has_mail"] = True
    return True


def _end_timer_rebuilt_every_frame(ctx, args=None, **kw):
    """Regression shape 2: the 0.6 s timer is dropped at the end of the check."""
    owner = ctx.owner
    if owner.appear(MAIL_BATCH_CLAIM, offset=(20, 20)):
        ctx.params["_mail_enter_result"] = True
        return True
    if owner.appear(MAIL_WHITE_EMPTY, offset=(20, 20)):
        ctx.params["_mail_enter_result"] = False
        return True
    if not ctx.params.get("_mail_has_mail") and owner.appear(GOTO_MAIN_WHITE, offset=(20, 20)):
        owner._mail_enter_timeout = owner._mail_enter_timeout or Timer(0.6, count=1).start()
        if owner._mail_enter_timeout.reached():
            ctx.params["_mail_enter_result"] = False
            return True
    owner._mail_enter_timeout = None
    return False


@pytest.mark.parametrize(
    "attribute, broken",
    [
        ("_mail_manage_click", _manage_always_handled),
        ("_mail_enter_end", _end_timer_rebuilt_every_frame),
    ],
)
def test_gate_detects_the_regression_it_was_built_for(monkeypatch, attribute, broken):
    """If these fail, the equivalence tests above prove nothing."""
    monkeypatch.setattr(mail_white, attribute, broken)
    problems = []
    for scenario in SCENARIOS:
        old, old_result, new, new_result = _run_pair(scenario)
        problems += _differences(old, old_result, new, new_result)
    assert problems, f"the gate accepted the broken {attribute}"
