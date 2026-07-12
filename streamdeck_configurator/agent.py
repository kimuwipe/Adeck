# agent.py  v3
# PC側常駐エージェント
# 音量・マイク音量・起動アプリ・天気を取得して Pico へ送信
# Pico からのアクション（アプリ起動・マイク制御）を処理
#
# 依存: pip install -r requirements.txt
#   pyserial, pycaw, psutil, comtypes, requests

from __future__ import annotations   # 古いPythonでも list[str] 等の型注釈を許可

import serial
import serial.tools.list_ports
import json
import time
import subprocess
import threading
import psutil
import urllib.request

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    from ctypes import cast, POINTER
    PYCAW_OK = True
except ImportError:
    PYCAW_OK = False
    print("[WARN] pycaw が見つかりません。音量/マイク制御は無効です。")

SEND_INTERVAL   = 2.0   # 秒ごとに Pico へ情報送信
APP_DISPLAY_MAX = 8     # LCD に表示するアプリ数
WEATHER_INTERVAL = 600  # 天気は10分ごとに取得（APIレート制限対策）

# 豊田市の緯度経度（Open-Meteo API用）
WEATHER_LAT  = 35.0826
WEATHER_LON  = 137.1564
WEATHER_CITY = "Toyota"

_EXCLUDE_PROCS = {
    "svchost.exe","RuntimeBroker.exe","SearchHost.exe",
    "ShellExperienceHost.exe","sihost.exe","taskhostw.exe",
    "explorer.exe","dwm.exe","csrss.exe","winlogon.exe",
    "TextInputHost.exe","dllhost.exe","conhost.exe",
    "fontdrvhost.exe","lsass.exe","services.exe",
    "System","Registry","smss.exe","wininit.exe",
    "python.exe","pythonw.exe",
}

# WMO天気コード → 内部条件文字列
_WMO_TO_COND = {
    0:"sunny", 1:"sunny", 2:"cloudy", 3:"cloudy",
    45:"cloudy",48:"cloudy",
    51:"rainy",53:"rainy",55:"rainy",
    61:"rainy",63:"rainy",65:"rainy",
    71:"snowy",73:"snowy",75:"snowy",
    80:"rainy",81:"rainy",82:"rainy",
    95:"rainy",96:"rainy",99:"rainy",
}
_WMO_TO_DESC = {
    0:"晴れ",1:"晴れ",2:"曇り時々晴",3:"曇り",
    45:"霧",48:"霧",
    51:"小雨",53:"雨",55:"大雨",
    61:"小雨",63:"雨",65:"大雨",
    71:"小雪",73:"雪",75:"大雪",
    80:"にわか雨",81:"にわか雨",82:"激しい雨",
    95:"雷雨",96:"雷雨",99:"激しい雷雨",
}


# ===== 音量取得（新pycaw API: device.EndpointVolume）=====
def get_volume() -> int:
    if not PYCAW_OK:
        return -1
    try:
        device = AudioUtilities.GetSpeakers()
        vol    = device.EndpointVolume
        if vol.GetMute():
            return 0
        return round(vol.GetMasterVolumeLevelScalar() * 100)
    except Exception:
        return -1


# ===== マイク音量取得・制御 =====
# GetMicrophone() は旧型(IMMDevice)を返すため Activate 方式を使う
def _get_mic_if():
    device    = AudioUtilities.GetMicrophone()
    interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))

def get_mic_volume() -> int:
    if not PYCAW_OK:
        return -1
    try:
        return round(_get_mic_if().GetMasterVolumeLevelScalar() * 100)
    except Exception:
        return -1

def set_mic_volume(delta: int):
    if not PYCAW_OK:
        return
    try:
        mic     = _get_mic_if()
        current = mic.GetMasterVolumeLevelScalar()
        mic.SetMasterVolumeLevelScalar(
            max(0.0, min(1.0, current + delta / 100.0)), None)
        print(f"[MIC] {round(mic.GetMasterVolumeLevelScalar()*100)}%")
    except Exception as e:
        print(f"[MIC ERROR] {e}")

