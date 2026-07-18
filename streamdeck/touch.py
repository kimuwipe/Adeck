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


# CST816 ジェスチャーレジスタ(0x01)の値 → ジェスチャー定数
# ※実機で確認したコード（ソフト回転済み・横向き画面基準）:
#   0x01=左→右, 0x02=右→左, 0x03=下→上, 0x04=上→下, 0x05=タップ
# 横スワイプでページ送りにするため:
#   右→左(0x02)=SWIPE_LEFT→次ページ / 左→右(0x01)=SWIPE_RIGHT→前ページ
_GESTURE_MAP = {
    0x01: GESTURE_SWIPE_RIGHT,
    0x02: GESTURE_SWIPE_LEFT,
    0x03: GESTURE_SWIPE_UP,
    0x04: GESTURE_SWIPE_DOWN,
    0x05: GESTURE_TAP,
}

_REG_MOTIONMASK = 0xEC   # bit1 EnConUD, bit2 EnConLR（スライドジェスチャー有効化）


class TouchPanel:
    def __init__(self, i2c: I2C, irq_pin: int = None):
        self._i2c     = i2c
        self._addr    = _TOUCH_ADDR
        self._irq     = Pin(irq_pin, Pin.IN) if irq_pin is not None else None
        # IC内蔵のジェスチャー判定（レジスタ0x01）を使う。前回値でエッジ検出。
        self._prev_gesture = 0
        self._enable_gestures()

    def _enable_gestures(self):
        """CST816 のスライドジェスチャー検出を有効化する。"""
        try:
            self._i2c.writeto_mem(self._addr, _REG_MOTIONMASK, bytes([0x06]))
        except OSError:
            pass

    def _read_gesture(self) -> int:
        try:
            return self._i2c.readfrom_mem(self._addr, _REG_GESTURE, 1)[0]
        except OSError:
            return 0

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
        """タッチICのジェスチャーレジスタ(0x01)を読み、認識されたジェスチャーを返す。
        同じ値が続く間は無反応にし、0→ジェスチャー のエッジで1回だけ返す
        （座標の連続取得に依存しないため、遅いポーリングでもスワイプが成立する）。"""
        g = self._read_gesture()
        if g == self._prev_gesture:
            return GESTURE_NONE
        self._prev_gesture = g
        return _GESTURE_MAP.get(g, GESTURE_NONE)


class TouchManager:
    """2枚のタッチパネルを独立管理"""
    def __init__(self, i2c0: I2C, i2c1: I2C,
                 irq0: int = None, irq1: int = None):
        self.touch0 = TouchPanel(i2c0, irq0)
        self.touch1 = TouchPanel(i2c1, irq1)

    def update_all(self) -> tuple[str, str]:
        """(LCD0のジェスチャー, LCD1のジェスチャー) を返す"""
        return (self.touch0.update(), self.touch1.update())
