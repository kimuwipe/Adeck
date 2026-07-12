# test_encoder.py
# エンコーダ入力の単体テスト
# エンコーダ4個の回転（CW/CCW）とプッシュを確認
#   回転     → シェルに方向表示 + LED明度変化（CW=明るく/CCW=暗く）
#   プッシュ → シェルに表示 + LED一瞬点灯
#
# Thonnyで  import test_encoder  して実行
# Ctrl+C で終了

from machine import I2C, Pin
import time

from encoder   import EncoderManager
from mcp23017  import MCP23017
from debug_led import DebugLED

print("=== エンコーダ入力テスト ===")
print("エンコーダを回すと方向が表示され、LED明度が変化します")
print("  CW（時計回り）  → LED明るく")
print("  CCW（反時計回り）→ LED暗く")
print("  プッシュ        → LED一瞬点灯")
print("Ctrl+C で終了\n")

# 初期化
i2c0    = I2C(0, sda=Pin(4), scl=Pin(5), freq=400_000)
mcp     = MCP23017(i2c0, addr=0x20)
enc_mgr = EncoderManager()
led     = DebugLED()

# 各エンコーダの積算カウント（動作確認用）
counts = [0, 0, 0, 0]

print("[準備完了] エンコーダを回してください\n")

try:
    while True:
        # ── 回転検出 ──
        rotations = enc_mgr.update_all()
        for i, rot in enumerate(rotations):
            if rot != 0:
                counts[i] += rot
                if rot > 0:
                    direction = "CW →"
                    led.enc_brighter()
                else:
                    direction = "CCW ←"
                    led.enc_dimmer()
                print(f"  ENC{i+1} {direction}  "
                      f"(累計:{counts[i]:+d})  "
                      f"LED明度:{led.brightness_pct()}%")

        # ── プッシュ検出 ──
        for idx in mcp.get_push_events():
            print(f"  ENC{idx+1} プッシュ！")
            led.flash()

        led.update()
        time.sleep_ms(2)   # エンコーダは高速応答が必要なので短め

except KeyboardInterrupt:
    print("\n[終了] テストを終了しました")
    print(f"最終カウント: ENC1={counts[0]} ENC2={counts[1]} "
          f"ENC3={counts[2]} ENC4={counts[3]}")
