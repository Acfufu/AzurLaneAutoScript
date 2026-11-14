# Test doubles attach fake attributes/values to real classes, which is the point of a
# double but not something a type checker can verify.
# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
"""The buy loop must wait out the purchase success popup before honoring the back arrow.

The popup renders ~2s after ISLAND_SHOP_BUY_CONFIRM is clicked, and the back arrow
reappears before it; breaking on the back arrow immediately left the popup starving
every wait in the caller's ui_back (GameStuckError, 2026-11-14 error/1794643647547
and error/1794644074407).
"""
from types import SimpleNamespace

import module.base.timer as timer_module
from module.island_handler.shop import IslandShop


class BuyDevice:
    """Frames are dicts keyed by asset name; 'popup' means the success popup is up."""

    def __init__(self, frames):
        self.frames = list(frames)
        self.index = -1
        self.image = None
        self.now = 100.0
        self.screenshots = 0
        self.clicks = []

    def screenshot(self):
        self.screenshots += 1
        assert self.screenshots < 200, 'buy loop did not terminate'
        self.now += 0.5
        self.index += 1
        self.image = self.frames[min(self.index, len(self.frames) - 1)]

    def click(self, button):
        self.clicks.append(getattr(button, 'name', str(button)))


def make_shop(monkeypatch, frames):
    device = BuyDevice(frames)
    monkeypatch.setattr(timer_module, 'time', lambda: device.now)
    shop = object.__new__(IslandShop)
    shop.device = device
    intervals = {}

    def state():
        if device.index < 0:
            return {}
        return device.frames[min(device.index, len(device.frames) - 1)]

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

    shop.appear = appear
    shop.appear_then_click = appear_then_click
    shop.interval_reset = lambda button: intervals.pop(getattr(button, 'name', str(button)), None)
    shop.island_shop_buy_ensure_amount = lambda amount: None
    shop.handle_island_additional = lambda: bool(state().get('popup'))
    return shop, device


def run_buy(monkeypatch, frames):
    shop, device = make_shop(monkeypatch, frames)
    item = SimpleNamespace(name='ISLAND_SHOP_ITEM_BUTTON')
    shop.island_shop_buy_execute(item, 9)
    return device


def test_break_waits_for_the_late_success_popup(monkeypatch):
    # Dialog open -> confirm clicked -> back arrow reappears while the popup has
    # not rendered yet -> popup handled at ~3.5s -> back arrow honored.
    frames = [
        {'ISLAND_SHOP_BUY_CHECK': True},
        {'ISLAND_SHOP_BUY_CONFIRM': True},
        {'BACK_ARROW_WHITE': True},
        {'BACK_ARROW_WHITE': True},
        {'BACK_ARROW_WHITE': True},
        {'BACK_ARROW_WHITE': True},
        {'BACK_ARROW_WHITE': True},
        {'popup': True},
        {'BACK_ARROW_WHITE': True},
    ]
    device = run_buy(monkeypatch, frames)

    # The regression: old code broke on the first back-arrow frame (frame 2) and
    # never consumed the popup frame. The gate must hold past it.
    assert device.index >= 8, 'buy loop broke before the success popup was handled'
    assert device.clicks == ['ISLAND_SHOP_BUY_CONFIRM']


def test_break_eventually_happens_without_any_popup(monkeypatch):
    # No popup at all (popup branch never fires): the grace window must expire
    # instead of looping forever.
    frames = [
        {'ISLAND_SHOP_BUY_CHECK': True},
        {'ISLAND_SHOP_BUY_CONFIRM': True},
        *({'BACK_ARROW_WHITE': True} for _ in range(12)),
    ]
    device = run_buy(monkeypatch, frames)

    assert device.clicks == ['ISLAND_SHOP_BUY_CONFIRM']
    assert device.index >= 6, 'grace window did not hold the exit'


def test_repeated_confirm_clicks_extend_the_grace_window(monkeypatch):
    # Confirm click needs a retry (first click not registered): the window
    # restarts from the last click instead of letting a stale popup through.
    frames = [
        {'ISLAND_SHOP_BUY_CHECK': True},
        {'ISLAND_SHOP_BUY_CONFIRM': True},
        {'ISLAND_SHOP_BUY_CONFIRM': True, 'BACK_ARROW_WHITE': True},
        {'ISLAND_SHOP_BUY_CONFIRM': True, 'BACK_ARROW_WHITE': True},
        {'ISLAND_SHOP_BUY_CONFIRM': True, 'BACK_ARROW_WHITE': True},
        {'ISLAND_SHOP_BUY_CONFIRM': True, 'BACK_ARROW_WHITE': True},
        {'ISLAND_SHOP_BUY_CONFIRM': True, 'BACK_ARROW_WHITE': True},
        {'ISLAND_SHOP_BUY_CONFIRM': True, 'BACK_ARROW_WHITE': True},
        *({'BACK_ARROW_WHITE': True} for _ in range(10)),
    ]
    device = run_buy(monkeypatch, frames)

    # First click ~101.0s, retry ~104.0s once the 3s click interval expires;
    # the break may only happen 3s after the retry (~107.5s on this clock).
    assert device.clicks == ['ISLAND_SHOP_BUY_CONFIRM', 'ISLAND_SHOP_BUY_CONFIRM']
    assert device.now >= 107.0, 'grace window did not restart after the confirm retry'
