from collections import namedtuple
from datetime import datetime, timedelta

import cv2
import numpy as np
from jellyfish import levenshtein_distance

import module.config.server as server
from module.base.button import Button, ButtonGrid
from module.base.decorator import cached_property
from module.base.timer import Timer
from module.base.utils import color_similarity_2d, crop
from module.config.utils import get_server_next_update
from module.island.assets import *  # noqa: F403  (data-bundle star import)
from module.island.data import DIC_ISLAND_ITEM, DIC_ISLAND_SEASON_ORDER
from module.island.ui import IslandUI
from module.island.utils import (
    get_active_island_activity_ids,
    get_order_effective_stock,
    load_hard_floor_items,
    normalize_item_keys,
)
from module.island_handler.recipe import IslandReversedDigitCounter
from module.island_handler.restaurant_config import get_menu_reserve_items
from module.logger import logger
from module.ocr.ocr import Duration, Ocr
from module.ui.page import page_island_order

COLOR_REGULAR = (57, 189, 255)  # Blue
COLOR_REGULAR_COOLDOWN = (173, 227, 255)  # Light Blue
COLOR_SEASON = (255, 173, 27)  # Yellow
COLOR_URGENT = (135, 122, 239)  # Purple
# COLOR_EASY = (114, 225, 167)  # Green
# COLOR_HARD = (237, 128, 102)  # Red
EMPTY_SEASON_ORDER_ID = 0
# Regular orders expire at server update. Within this window a reject-cooldown
# cycle (~100min) would outlive the order, so submit using protected stock instead.
ORDER_EXPIRE_FORCE_WINDOW = timedelta(hours=2)
# Counter-area ink (pixels near the letter color) under which a requirement row
# counts as empty, matching the 30-pixel red gate in
# IslandReversedDigitCounter.pre_process.
REQUIREMENT_ROW_EMPTY_INK = 30
# Red pixels above which the row's stock text is red, i.e. the row is short.
REQUIREMENT_ROW_RED_INK = 30

# Scan result of the requirement panel. readable=False means rows were covered
# by popups or still rendering, so the order must never be submitted on it;
# red_insufficient means the game paints a row's stock red, i.e. short.
OrderRequirementScan = namedtuple(
    'OrderRequirementScan', ['requirements', 'readable', 'red_insufficient'], defaults=({}, True, False))


def get_circles(image, color, inner_radius, outer_radius):
    """
    First use color_similarity_2d to create a mask of the image, then
    Use cv2.HoughCircles to detect circles in the image,
    and return the circles that are detected.
    """
    mask = color_similarity_2d(image, color=color)
    cv2.threshold(mask, 240, 255, cv2.THRESH_BINARY, dst=mask)
    blurred = cv2.GaussianBlur(mask, (7, 7), sigmaX=1.5, sigmaY=1.5)
    circles = cv2.HoughCircles(blurred, cv2.HOUGH_GRADIENT, dp=1, minDist=2*inner_radius,
                               param1=100, param2=30, minRadius=inner_radius-2, maxRadius=outer_radius+2)
    if circles is not None:
        circles = circles[0]
    else:
        circles = []
    return circles


def get_season_order_id(requirements, current_time=None):
    required_items = {
        item_id: counter[1] if isinstance(counter, (list, tuple)) and len(counter) > 1 else counter
        for item_id, counter in requirements.items()
    }
    matches = [
        (order_id, order)
        for order_id, order in DIC_ISLAND_SEASON_ORDER.items()
        if required_items == order.get('request', {})
    ]
    if not matches:
        logger.warning(f'Cannot find season order id for requirements: {requirements}')
        return None
    activity_list = get_active_island_activity_ids(current_time)
    active_matches = [
        (order_id, order)
        for order_id, order in matches
        if order.get('activity_id') in activity_list
    ]
    if len(active_matches) == 1:
        order_id, order = active_matches[0]
        historical_ids = [candidate_id for candidate_id, _ in matches if candidate_id != order_id]
        if historical_ids:
            logger.info(
                f'Season order requirements matched current order {order_id} '
                f'(activity {order.get("activity_id", 0)}); ignored historical matches '
                f'{historical_ids}'
            )
        return order_id
    if len(active_matches) > 1:
        logger.warning(
            f'Multiple active season orders match requirements {requirements}: '
            f'{[order_id for order_id, _ in active_matches]}'
        )
        return active_matches[0][0]
    if len(matches) > 1:
        logger.warning(
            f'No active season order uniquely matches requirements {requirements}; '
            f'falling back to historical order {matches[0][0]} among '
            f'{[order_id for order_id, _ in matches]}'
        )
    return matches[0][0]