def toggle_mic_mute():
    if not PYCAW_OK:
        return
    try:
        mic = _get_mic_if()
        new = not mic.GetMute()
        mic.SetMute(new, None)
        print(f"[MIC] ミュート: {'ON' if new else 'OFF'}")
    except Exception as e:
        print(f"[MIC ERROR] {e}")


# ===== 起動中アプリ取得 =====
def get_running_apps() -> list[str]:
    """
    ユーザーが起動しているアプリ名リストを返す。
    メモリ使用量が多い順に並べ、システムプロセスを除外する。
    """
    procs = []
    for proc in psutil.process_iter(["name", "memory_info"]):
        try:
            name = proc.info["name"]
            if not name or name in _EXCLUDE_PROCS:
                continue
            mem = proc.info["memory_info"].rss if proc.info["memory_info"] else 0
            procs.append((name, mem))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    procs.sort(key=lambda x: x[1], reverse=True)

    seen, result = set(), []
    for name, _ in procs:
        if name in seen:
            continue
        seen.add(name)
        result.append(name.replace(".exe","").replace(".EXE",""))
        if len(result) >= APP_DISPLAY_MAX:
            break
    return result


# ===== 天気取得（Open-Meteo API・無料・APIキー不要）=====
def get_weather() -> dict:
    """
    Open-Meteo API（無料・登録不要）から現在の天気を取得。
    戻り値: {condition, temp, humidity, desc}
    """
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={WEATHER_LAT}&longitude={WEATHER_LON}"
        f"&current=temperature_2m,relative_humidity_2m,weathercode"
        f"&timezone=Asia%2FTokyo"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "StreamDeckAgent/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data    = json.loads(resp.read().decode())
            current = data["current"]
            code    = int(current.get("weathercode", 0))
            temp    = round(current.get("temperature_2m", 0))
            hum     = round(current.get("relative_humidity_2m", 0))
            return {
                "condition": _WMO_TO_COND.get(code, "unknown"),
                "temp":      temp,
                "humidity":  hum,
                "desc":      _WMO_TO_DESC.get(code, "不明"),
            }
    except Exception as e:
        print(f"[WEATHER ERROR] {e}")
        return {"condition": "unknown", "temp": "--", "humidity": "--", "desc": "取得失敗"}


# ===== Pico ポート自動検出 =====
def find_pico_port() -> str | None:
    """
    Pico の COM ポートを検出。
    判定は3段階：
      1. VID/PID（Raspberry Pi: VID=0x2E8A）が最も確実
      2. 説明文に pico / micropython / raspberry
      3. 説明文に usb serial / usb シリアル（Picoは環境によりこの名前になる）
    """
    candidates = []
    for port in serial.tools.list_ports.comports():
        desc = (port.description  or "").lower()
        mfr  = (port.manufacturer or "").lower()
        vid  = port.vid

        # 1. VID一致（Raspberry Pi公式VID = 0x2E8A）→ 最優先
        if vid == 0x2E8A:
            return port.device

        # 2. 明確なPico系の名前
        if "pico" in desc or "micropython" in desc or "raspberry" in mfr:
            return port.device

        # 3. USB シリアルデバイス（候補として保留）
        if "usb serial" in desc or "usb シリアル" in desc or "シリアル デバイス" in desc:
            candidates.append(port.device)

    # 明確なものが無ければ USB シリアル候補の先頭を返す
    if candidates:
        return candidates[0]
    return None


# ===== アプリ起動 =====
def launch_app(exe_path: str):
    try:
        if exe_path == "calc.exe":
            subprocess.Popen("calc.exe", shell=True)
        else:
            subprocess.Popen([exe_path], shell=False)
        print(f"[LAUNCH] {exe_path}")
    except Exception as e:
        print(f"[LAUNCH ERROR] {e}")


