# encoder.py
# ロータリーエンコーダ（EC11）ドライバ
# A/B信号をGPIOで読み取り、回転方向を検出

from machine import Pin
import time

# エンコーダのGPIOピン定義（config.pyのピンアサインに対応）
ENCODER_PINS = [
    (8,  9),   # ENC0: A=GP8,  B=GP9
    (10, 11),  # ENC1: A=GP10, B=GP11
    (12, 13),  # ENC2: A=GP12, B=GP13
    (14, 15),  # ENC3: A=GP14, B=GP15
]

# 何シグナル（クォードラチャ遷移）で1反応にするかの分周数。
# EC11は1ノッチ＝4エッジが一般的。ループ高速化で取りこぼしが無くなったため、
# 4 で「1ノッチ＝1反応」になる。大きいほど鈍い / 小さいほど敏感。
# 敏感にしたい:3 / さらに鈍く:6・8
STEPS_PER_STEP = 4

# 回転方向の反転（Trueで CW↔CCW を入れ替え）
REVERSE_DIRECTION = True

# 状態遷移テーブル（グレイコードデコード）
# (prev_AB, curr_AB) -> direction: +1=CW, -1=CCW, 0=無効
_TRANSITION = {
    (0b00, 0b01): +1,
    (0b01, 0b11): +1,
    (0b11, 0b10): +1,
    (0b10, 0b00): +1,
    (0b00, 0b10): -1,
    (0b10, 0b11): -1,
    (0b11, 0b01): -1,
    (0b01, 0b00): -1,
}

class Encoder:
    def __init__(self, pin_a: int, pin_b: int):
        self._a = Pin(pin_a, Pin.IN)   # 外付けプルアップ済みのためPULL_UPなし
        self._b = Pin(pin_b, Pin.IN)
        self._prev = self._read_ab()
        self._accum = 0                 # 分周用の累積カウント
        self._last_time = time.ticks_ms()

    def _read_ab(self) -> int:
        return (self._a.value() << 1) | self._b.value()

    def update(self) -> int:
        """
        回転量を返す（+1=CW1クリック, -1=CCW1クリック, 0=変化なし）
        デバウンス：5ms以内の連続変化は無視。
        STEPS_PER_STEP シグナルたまるごとに1反応（過敏さ抑制）。
        """
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_time) < 5:
            return 0

        curr = self._read_ab()
        if curr == self._prev:
            return 0

        direction = _TRANSITION.get((self._prev, curr), 0)
        self._prev = curr

        if direction == 0:
            return 0

        if REVERSE_DIRECTION:
            direction = -direction

        self._last_time = now
        # 方向転換したら累積をリセット（逆回転にすぐ追従できるように）
        if self._accum != 0 and (self._accum > 0) != (direction > 0):
            self._accum = 0
        self._accum += direction

        if self._accum >= STEPS_PER_STEP:
            self._accum = 0
            return 1
        if self._accum <= -STEPS_PER_STEP:
            self._accum = 0
            return -1
        return 0


class EncoderManager:
    """4つのエンコーダをまとめて管理"""
    def __init__(self):
        self._encoders = [Encoder(a, b) for a, b in ENCODER_PINS]

    def update_all(self) -> list[int]:
        """
        各エンコーダの回転量リストを返す
        例: [0, +1, 0, -1] → ENC1がCW1クリック、ENC3がCCW1クリック
        """
        return [enc.update() for enc in self._encoders]