class IslandOrder(IslandUI):
    def detect_orders(self, color=COLOR_REGULAR):
        """
        Returns:
            (List[Button]): A list of Button objects that represent the detected orders in the page."""
        inner_radius = 44
        outer_radius = 52
        circles = get_circles(self.device.image, color, inner_radius, outer_radius)
        button_list = []
        for _index, circle in enumerate(circles):
            x, y, _ = circle
            x = int(x)
            y = int(y)
            detect_area = (x - outer_radius, y - outer_radius, x + outer_radius, y + outer_radius)
            click_area = (x - inner_radius, y - inner_radius, x + inner_radius, y + inner_radius)
            button = Button(area=detect_area, color=(), button=click_area, name=f'ORDER_AT_{x}_{y}')
            button_list.append(button)
        return button_list

    @property
    def requirement_grid(self):
        return ButtonGrid(
            origin=(884, 240),
            delta=(0, 79),
            button_shape=(334, 78),
            grid_shape=(1, 3),
            name="REQUIREMENT_GRID"
        )

    @property
    def requirement_name_grid(self):
        if server.server == 'en':
            name_grid = self.requirement_grid.crop((81, 12, 328, 40))
        else:
            name_grid = self.requirement_grid.crop((168, 12, 328, 40))
        return name_grid

    @property
    def requirement_counter_grid(self):
        if server.server == 'en':
            counter_grid = self.requirement_grid.crop((238, 44, 326, 70))
        else:
            counter_grid = self.requirement_grid.crop((238, 44, 327, 65))
        return counter_grid

    @cached_property
    def requirement_name_ocr(self):
        if server.server == 'jp':
            lang = 'jp'
        elif server.server == 'tw':
            lang = 'tw'
        else:
            lang = 'cnocr'
        return Ocr(self.requirement_name_grid.buttons, lang=lang, letter=(57, 59, 61), threshold=160, name='REQUIREMENTS_NAME_OCR')

    @cached_property
    def requirement_counter_ocr(self):
        return IslandReversedDigitCounter(self.requirement_counter_grid.buttons, lang='cnocr',
                                          letter=(57, 59, 61), sub_letter=(253, 97, 96),
                                          threshold=160, sub_threshold=160, background_color=None,
                                          name='REQUIREMENTS_COUNTER_OCR')

    def item_name_to_item_id(self, name):
        if name == '':
            return None
        if server.server == 'jp':
            # While we have 果樹園二重奏 and 朝光活力コンビ, the problem of カニ as 力二 is worse,
            # so we replace 力 with カ before matching,
            # which can fix most of the misrecognition without causing new issues.
            name = name.replace('二', 'ニ').replace('力', 'カ')
        min_distance = float('inf')
        corrected_name = None
        corrected_id = None
        item_lists = DIC_ISLAND_ITEM.keys()

        for item in item_lists:
            item_name = DIC_ISLAND_ITEM[item]['name'][server.server]
            distance = levenshtein_distance(name, item_name)
            if distance < min_distance:
                min_distance = distance
                corrected_name = item_name
                corrected_id = item

        if name != corrected_name:
            logger.info(f'Recipe product name OCR result "{name}" corrected to "{corrected_name}" with distance {min_distance}')
        return corrected_id

    def scan_current_order_requirements(self):
        """
        Scan the requirement rows on the current panel.

        Returns:
            OrderRequirementScan: requirements and whether the scan can be
            trusted. Rows covered by popups or still rendering make the scan
            unreadable so the order is never submitted on guesses; rows with
            red stock text are insufficient regardless of the digits read.
        """
        name_ocr = self.requirement_name_ocr
        counter_ocr = self.requirement_counter_ocr
        names = name_ocr.ocr(self.device.image)
        ids = [self.item_name_to_item_id(name) for name in names]
        counters = counter_ocr.ocr(self.device.image)
        requirements = {}
        readable = True
        red_insufficient = False
        for row, (id, counter) in enumerate(zip(ids, counters)):
            image = crop(self.device.image, counter_ocr.buttons[row])
            dark = color_similarity_2d(image, color=counter_ocr.letter)
            red = color_similarity_2d(image, color=counter_ocr.sub_letter)
            dark = int((dark >= counter_ocr.threshold).sum())
            red = int((red >= counter_ocr.sub_threshold).sum())
            if tuple(counter) == (0, 0, 0):
                if dark > REQUIREMENT_ROW_EMPTY_INK:
                    # Ink in the counter area but no digits read: the row is
                    # covered by a popup or still rendering.
                    logger.warning(f'Requirement row {row + 1} has unreadable counter text, treat scan as unreadable')
                    readable = False
                # Otherwise a genuinely empty row: orders list 1-3 items and
                # OCR noise on empty rows (e.g. a phantom item name) is dropped.
                continue
            if id is None:
                logger.warning(f'Requirement row {row + 1} has counter {counter} but no item name, treat scan as unreadable')
                readable = False
                continue
            requirements[id] = counter
            if red > REQUIREMENT_ROW_RED_INK:
                # The game paints the stock red iff the row is short; trust
                # the color over the digits.
                logger.warning(f'Requirement row {row + 1} stock is red: {counter}, insufficient regardless of digits')
                red_insufficient = True
        if not requirements and readable:
            # Orders always list at least one item; an all-empty read means
            # the whole panel was covered or still rendering.
            logger.warning('No requirement row read, treat scan as unreadable')
            readable = False
        return OrderRequirementScan(requirements=requirements, readable=readable, red_insufficient=red_insufficient)

    def get_order_remain_time(self, order_button: Button):
        time_button = order_button.crop((10, 119, 100, 145))
        print(f'OCR area: {time_button.area}')
        time_ocr = Duration(time_button, name='ORDER_REMAIN_TIME_OCR')
        remain_time = time_ocr.ocr(self.device.image)
        logger.info(f'Order remain time: {remain_time}')
        return remain_time

    @cached_property
    def hard_floor(self):
        hard_floor_items_text = load_hard_floor_items(
            self.config.cross_get("IslandProduction.IslandProduction.HardFloorItems", "")
        )
        return normalize_item_keys(hard_floor_items_text)

    @cached_property
    def reserve(self):
        return get_menu_reserve_items(self.config)

    def is_order_satisfied(self, order_requirements, is_urgent=False, is_season=False, force=False):
        for item, counter in order_requirements.items():
            stock, required, _ = counter
            hard_floor = self.hard_floor.get(item, 0)
            priority = is_urgent or is_season or force
            effective_stock = get_order_effective_stock(
                stock,
                hard_floor,
                reserve=self.reserve.get(item, 0),
                priority=priority,
            )
            if required > effective_stock:
                logger.warning(
                    f'Item {item} does not meet the requirement: stock {stock}, '
                    f'hard floor {hard_floor}, reserve {self.reserve.get(item, 0)}, '
                    f'effective stock {effective_stock}, required {required}'
                )
                return False
        return True

    def handle_island_order_level_up(self):
        if self.appear(ISLAND_ORDER_LEVEL_UP, offset=(20, 20), interval=1):
            logger.info('Detected island order level up')
            self.device.click(ISLAND_CLICK_SAFE_AREA)
            return True
        return False

    def click_order(self, order_button, is_urgent=False):
        click_timer = Timer(1, count=3)
        for _ in self.loop(timeout=5, skip_first=False):
            if click_timer.reached():
                self.device.click(order_button)
                click_timer.reset()
                continue
            if (is_urgent and self.appear(ISLAND_ORDER_ACCEPT, offset=(20, 20))) or \
                    (not is_urgent and self.appear(ISLAND_ORDER_ACCEPT_URGENT, offset=(20, 20))):
                logger.info('requirement page does not match, should click order button again')
                click_timer.reset()
                continue
            if self.appear(ISLAND_ORDER_REQUIREMENTS_CHECK, offset=(0, 20)):
                logger.info('Clicked order button, requirements page appeared')
                break
            if self.appear(ISLAND_ORDER_COOLDOWN_SPEED_UP, offset=(20, 20)):
                logger.info('Clicked order button, cooldown speed up page appeared')
                break
        else:
            logger.info('click timer timeout, assuming requirements page appeared')

    def submit_order(self, is_urgent=False):
        if is_urgent:
            submit_button = ISLAND_ORDER_ACCEPT_URGENT
        else:
            submit_button = ISLAND_ORDER_ACCEPT
        confirm_timer = Timer(3, count=6).start()
        clicked = False
        for _ in self.loop(timeout=20):
            if self.handle_island_additional():
                clicked = True
                confirm_timer.reset()
                continue
            # Game refuses the submit with a "资源不够啦" toast when stock run
            # out between the satisfy check and the submit (requirement OCR can
            # misread); clicking on would never confirm, reject instead.
            if self.appear(ISLAND_ORDER_SUBMIT_REFUSED, offset=(20, 20), interval=2):
                logger.warning('Order submit refused: insufficient resources, reject it instead')
                self.reject_order()
                return False
            if self.handle_island_order_level_up():
                confirm_timer.reset()
                continue
            if not clicked and self.match_template_color(submit_button, offset=(20, 20), interval=1):
                self.device.click(submit_button)
                confirm_timer.reset()
                continue
            if not confirm_timer.reached():
                continue
            if self.match_template_color(ISLAND_ORDER_BACKGROUND, offset=(20, 20)):
                logger.info('Submit success')
                return True
            # after urgent order submission, cursor may jump to normal order and the normal order submit button is visible
            if is_urgent and self.match_template_color(ISLAND_ORDER_ACCEPT, offset=(20, 20)):
                logger.info('Urgent order submit success')
                return True
            if not is_urgent and self.match_template_color(ISLAND_ORDER_COOLDOWN_SPEED_UP, offset=(20, 20)):
                logger.info('Previous order submitted, wait for next order to appear')
                continue
            if clicked and self.match_template_color(ISLAND_ORDER_ACCEPT, offset=(20, 20)):
                logger.info('Confirm timer timeout, assuming submit success')
                return True
        else:
            logger.warning('Submit order timeout, something may be wrong')
            return False

    @property
    def cooldown_time_ocr(self):
        time_ocr = Duration(ISLAND_ORDER_COOLDOWN_REMAIN_TIME, letter=(57, 59, 61), name='ORDER_COOLDOWN_REMAIN_TIME_OCR')
        return time_ocr

    def reject_order(self):
        for _ in self.loop():
            if self.appear_then_click(ISLAND_ORDER_REJECT, offset=(20, 20), interval=1):
                continue
            if self.appear(ISLAND_ORDER_COOLDOWN_SPEED_UP, offset=(20, 20)):
                break
        cooldown_remain_time = self.cooldown_time_ocr.ocr(self.device.image)
        logger.info(f'Order cooldown remain time: {cooldown_remain_time}')
        return cooldown_remain_time

    next_runtime = []
    update_production_plan = False

    def update_stuck_season_order(self, order_id):
        order_id = order_id or EMPTY_SEASON_ORDER_ID
        previous_id = self.config.cross_get("IslandOrder.IslandOrder.StuckSeasonOrderId", EMPTY_SEASON_ORDER_ID)
        if order_id != previous_id:
            logger.info(f'Updating stuck season order id from {previous_id} to {order_id}')
            self.config.cross_set("IslandOrder.IslandOrder.StuckSeasonOrderId", order_id)
            self.update_production_plan = True

    def execute_order(self, order_button, is_urgent=False, is_season=False):
        """
        Returns:
            (bool): True if the order is dealt.
        """
        self.handle_island_additional()
        self.handle_info_bar()
        self.click_order(order_button, is_urgent=is_urgent)
        if self.appear(ISLAND_ORDER_COOLDOWN_SPEED_UP, offset=(20, 20)):
            logger.warning('Order is in cooldown, cannot submit')
            remain_time = self.cooldown_time_ocr.ocr(self.device.image)
            next_runtime = datetime.now() + remain_time
            self.next_runtime.append(next_runtime)
            return False
        scan = self.scan_current_order_requirements()
        if not scan.readable:
            # The panel can be covered by popups or still rendering when the
            # scan lands (observed 2026-10-29: panel content lagged the panel
            # frame under client lag and a submit on the stale content got
            # refused); wait once and re-scan before deciding.
            logger.info('Requirement panel unreadable, wait 1s and scan again')
            self.device.sleep(1)
            self.device.screenshot()
            scan = self.scan_current_order_requirements()
        force = not is_urgent and not is_season and (
            get_server_next_update(self.config.Scheduler_ServerUpdate) - datetime.now() <= ORDER_EXPIRE_FORCE_WINDOW
        )
        if force:
            logger.info('Regular order is about to expire at server update, submit ignoring protected stock')
        satisfied = scan.readable and not scan.red_insufficient and self.is_order_satisfied(
            scan.requirements, is_urgent=is_urgent, is_season=is_season, force=force)
        if satisfied:
            return self.submit_order(is_urgent=is_urgent)
        else:
            if not scan.readable:
                logger.warning('Order requirements unreadable, treat as not satisfied')
            else:
                logger.warning('Order requirements not satisfied due to low stock')
            if is_urgent:
                logger.warning('Urgent order can only be delayed')
                remain_time = self.get_order_remain_time(order_button)
                if remain_time == timedelta(0):
                    logger.warning('Urgent order remain time ocr error, default to 8 hours')
                    remain_time = timedelta(hours=8)
                else:
                    logger.warning(f'Order remain time: {remain_time}')
                next_runtime = datetime.now() + remain_time
                self.next_runtime.append(next_runtime)
                return False
            elif is_season:
                if not scan.readable:
                    # Requirements are unreliable, marking a wrong season
                    # order stuck would trigger a pointless replan.
                    logger.warning('Season order requirements unreadable, keep stuck season order id unchanged')
                    return False
                logger.warning('Season order can only be abandoned, skip this order')
                stuck_season_order_id = get_season_order_id(scan.requirements)
                self.update_stuck_season_order(stuck_season_order_id)
                return False
            else:
                remain_time = self.reject_order()
                next_runtime = datetime.now() + remain_time
                self.next_runtime.append(next_runtime)
                return True

    regular_orders = []
    regular_cooldown_orders = []
    urgent_orders = []
    season_orders = []

    def detect_all_orders(self):
        self.regular_cooldown_orders = self.detect_orders(color=COLOR_REGULAR_COOLDOWN)
        self.regular_orders = self.detect_orders(color=COLOR_REGULAR)
        for order in self.regular_orders:
            for cooldown_order in self.regular_cooldown_orders:
                if np.linalg.norm(np.array(order.button) - np.array(cooldown_order.button)) < 10:
                    self.regular_orders.remove(order)
                    break
        self.urgent_orders = self.detect_orders(color=COLOR_URGENT)
        if len(self.urgent_orders) > 1:
            logger.warning(f'Multiple urgent orders detected, which is unexpected: {len(self.urgent_orders)}')
            self.urgent_orders = self.urgent_orders[:1]
        self.season_orders = self.detect_orders(color=COLOR_SEASON)
        if len(self.season_orders) > 1:
            logger.warning(f'Multiple season orders detected, which is unexpected: {len(self.season_orders)}')
            self.season_orders = self.season_orders[:1]

    def run_any_order(self):
        for order in self.urgent_orders:
            if self.execute_order(order, is_urgent=True, is_season=False):
                logger.info('Urgent order submitted')
            else:
                logger.info('Urgent order delayed')
        for order in self.regular_orders:
            if self.execute_order(order, is_urgent=False, is_season=False):
                logger.info('Regular order submitted')
                return True
            else:
                logger.info('Regular order rejected')
        for order in self.season_orders:
            if self.execute_order(order, is_urgent=False, is_season=True):
                logger.info('Season order submitted')
                return True
            else:
                logger.info('Season order abandoned')
        return False

    def run(self):
        self.ui_ensure(page_island_order)
        self.next_runtime = []
        self.update_production_plan = False
        for _ in self.loop():
            self.detect_all_orders()
            if self.run_any_order():
                continue
            else:
                logger.info('No order can be submitted')
                break
        if not self.season_orders:
            self.update_stuck_season_order(EMPTY_SEASON_ORDER_ID)
        if self.update_production_plan:
            logger.info('Production plan needs to be updated due to stuck season order change')
            from module.island_handler.production_planner import IslandProductionPlanner
            IslandProductionPlanner(self.config, self.device).run()
            self.update_production_plan = False
        for order in self.regular_cooldown_orders:
            remain_time = self.get_order_remain_time(order)
            if remain_time == timedelta(0):
                logger.warning('Order remain time ocr error, click to check')
                self.click_order(order)
                remain_time = self.cooldown_time_ocr.ocr(self.device.image)
            next_runtime = datetime.now() + remain_time
            self.next_runtime.append(next_runtime)
        # The speed-up coupon dialog can surface around a reject (observed
        # 2026-10-29: it opened by itself under client lag after the last
        # reject) and dims the whole screen, so leaving it open makes the
        # next task's ui_ensure die with GamePageUnknownError.
        for _ in self.loop(timeout=6):
            if self.appear(page_island_order.check_button, offset=(20, 20)):
                break
            if self.handle_island_additional():
                continue
            self.device.click(ISLAND_CLICK_SAFE_AREA)
        else:
            logger.warning('Order page still not recognizable at task end, next task should recover via popups')
        if self.next_runtime:
            next_runtime = min(self.next_runtime)
            logger.info(f'Next order runtime: {next_runtime}')
            self.config.task_delay(target=next_runtime, server_update=True)
        else:
            self.config.task_delay(server_update=True)