# ===== メインエージェントクラス =====
class StreamDeckAgent:
    def __init__(self, config_path: str = "streamdeck_config.json"):
        self._config_path  = config_path
        self._config       = {}
        self._ser          = None
        self._running      = False
        self._weather      = {}
        self._weather_at   = 0   # 最終取得時刻（time.time()）
        self._load_config()

    def _load_config(self):
        try:
            with open(self._config_path, encoding="utf-8") as f:
                self._config = json.load(f)
            print(f"[CONFIG] {self._config_path} を読み込みました")
        except FileNotFoundError:
            print(f"[WARN] {self._config_path} が見つかりません")

    def _connect(self) -> bool:
        port = find_pico_port()
        if not port:
            print("[ERROR] Pico が見つかりません")
            return False
        try:
            self._ser = serial.Serial(port, baudrate=115200, timeout=1)
            print(f"[SERIAL] {port} に接続しました")
            return True
        except Exception as e:
            print(f"[SERIAL ERROR] {e}")
            return False

    def _send(self, data: dict):
        if self._ser and self._ser.is_open:
            try:
                self._ser.write(
                    (json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8"))
            except Exception as e:
                print(f"[SEND ERROR] {e}")
                self._ser = None

    def _receive_loop(self):
        while self._running:
            if not self._ser or not self._ser.is_open:
                time.sleep(0.5); continue
            try:
                line = self._ser.readline().decode("utf-8").strip()
                if line:
                    self._handle_message(json.loads(line))
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
            except Exception as e:
                print(f"[RECV ERROR] {e}")
                time.sleep(0.5)

    def _handle_message(self, msg: dict):
        t = msg.get("type")
        if t == "app_launch":
            exe = msg.get("exe","")
            if exe: launch_app(exe)
        elif t == "action":
            a = msg.get("action","")
            if   a == "MIC_UP":   set_mic_volume(+5)
            elif a == "MIC_DOWN": set_mic_volume(-5)
            elif a == "MIC_MUTE": toggle_mic_mute()
            elif a == "APP_CALC": launch_app("calc.exe")
            else: print(f"[ACTION] 未定義: {a}")
        elif t == "profile_change":
            print(f"[PROFILE] → {msg.get('profile','?')}")
        elif t == "button":
            sw  = msg.get("sw")
            enc = msg.get("enc")
            d   = msg.get("dir","")
            pf  = msg.get("profile","")
            action = msg.get("action","")
            if sw is not None:
                print(f"[BTN] SW{sw+1} profile={pf} action={action}")
                if action:
                    send_key(action)
            elif enc is not None:
                print(f"[BTN] ENC{enc+1} {d} profile={pf} action={action}")
                if action:
                    send_key(action)

    def _get_weather_cached(self) -> dict:
        """天気を WEATHER_INTERVAL 秒キャッシュして取得"""
        now = time.time()
        if not self._weather or now - self._weather_at > WEATHER_INTERVAL:
            print("[WEATHER] 取得中...")
            self._weather    = get_weather()
            self._weather_at = now
            print(f"[WEATHER] {self._weather}")
        return self._weather

    def _info_loop(self):
        while self._running:
            if not self._ser or not self._ser.is_open:
                print("[RECONNECT] 再接続を試みます...")
                self._connect()
                time.sleep(2); continue

            payload = {
                "type":       "info",
                "volume":     get_volume(),
                "mic_volume": get_mic_volume(),
                "apps":       get_running_apps(),
                "weather":    self._get_weather_cached(),
            }
            self._send(payload)
            time.sleep(SEND_INTERVAL)

    def run(self):
        if not self._connect():
            print("[ERROR] Pico に接続できません。")
            return
        self._running = True
        rx = threading.Thread(target=self._receive_loop, daemon=True)
        rx.start()
        print("[AGENT] 起動しました。Ctrl+C で終了")
        try:
            self._info_loop()
        except KeyboardInterrupt:
            print("\n[AGENT] 停止します")
        finally:
            self._running = False
            if self._ser and self._ser.is_open:
                self._ser.close()


if __name__ == "__main__":
    agent = StreamDeckAgent()
    agent.run()


# ===== pyautogui によるキー送信（HIDスタブ代替）=====
# pip install pyautogui
try:
    import pyautogui
    pyautogui.FAILSAFE = False
    PYAUTOGUI_OK = True
except ImportError:
    PYAUTOGUI_OK = False
    print("[WARN] pyautogui が見つかりません。キー送信は無効です。")

# アクション → pyautogui キー名 変換テーブル
_ACTION_TO_KEY = {
    "VOLUME_UP":    ("volumeup",   []),
    "VOLUME_DOWN":  ("volumedown", []),
    "MUTE":         ("volumemute", []),
    "MEDIA_PLAY":   ("playpause",  []),
    "MEDIA_NEXT":   ("nexttrack",  []),
    "MEDIA_PREV":   ("prevtrack",  []),
    "UNDO":         ("z",  ["ctrl"]),
    "REDO":         ("y",  ["ctrl"]),
    "SAVE":         ("s",  ["ctrl"]),
    "ZOOM_IN":      ("=",  ["ctrl"]),
    "ZOOM_OUT":     ("-",  ["ctrl"]),
    "ZOOM_FIT":     ("0",  ["ctrl"]),
    "TAB_NEXT":     ("tab",   ["ctrl"]),
    "TAB_PREV":     ("tab",   ["ctrl","shift"]),
    "NEW_TAB":      ("t",     ["ctrl"]),
    "WIN_SNIP":     ("s",     ["win","shift"]),
    "VDESK_NEXT":   ("right", ["ctrl","win"]),
    "VDESK_PREV":   ("left",  ["ctrl","win"]),
    "WIN_MAX":      ("up",    ["win"]),
    "TASK_MGR":     ("escape",["ctrl","shift"]),
    "WIN_LOCK":     ("l",     ["win"]),
    "SW_SHORTCUT_BAR": ("s",  []),
    "SW_REBUILD":      ("b",  ["ctrl"]),
    "SW_REBUILD_FULL": ("q",  ["ctrl"]),
    "SW_NORMAL_TO":    ("8",  ["ctrl"]),
    "SW_FILTER_CLEAR": ("f6", []),
    "SW_MAGNIFIER":    ("g",  []),
    "SW_ISO":          ("7",  ["ctrl"]),
    "SW_ZOOM_FIT":     ("f",  []),
    "SW_VIEW_NEXT":    ("right",["ctrl"]),
    "SW_VIEW_PREV":    ("left", ["ctrl"]),
    "SHIFT_F5":        ("f5", ["shift"]),
    "DEV_TERMINAL":    ("`",  ["ctrl"]),
    "DEV_COMMENT":     ("/",  ["ctrl"]),
    "DEV_GOTO_DEF":    ("f12",[]),
    "FONT_UP":         ("=",  ["ctrl"]),
    "FONT_DOWN":       ("-",  ["ctrl"]),
    "F5":  ("f5", []),  "F9":  ("f9", []),
    "F10": ("f10",[]),  "F11": ("f11",[]),
    "F13": ("f13",[]),  "F14": ("f14",[]),  "F15": ("f15",[]),
}

def send_key(action: str):
    """pyautogui でキー送信"""
    if not PYAUTOGUI_OK:
        print(f"[KEY] pyautogui無効: {action}")
        return
    entry = _ACTION_TO_KEY.get(action)
    if not entry:
        print(f"[KEY] 未定義アクション: {action}")
        return
    key, mods = entry
    try:
        if mods:
            pyautogui.hotkey(*mods, key)
        else:
            pyautogui.press(key)
        print(f"[KEY] {action} → {mods}+{key}")
    except Exception as e:
        print(f"[KEY ERROR] {e}")
