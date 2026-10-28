import os
import sys
import time

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from module.island.assets import ISLAND_ORDER_ACCEPT, ISLAND_ORDER_ACCEPT_URGENT
from module.island.order import IslandOrder


class FakeDevice:
    def __init__(self):
        self.clicks = []

    def click(self, button, *args, **kwargs):
        self.clicks.append(getattr(button, 'name', str(button)))


def fake_loop(iterations, interval=0.0):
    # Stands in for AbstractUI.loop: yields `iterations` frames (interval
    # simulates screenshot cost under client lag), then exhausts so the
    # submit_order for-else timeout branch fires.
    def loop(timeout=None):
        for _ in range(iterations):
            if interval:
                time.sleep(interval)
            yield None

    return loop


def make_shim(visible, loop, refuse_after=-1):
    # Skip IslandOrder.__init__ (needs a live config and device); submit_order
    # only touches device, loop and the match/appear shims below.
    calls = {'appear': 0, 'rejected': False}

    def appear(button, **kwargs):
        calls['appear'] += 1
        return refuse_after >= 0 and calls['appear'] > refuse_after

    shim = object.__new__(IslandOrder)
    shim.device = FakeDevice()
    shim.handle_island_additional = lambda: False
    shim.handle_island_order_level_up = lambda: False
    shim.appear = appear
    shim.match_template_color = lambda button, **kwargs: any(button is v for v in visible)
    shim.loop = loop
    shim.reject_order = lambda: calls.update(rejected=True)
    shim._audit_calls = calls
    return shim


def run(name, shim, is_urgent, expect_clicks, expect_result, expect_rejected=False):
    result = shim.submit_order(is_urgent=is_urgent)
    calls = shim._audit_calls
    ok = (len(shim.device.clicks) == expect_clicks
          and result == expect_result
          and calls['rejected'] == expect_rejected)
    print(f'=== {name}')
    print(f'  clicks={len(shim.device.clicks)} (expect {expect_clicks}) '
          f'result={result} (expect {expect_result}) '
          f'rejected={calls["rejected"]} (expect {expect_rejected}) '
          f'-> {"OK" if ok else "FAIL"}')
    return ok


def main():
    ok = True

    # Scenario 1: frozen frame, submit button visible for the whole loop
    # (2026-10-29 06:11 crash hit exactly this: 11 clicks / 66s). Loop
    # exhausts within the 3s confirm window -> timeout fallback, ONE click.
    ok &= run('frozen frame -> loop timeout',
              make_shim({ISLAND_ORDER_ACCEPT}, fake_loop(60)), False, 1, False)

    # Scenario 2: button stays visible while the loop keeps yielding past the
    # 3s confirm window -> assume-success fallback, ONE click.
    ok &= run('stuck button -> assume success',
              make_shim({ISLAND_ORDER_ACCEPT}, fake_loop(30, interval=0.6)),
              False, 1, True)

    # Scenario 3: urgent order, both accept buttons visible -> urgent success
    # fallback, ONE click.
    ok &= run('urgent stuck button -> urgent success',
              make_shim({ISLAND_ORDER_ACCEPT, ISLAND_ORDER_ACCEPT_URGENT},
                        fake_loop(20, interval=0.6)), True, 1, True)

    # Scenario 4: refuse toast lands in a frame after the first click ->
    # reject fallback, ONE click.
    ok &= run('refuse toast -> reject',
              make_shim({ISLAND_ORDER_ACCEPT}, fake_loop(20, interval=0.3),
                        refuse_after=1), False, 1, False, expect_rejected=True)

    print('ALL OK' if ok else 'FAILED')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
