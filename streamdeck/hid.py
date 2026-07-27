# hid.py  v2.2 デバッグスタブ版
# USB HID（usb.device）が使えない環境向けの暫定スタブ
# キー送信はシリアル経由でPC側agent.pyに委譲する方式に切り替え
#
# 本番移行時は以下のいずれかで対応:
#   A) MicroPython with usb-device-hid パッケージを導入
#   B) agent.py 側でpyautoguiによるキー送信に切り替え（推奨）

import time

MOD_CTRL  = 0x01
MOD_SHIFT = 0x02
MOD_ALT   = 0x04
MOD_GUI   = 0x08

_KEY = {
    "F1": 0x3A, "F2": 0x3B, "F3": 0x3C, "F4": 0x3D,
    "F5": 0x3E, "F6": 0x3F, "F7": 0x40, "F8": 0x41,
    "F9": 0x42, "F10":0x43, "F11":0x44, "F12":0x45,
    "F13":0x68, "F14":0x69, "F15":0x6A,
}


class HIDKeyboard:
    def __init__(self):
        # USB HID 未使用：シリアル経由でPC側に送信
        print("[HID] スタブモード: キー送信はagent.py経由")
        time.sleep_ms(100)

    def _key(self, keycode: int, mod: int = 0):
        # スタブ: 何もしない（agent.pyがキー送信を担当）
        pass

    def send(self, action: str):
        # スタブ: シリアル送信はmain.pyのserial_sendが担当。
        # 毎アクションでprintするとUSB CDCを圧迫しループが詰まるため出力しない。
        pass
