# Test doubles attach fake attributes/values to real classes, which is the point of a
# double but not something a type checker can verify.
# pyright: reportAttributeAccessIssue=false
"""Screenshot recognition coverage for island material collection."""

from module.island.assets import ISLAND_COLLECT_LOCATION_1, ISLAND_COLLECT_LOCATION_2
from module.island.collect import IslandCollect
from module.testing.screenshot import image

LOCATION_BUTTONS = (ISLAND_COLLECT_LOCATION_1, ISLAND_COLLECT_LOCATION_2)


class TestLocationSelectionJP:
    @image('island/collect/5081d7cc', server='jp')
    def test_both_collect_locations_unselected(self, main: IslandCollect):
        selected = [main.is_button_selected(button) for button in LOCATION_BUTTONS]
        unselected = main.collect_location_unselected_buttons()
        actual = {
            'selected': selected,
            'unselected': [button.area for button in unselected],
        }
        regions = [
            (button.area, f'collect location #{index} selected={selected[index]}')
            for index, button in enumerate(LOCATION_BUTTONS)
        ]
        main.device.review(actual, regions)
        assert actual == {
            'selected': [False, False],
            'unselected': [(431, 216, 608, 466), (672, 216, 849, 466)],
        }

    @image('island/collect/99fd267e', server='jp')
    def test_both_collect_locations_selected(self, main: IslandCollect):
        selected = [main.is_button_selected(button) for button in LOCATION_BUTTONS]
        unselected = main.collect_location_unselected_buttons()
        actual = {
            'selected': selected,
            'unselected': [button.area for button in unselected],
        }
        regions = [
            (button.area, f'collect location #{index} selected={selected[index]}')
            for index, button in enumerate(LOCATION_BUTTONS)
        ]
        main.device.review(actual, regions)
        assert actual == {
            'selected': [True, True],
            'unselected': [],
        }
