# debug_led.py
# デバッグ用 LED 制御モジュール
#
# GP28 に LED（＋抵抗）を接続する
#   GP28 → 抵抗（330Ω程度）→ LED → GND
#
# 動作仕様
#   スイッチ入力  : 一定時間点灯（ワンショット）
#   エンコーダ回転: PWM輝度を変化させる（CW=明るく / CCW=暗く）

from machine import Pin, PWM
import time

LED_PIN      = 28      # デバッグLED ピン番号
LED_FREQ     = 1000    # PWM周波数 Hz
FLASH_MS     = 80      # スイッチ入力時の点灯時間 ms
ENC_STEP     = 4096    # エンコーダ1クリックあたりの輝度変化量（65535基準）
ENC_MIN      = 0       # 輝度最小値
ENC_MAX      = 65535   # 輝度最大値（最大輝度）
ENC_INIT     = 32768   # 起動時輝度（50%）


class DebugLED:
    def __init__(self):
        self._pwm       = PWM(Pin(LED_PIN, Pin.OUT))
        self._pwm.freq(LED_FREQ)
        self._duty      = ENC_INIT
        self._flash_end = 0        # ワンショット消灯タイミング（ticks_ms）
        self._flashing  = False
        self._pwm.duty_u16(0)     # 起動時は消灯

    # ---------- 外部インターフェース ----------

    def flash(self):
        """スイッチ入力時: FLASH_MS だけ最大輝度で点灯"""
        self._pwm.duty_u16(ENC_MAX)
        self._flash_end = time.ticks_ms() + FLASH_MS
        self._flashing  = True

    def enc_brighter(self):
        """エンコーダ CW: 輝度アップ"""
        self._duty = min(ENC_MAX, self._duty + ENC_STEP)
        self._apply()

    def enc_dimmer(self):
        """エンコーダ CCW: 輝度ダウン"""
        self._duty = max(ENC_MIN, self._duty - ENC_STEP)
        self._apply()

    def update(self):
        """メインループから毎周期呼ぶ。ワンショット消灯タイミングを管理"""
        if self._flashing:
            if time.ticks_diff(time.ticks_ms(), self._flash_end) >= 0:
                self._flashing = False
                self._apply()   # ワンショット終了 → エンコーダ輝度へ戻す

    def brightness_pct(self) -> int:
        """現在の輝度を 0〜100% で返す（ログ表示用）"""
        return round(self._duty / ENC_MAX * 100)

    # ---------- 内部 ----------
    def _apply(self):
        if not self._flashing:
            self._pwm.duty_u16(self._duty)
