# Test doubles attach fake attributes/values to real classes, which is the point of a
# double but not something a type checker can verify.
# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
"""claim_slot_reward backs out of the slot setup window an emptied slot opens.

Collecting a finished production empties the slot; the claim loop's re-click then
opens the product-select window, which matched none of the loop's checks and
starved it (GameStuckError, 2026-11-14 error/1794643049874). The second wait loop
must close it via the back arrow and carry on.
"""
from types import SimpleNamespace

import numpy as np
import pytest

import module.base.timer as timer_module
from module.island.assets import ISLAND_CLICK_SAFE_AREA, ISLAND_PRODUCTION_RERUN
from module.island.production import PRODUCT_DISPATCH_BUTTON_AREA, IslandProduction
from module.ui.page import page_island_manage
from module.ui_white.assets import BACK_ARROW_WHITE

BLUE = (57, 189, 255)
MANAGE = page_island_manage.check_button.name


class ClaimDevice:
    def __init__(self, frames):
        self.frames = list(frames)
        self.index = -1
        self.image = None
        self.now = 100.0
        self.screenshots = 0
        self.clicks = []

    def screenshot(self):
        self.screenshots += 1
        assert self.screenshots < 200, 'claim loop did not terminate'
        self.now += 0.5
        self.index += 1
        frame = self.frames[min(self.index, len(self.frames) - 1)]
        image = np.zeros((720, 1280, 3), dtype=np.uint8)
        if frame.get('product'):
            x0, y0, x1, y1 = PRODUCT_DISPATCH_BUTTON_AREA
            image[y0:y1, x0:x1] = BLUE
        self.image = image

    def click(self, button):
        self.clicks.append(getattr(button, 'name', str(button)))


def make_main(monkeypatch, frames):
    device = ClaimDevice(frames)
    monkeypatch.setattr(timer_module, 'time', lambda: device.now)
    main = object.__new__(IslandProduction)
    main.device = device
    intervals = {}

    def state():
        return device.frames[device.index] if device.index >= 0 else {}

    def appear(button, offset=(), interval=0, **_):
        name = getattr(button, 'name', str(button))
        if not state().get(name, False):
            intervals.pop(name, None)
            return False
        if interval and name in intervals and device.now - intervals[name] < interval:
            return False
        if interval:
            intervals[name] = device.now
        return True

    def appear_then_click(button, offset=(), interval=0, **_):
        if appear(button, offset=offset, interval=interval):
            device.click(button)
            return True
        return False

    main.appear = appear
    main.appear_then_click = appear_then_click

    def ui_page_appear(page, interval=0):
        return appear(page.check_button, interval=interval)

    def match_template_color(button, **_):
        return state().get(getattr(button, 'name', str(button)), False)

    main.ui_page_appear = ui_page_appear
    main.match_template_color = match_template_color
    main.interval_reset = lambda button: intervals.pop(getattr(button, 'name', str(button)), None)
    main.is_slot_finished = lambda button: True
    main.is_enter_window_shown = lambda: bool(state().get('enter'))
    main.handle_island_additional = lambda: False
    return main, device


def test_claim_backs_out_of_product_select_window(monkeypatch):
    # Claim reward -> back on the manage page the emptied slot is re-clicked ->
    # the product-select window opens and outlives the first loop's timeout ->
    # the second loop closes it via the back arrow and returns.
    frames = [
        {'ISLAND_PRODUCTION_RECEIVE': True},
        {MANAGE: True},
        *({'product': True, BACK_ARROW_WHITE.name: True} for _ in range(8)),
        {MANAGE: True},
    ]
    main, device = make_main(monkeypatch, frames)
    slot = SimpleNamespace(name='SLOT_402_3_0')

    assert main.claim_slot_reward(slot) is True
    assert device.clicks == ['ISLAND_PRODUCTION_RECEIVE', 'SLOT_402_3_0', BACK_ARROW_WHITE.name]
    assert ISLAND_CLICK_SAFE_AREA.name not in device.clicks
    assert ISLAND_PRODUCTION_RERUN.name not in device.clicks


def test_claim_still_closes_worker_select_window(monkeypatch):
    # The pre-existing path stays intact: the worker-select window (enter
    # window) closes on the safe-area click; the product-select branch must
    # not shadow it.
    frames = [
        {'ISLAND_PRODUCTION_RECEIVE': True},
        {MANAGE: True},
        *({'enter': True} for _ in range(8)),
        {MANAGE: True},
    ]
    main, device = make_main(monkeypatch, frames)
    slot = SimpleNamespace(name='SLOT_101_0_0')

    assert main.claim_slot_reward(slot) is True
    # The safe-area click repeats once per frame while the window stays up.
    assert device.clicks[:2] == ['ISLAND_PRODUCTION_RECEIVE', 'SLOT_101_0_0']
    assert ISLAND_CLICK_SAFE_AREA.name in device.clicks
    assert BACK_ARROW_WHITE.name not in device.clicks


@pytest.mark.parametrize('window_key', ['product', 'enter'])
def test_claim_window_cannot_loop_forever(monkeypatch, window_key):
    # Either window staying up forever must trip the screenshot guard instead
    # of silently spinning; a fixed window frame keeps the loop free of clicks,
    # so this exercises the bounded-device guard, not the branch logic.
    frames = [
        {'ISLAND_PRODUCTION_RECEIVE': True},
        {MANAGE: True},
        *({window_key: True, BACK_ARROW_WHITE.name: False} for _ in range(400)),
    ]
    main, _device = make_main(monkeypatch, frames)
    slot = SimpleNamespace(name='SLOT_X')

    with pytest.raises(AssertionError, match='claim loop did not terminate'):
        main.claim_slot_reward(slot)
