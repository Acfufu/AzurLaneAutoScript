# Test doubles attach fake attributes/values to real classes, which is the point of a
# double but not something a type checker can verify.
# pyright: reportAttributeAccessIssue=false
"""IslandUI.ui_back forwards `additional` so in-flight popups get handled during back navigation.

After an island shop purchase the success popup can render while ui_back is already
waiting for the target page; without an additional handler that wait starves
(GameStuckError, 2026-11-14 error/1794644074407).
"""
from module.island.ui import IslandUI
from module.ui_white.assets import BACK_ARROW_WHITE


def test_ui_back_forwards_additional():
    ui = object.__new__(IslandUI)
    captured = {}

    def fake_ui_click(**kwargs):
        captured.update(kwargs)
        return 'done'

    ui.ui_click = fake_ui_click
    assert ui.ui_back(check_button='CHECK', additional='ADDITIONAL') == 'done'
    assert captured['click_button'] is BACK_ARROW_WHITE
    assert captured['check_button'] == 'CHECK'
    assert captured['additional'] == 'ADDITIONAL'


def test_ui_back_additional_defaults_to_none():
    ui = object.__new__(IslandUI)
    captured = {}
    ui.ui_click = lambda **kwargs: captured.update(kwargs)
    ui.ui_back(check_button='CHECK')
    assert captured['additional'] is None
    assert captured['appear_button'] is None
