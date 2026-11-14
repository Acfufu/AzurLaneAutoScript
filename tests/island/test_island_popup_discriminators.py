# Test doubles attach fake attributes/values to real classes, which is the point of a
# double but not something a type checker can verify.
# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
"""Popup discriminators pinned to the 2026-11-14 incident geometry.

- has_white_band must catch the purchase-success popup: a full-width white band
  below the item plate (runs y405..503 on both incident screenshots, error/
  1794643647547 and error/1794644074407).
- is_product_select_shown must catch the slot setup window (bright-blue dispatch
  button) that an emptied slot opens when re-clicked, and stay dark on every
  other surface (error/1794643049874).
"""
from types import SimpleNamespace

import numpy as np
import pytest

from module.island.production import PRODUCT_DISPATCH_BUTTON_AREA, IslandProduction
from module.island.ui import IslandUI

BLUE = (57, 189, 255)


def canvas():
    return np.zeros((720, 1280, 3), dtype=np.uint8)


def owner_with_image(cls, image):
    main = object.__new__(cls)
    main.device = SimpleNamespace(image=image)
    main.image_crop = lambda area, copy=False: image[area[1]:area[3], area[0]:area[2]]
    return main


def paint_purchase_success_popup(image):
    # White band y405..503 with the dark item art patch the real popups carry
    # (~70px wide, rows y405..455), matching the incident screenshots.
    image[405:503, :] = (255, 255, 255)
    image[405:455, 605:675] = (80, 120, 60)
    return image


def paint_product_select_window(image):
    x0, y0, x1, y1 = PRODUCT_DISPATCH_BUTTON_AREA
    image[y0:y1, x0:x1] = BLUE
    return image


class TestHasWhiteBand:
    def test_matches_purchase_success_popup(self):
        main = owner_with_image(IslandUI, paint_purchase_success_popup(canvas()))
        assert main.has_white_band() is True

    def test_dark_page_is_negative(self):
        main = owner_with_image(IslandUI, canvas())
        assert main.has_white_band() is False

    def test_product_select_window_is_negative(self):
        main = owner_with_image(IslandUI, paint_product_select_window(canvas()))
        assert main.has_white_band() is False


class TestIsProductSelectShown:
    def test_matches_slot_setup_window(self):
        main = owner_with_image(IslandProduction, paint_product_select_window(canvas()))
        assert main.is_product_select_shown() is True

    def test_dark_page_is_negative(self):
        main = owner_with_image(IslandProduction, canvas())
        assert main.is_product_select_shown() is False

    def test_purchase_success_popup_is_negative(self):
        main = owner_with_image(IslandProduction, paint_purchase_success_popup(canvas()))
        assert main.is_product_select_shown() is False

    def test_worker_select_title_is_negative(self):
        # The worker-select window carries a bright-blue title bar higher up;
        # only the dispatch button area may trigger the probe.
        image = canvas()
        image[144:202, 515:765] = (62, 193, 255)
        main = owner_with_image(IslandProduction, image)
        assert main.is_product_select_shown() is False


def test_partially_blue_probe_is_negative():
    # A window whose button is occluded (caption text over the probe) must not
    # trip the 2000/2400 pixel requirement.
    image = paint_product_select_window(canvas())
    x0, y0, x1, y1 = PRODUCT_DISPATCH_BUTTON_AREA
    image[y0:y1, x0:x1] = (40, 40, 40)  # dark strip across the whole probe
    main = owner_with_image(IslandProduction, image)
    assert main.is_product_select_shown() is False
    assert main.has_white_band() is False


@pytest.mark.parametrize('cls', [IslandUI, IslandProduction])
def test_white_band_probe_is_shared(cls):
    image = paint_purchase_success_popup(canvas())
    main = owner_with_image(cls, image)
    assert main.has_white_band() is True
