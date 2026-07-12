# test_agent.py
# PC側の情報取得を単体テスト（Pico不要）
# 音量・マイク・起動アプリ・天気が取得できるか確認する
#
# 実行: python test_agent.py
# 依存: pip install -r requirements.txt

import sys

print("=== PC側情報取得テスト ===\n")

# --- ライブラリ確認 ---
print("[1] ライブラリのインポート確認")
try:
    import psutil
    print("  psutil       OK")
except ImportError:
    print("  psutil       ✗ 未インストール → pip install psutil")

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    from ctypes import cast, POINTER
    print("  pycaw        OK")
    PYCAW_OK = True
except ImportError:
    print("  pycaw        ✗ 未インストール → pip install pycaw comtypes")
    PYCAW_OK = False

try:
    import pyautogui
    print("  pyautogui    OK")
except ImportError:
    print("  pyautogui    ✗ 未インストール → pip install pyautogui")

try:
    import serial.tools.list_ports
    print("  pyserial     OK")
except ImportError:
    print("  pyserial     ✗ 未インストール → pip install pyserial")

import urllib.request
import json

# --- 音量取得 ---
print("\n[2] システム音量")
if PYCAW_OK:
    try:
        device = AudioUtilities.GetSpeakers()
        vol    = device.EndpointVolume
        mute   = vol.GetMute()
        level  = round(vol.GetMasterVolumeLevelScalar() * 100)
        print(f"  マスター音量: {level}%  (ミュート: {'ON' if mute else 'OFF'})")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
else:
    print("  pycaw未導入のためスキップ")

# --- マイク音量取得 ---
print("\n[3] マイク音量")
if PYCAW_OK:
    try:
        mic_dev = AudioUtilities.GetMicrophone()
        mic_if  = mic_dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        mic     = cast(mic_if, POINTER(IAudioEndpointVolume))
        mic_lvl = round(mic.GetMasterVolumeLevelScalar() * 100)
        print(f"  マイク音量: {mic_lvl}%")
    except Exception as e:
        print(f"  ✗ エラー: {e}（マイクが接続されていない可能性）")
else:
    print("  pycaw未導入のためスキップ")

# --- 起動中アプリ ---
print("\n[4] 起動中アプリ（上位8件）")
try:
    EXCLUDE = {"svchost.exe","RuntimeBroker.exe","explorer.exe","dwm.exe",
               "csrss.exe","python.exe","pythonw.exe","System","Registry",
               "System Idle Process","smss.exe","wininit.exe","services.exe",
               "lsass.exe","winlogon.exe","fontdrvhost.exe","conhost.exe",
               "sihost.exe","taskhostw.exe","dllhost.exe","spoolsv.exe"}
    procs = []
    for proc in psutil.process_iter(["name","memory_info"]):
        try:
            name = proc.info["name"]
            if not name or name in EXCLUDE:
                continue
            mem = proc.info["memory_info"].rss if proc.info["memory_info"] else 0
            procs.append((name, mem))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    procs.sort(key=lambda x: x[1], reverse=True)
    seen, apps = set(), []
    for name, _ in procs:
        if name in seen:
            continue
        seen.add(name)
        apps.append(name.replace(".exe",""))
        if len(apps) >= 8:
            break
    for a in apps:
        print(f"  - {a}")
except Exception as e:
    print(f"  ✗ エラー: {e}")

# --- 天気取得（豊田市）---
print("\n[5] 天気（豊田市 / Open-Meteo）")
try:
    url = ("https://api.open-meteo.com/v1/forecast"
           "?latitude=35.0826&longitude=137.1564"
           "&current=temperature_2m,relative_humidity_2m,weathercode"
           "&timezone=Asia%2FTokyo")
    req = urllib.request.Request(url, headers={"User-Agent":"test/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
        cur  = data["current"]
        print(f"  気温: {cur['temperature_2m']}°C")
        print(f"  湿度: {cur['relative_humidity_2m']}%")
        print(f"  天気コード: {cur['weathercode']}")
except Exception as e:
    print(f"  ✗ エラー: {e}（ネット接続を確認）")

# --- Picoポート検出 ---
print("\n[6] Picoシリアルポート検出")
try:
    found = None
    for port in serial.tools.list_ports.comports():
        desc = (port.description or "").lower()
        vid  = port.vid
        vid_str = f"VID={hex(vid)}" if vid else "VID=?"
        is_pico = (vid == 0x2E8A or "pico" in desc or "micropython" in desc
                   or "usb serial" in desc or "シリアル デバイス" in desc)
        mark = " ★Pico候補" if is_pico else ""
        if is_pico and found is None:
            found = port.device
        print(f"  検出: {port.device} - {port.description} [{vid_str}]{mark}")
    if found:
        print(f"  → Pico: {found}")
    else:
        print("  ※ Picoが見つかりません（Thonnyが掴んでいる場合は閉じてください）")
except Exception as e:
    print(f"  ✗ エラー: {e}")

print("\n=== テスト完了 ===")
print("全項目OKなら agent.py 本体を起動できます")
