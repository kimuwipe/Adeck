# touch.py  v2
# タッチパネル I2C ドライバ + スワイプ/タップ検出
# 秋月131295モジュール（CST816S / AXS5106L 互換）

from machine import I2C, Pin
import time

_TOUCH_ADDR = 0x15

_REG_GESTURE = 0x01
_REG_FINGERS = 0x02
_REG_XH      = 0x03
_REG_XL      = 0x04
_REG_YH      = 0x05
_REG_YL      = 0x06

# ジェスチャー定数
GESTURE_NONE       = "none"
GESTURE_TAP        = "tap"
GESTURE_SWIPE_LEFT = "swipe_left"
GESTURE_SWIPE_RIGHT= "swipe_right"
GESTURE_SWIPE_UP   = "swipe_up"
GESTURE_SWIPE_DOWN = "swipe_down"

# スワイプ判定閾値（px）
_SWIPE_THRESHOLD = 30


class TouchPanel:
    def __init__(self, i2c: I2C, irq_pin: int = None):
        self._i2c     = i2c
        self._addr    = _TOUCH_ADDR
        self._irq     = Pin(irq_pin, Pin.IN) if irq_pin is not None else None
        # タッチ開始座標（スワイプ判定用）
        self._start_x  = None
        self._start_y  = None
        self._start_ms = 0
        self._touching = False

    def _is_touched(self) -> bool:
        if self._irq is not None:
            return self._irq.value() == 0
        try:
            data = self._i2c.readfrom_mem(self._addr, _REG_FINGERS, 1)
            return data[0] > 0
        except OSError:
            return False

    def _read_xy(self) -> tuple[int, int] | None:
        try:
            data = self._i2c.readfrom_mem(self._addr, _REG_XH, 4)
            x = ((data[0] & 0x0F) << 8) | data[1]
            y = ((data[2] & 0x0F) << 8) | data[3]
            return (x, y)
        except OSError:
            return None

    def update(self) -> str:
        """
        タッチ状態を更新してジェスチャーを返す。
        タッチ中は GESTURE_NONE、離したタイミングでジェスチャーを返す。
        """
        touched = self._is_touched()

        if touched and not self._touching:
            # タッチ開始
            pos = self._read_xy()
            if pos:
                self._start_x  = pos[0]
                self._start_y  = pos[1]
                self._start_ms = time.ticks_ms()
                self._touching = True

        elif not touched and self._touching:
            # タッチ終了 → ジェスチャー判定
            self._touching = False
            if self._start_x is None:
                return GESTURE_NONE

            pos = self._read_xy()
            if pos is None:
                # 離した瞬間は座標取れないことがあるためタップとして扱う
                return GESTURE_TAP

            end_x, end_y = pos
            dx = end_x - self._start_x
            dy = end_y - self._start_y
            duration = time.ticks_diff(time.ticks_ms(), self._start_ms)

            # 移動量が小さければタップ
            if abs(dx) < _SWIPE_THRESHOLD and abs(dy) < _SWIPE_THRESHOLD:
                return GESTURE_TAP

            # 主移動方向でスワイプ判定
            if abs(dx) >= abs(dy):
                return GESTURE_SWIPE_RIGHT if dx > 0 else GESTURE_SWIPE_LEFT
            else:
                return GESTURE_SWIPE_DOWN if dy > 0 else GESTURE_SWIPE_UP

        return GESTURE_NONE


class TouchManager:
    """2枚のタッチパネルを独立管理"""
    def __init__(self, i2c0: I2C, i2c1: I2C,
                 irq0: int = None, irq1: int = None):
        self.touch0 = TouchPanel(i2c0, irq0)
        self.touch1 = TouchPanel(i2c1, irq1)

    def update_all(self) -> tuple[str, str]:
        """(LCD0のジェスチャー, LCD1のジェスチャー) を返す"""
        return (self.touch0.update(), self.touch1.update())
