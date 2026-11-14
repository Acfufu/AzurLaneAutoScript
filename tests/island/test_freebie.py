# Test doubles attach fake attributes/values to real classes, which is the point of a
# double but not something a type checker can verify.
# pyright: reportAttributeAccessIssue=false
"""Screenshot recognition coverage for the island daily freebie notice."""

from module.island.assets import ISLAND_FREEBIE_AVAILABLE, ISLAND_FREEBIE_UNAVAILABLE
from module.island.freebie import IslandFreebie
from module.testing.screenshot import image


class TestFreebieNoticeJP:
    @image('island/freebie/c6d615b9', server='jp')
    def test_available_freebie_notice(self, main: IslandFreebie):
        actual = {'available': main.island_freebie_notice_appear()}
        main.device.review(actual, [
            (ISLAND_FREEBIE_AVAILABLE.area, 'freebie notice available'),
        ])
        assert actual == {'available': True}

    @image('island/freebie/f62779cb', server='jp')
    def test_unavailable_freebie_notice(self, main: IslandFreebie):
        actual = {'available': main.island_freebie_notice_appear()}
        main.device.review(actual, [
            (ISLAND_FREEBIE_UNAVAILABLE.area, 'freebie notice unavailable'),
        ])
        assert actual == {'available': False}
