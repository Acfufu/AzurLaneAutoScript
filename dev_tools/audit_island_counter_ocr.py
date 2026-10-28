import os
import sys
import types

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
from PIL import Image

from module.island.order import IslandOrder


def load_rgb(path):
    # Screenshots are full 1280x720 PNGs; load through PIL to get the same RGB
    # layout as device.image (cv2.imread would give BGR and skew color gates).
    return np.array(Image.open(path).convert('RGB'))


def scan_image(image):
    # Skip IslandOrder.__init__ (needs a live config and device); the scan and
    # its cached OCR grids only touch device.image.
    shim = object.__new__(IslandOrder)
    shim.device = types.SimpleNamespace(image=image)
    return shim.scan_current_order_requirements()


def main():
    for path in sys.argv[1:]:
        image = load_rgb(path)
        scan = scan_image(image)
        verdict = 'satisfied' if scan.readable and not scan.red_insufficient else 'NOT satisfied'
        print(f'\n=== {os.path.basename(path)}')
        print(f'  requirements={scan.requirements}')
        print(f'  readable={scan.readable} red_insufficient={scan.red_insufficient} -> {verdict}')


if __name__ == '__main__':
    main()
