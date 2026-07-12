# test_switch.py
# スイッチ入力の単体テスト
# MCP23017 GPA0〜7 に接続した8個のスイッチをチェック
# 押すとシェルに表示 + デバッグLED(GP28)が点灯
#
# Thonnyで  import test_switch  して実行
# Ctrl+C で終了

from machine import I2C, Pin
import time

from mcp23017 import MCP23017
from debug_led import DebugLED

print("=== スイッチ入力テスト ===")
print("各スイッチを押すと番号が表示され、LEDが光ります")
print("Ctrl+C で終了\n")

# 初期化
i2c0 = I2C(0, sda=Pin(4), scl=Pin(5), freq=400_000)
mcp  = MCP23017(i2c0, addr=0x20)
led  = DebugLED()

print("[準備完了] スイッチを押してください\n")

# 現在の全スイッチ状態を表示（デバッグ用）
def show_all_states():
    states = mcp.read_switches()
    line = ""
    for i, pressed in enumerate(states):
        mark = "●" if pressed else "○"
        line += f"SW{i+1}:{mark} "
    print(line)

try:
    loop = 0
    while True:
        # エッジ検出（押した瞬間）
        events = mcp.get_switch_events()
        for idx in events:
            print(f"  → SW{idx+1} が押されました！")
            led.flash()   # LED点灯

        led.update()

        # 1秒ごとに全状態を表示（押しっぱなし確認用）
        loop += 1
        if loop >= 200:   # 5ms × 200 = 1秒
            loop = 0
            show_all_states()

        time.sleep_ms(5)

except KeyboardInterrupt:
    print("\n[終了] テストを終了しました")
