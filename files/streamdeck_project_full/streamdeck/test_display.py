# test_display.py
# ディスプレイ単体テスト（メモリ・描画確認用）
# Thonnyで import test_display して実行

import gc
gc.collect()
print("開始前 空きメモリ:", gc.mem_free())

from display import DisplayManager

disp = DisplayManager()
print("DisplayManager確保後 空きメモリ:", gc.mem_free())

# 色定数
BLACK = 0x0000
WHITE = 0xFFFF
RED   = 0xF800
GREEN = 0x07E0
CYAN  = 0x07FF

# LCD0 テスト描画
disp.lcd0.fill(BLACK)
disp.lcd0.rect(0, 0, 320, 20, CYAN, fill=True)
disp.lcd0.text("LCD0 TEST", 10, 40, WHITE)
disp.lcd0.text("123456", 10, 70, GREEN)
disp.lcd0.small_text("small text ok", 10, 100, RED)
disp.lcd0.show()
print("LCD0 描画完了")

# LCD1 テスト描画
disp.lcd1.fill(BLACK)
disp.lcd1.rect(0, 0, 320, 20, RED, fill=True)
disp.lcd1.text("LCD1 TEST", 10, 40, WHITE)
disp.lcd1.show()
print("LCD1 描画完了")

gc.collect()
print("描画後 空きメモリ:", gc.mem_free())
print("テスト完了！両画面に文字が表示されていればOK")
