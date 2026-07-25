# main.py  v4
# 5ページ表示・独立タッチスワイプ対応版

from machine import I2C, Pin
import sys, time, json, gc

gc.collect()   # 起動時にメモリを整理してフレームバッファ確保を確実に

import config as _config   # ライブ設定反映で display_pages 側の参照も更新するため
from config import (
    PROFILES, SWITCH_MAP, ENCODER_MAP,
    DISPLAY_BRIGHTNESS, SWITCH_DEBOUNCE_MS, ENCODER_DEBOUNCE_MS
)
from hid          import HIDKeyboard
from mcp23017     import MCP23017
from encoder      import EncoderManager
from display      import DisplayManager
from touch        import TouchManager, GESTURE_SWIPE_LEFT, GESTURE_SWIPE_RIGHT, GESTURE_TAP
from display_pages import draw_page, PAGE_COUNT
from debug_led    import DebugLED

# ===== USB CDC シリアル通信 =====
import select
_poll = select.poll()
_poll.register(sys.stdin, select.POLLIN)

def serial_send(data: dict):
    # MicroPython の json.dumps は ensure_ascii 等のキーワード引数を受け付けない
    # （渡すと TypeError で送信が黙って失敗する）。素の dumps は非ASCIIも
    # UTF-8 のまま出力するので PC 側 readline().decode("utf-8") でそのまま読める。
    try:
        sys.stdout.write(json.dumps(data) + "\n")
    except Exception as e:
        print("[serial_send ERR]", e)

def serial_recv():
    """ノンブロッキング受信。データが無ければ即 None を返す。"""
    try:
        # 0msタイムアウトで待ち無し。データがある時だけ読む。
        if _poll.poll(0):
            line = sys.stdin.readline()
            if line and line.strip():
                return json.loads(line.strip())
    except Exception:
        pass
    return None

# ===== 状態管理 =====
class State:
    # プロファイル
    profile:        int  = 0
    # 音量・アプリ（PCから取得）
    volume:         int  = -1
    mic_volume:     int  = -1
    apps:           list = []
    # 天気（PCから取得）
    weather:        dict = {}
    # LCD独立ページ
    page0:          int  = 0    # LCD① 現在ページ
    page1:          int  = 0    # LCD② 現在ページ
    # 再描画フラグ
    dirty0:         bool = True
    dirty1:         bool = True
    # SolidWorks表示スタイル順繰り
    sw_display_idx: int  = 0

state = State()

_SW_DISPLAY_KEYS = ["2", "3", "4"]

# ===== ヘルパ =====
def current_switches(): return SWITCH_MAP[state.profile]
def current_encoders(): return ENCODER_MAP[state.profile]
def profile_name():     return PROFILES[state.profile]

# ===== プロファイル切り替え =====
def next_profile():
    state.profile = (state.profile + 1) % len(PROFILES)
    state.dirty0  = True
    state.dirty1  = True
    serial_send({"type": "profile_change", "profile": profile_name()})
    print(f"[PROFILE] → {profile_name()}")

# ===== ページ切り替え =====
def page_next(lcd_idx: int):
    if lcd_idx == 0:
        state.page0 = (state.page0 + 1) % PAGE_COUNT
        state.dirty0 = True
    else:
        state.page1 = (state.page1 + 1) % PAGE_COUNT
        state.dirty1 = True

def page_prev(lcd_idx: int):
    if lcd_idx == 0:
        state.page0 = (state.page0 - 1) % PAGE_COUNT
        state.dirty0 = True
    else:
        state.page1 = (state.page1 - 1) % PAGE_COUNT
        state.dirty1 = True

# ===== アクション実行 =====
_AGENT_ACTIONS = {"MIC_UP", "MIC_DOWN", "MIC_MUTE", "APP_CALC"}

def handle_action(action):
    if not action or action in (None, "None", "（なし）"):
        return
    if action == "PROFILE_NEXT":
        next_profile(); return
    if action in _AGENT_ACTIONS:
        serial_send({"type": "action", "action": action}); return
    if isinstance(action, str) and action.startswith("APP:"):
        serial_send({"type": "app_launch", "exe": action[4:]}); return
    if action == "SW_DISPLAY_CYCLE":
        key = _SW_DISPLAY_KEYS[state.sw_display_idx]
        state.sw_display_idx = (state.sw_display_idx + 1) % len(_SW_DISPLAY_KEYS)
        from hid import MOD_CTRL, _KEY
        kbd._key(_KEY[key], MOD_CTRL); return
    if action == "ZOOM_FIT" and state.profile == 1:
        kbd.send("SW_ZOOM_FIT"); return
    kbd.send(action)

# ===== PC発のプロファイル遠隔切替（前面アプリ連動） =====
def set_profile_by(name=None, index=None):
    """PC側から指定されたプロファイルへ切り替える。
    エコー（profile_change送信）はしない（PC発なのでループ防止）。"""
    new = None
    if name in PROFILES:
        new = PROFILES.index(name)
    elif isinstance(index, int) and 0 <= index < len(PROFILES):
        new = index
    if new is not None and new != state.profile:
        state.profile = new
        state.dirty0  = True
        state.dirty1  = True
        print("[PROFILE] PC切替 →", profile_name())

# ===== ライブ設定反映（再起動なしでキー割り当てを更新） =====
def apply_live_config(msg):
    """PCから受け取ったマップで SWITCH_MAP/ENCODER_MAP/PROFILES を差し替える。
    main.py のグローバルと config モジュール属性（display_pagesが参照）の両方を更新。"""
    global PROFILES, SWITCH_MAP, ENCODER_MAP
    pf = msg.get("profiles")
    sm = msg.get("switches")
    em = msg.get("encoders")
    if isinstance(pf, list) and pf:
        PROFILES = pf; _config.PROFILES = pf
    if isinstance(sm, list) and sm:
        SWITCH_MAP = sm; _config.SWITCH_MAP = sm
    if isinstance(em, list) and em:
        ENCODER_MAP = em; _config.ENCODER_MAP = em
    if state.profile >= len(PROFILES):
        state.profile = 0
    state.dirty0 = True
    state.dirty1 = True
    gc.collect()
    print("[CONFIG] ライブ設定を反映")
    serial_send({"type": "config_ack"})

# ===== 初期化 =====
print("[BOOT] 初期化開始")
kbd       = HIDKeyboard()
i2c0      = I2C(0, sda=Pin(4),  scl=Pin(5),  freq=400_000)
i2c1      = I2C(1, sda=Pin(6),  scl=Pin(7),  freq=400_000)
mcp       = MCP23017(i2c0, addr=0x20)
enc_mgr   = EncoderManager()
disp      = DisplayManager()
touch_mgr = TouchManager(i2c0, i2c1)
disp.set_brightness(DISPLAY_BRIGHTNESS)
dbg_led   = DebugLED()          # GP28 デバッグLED
print("[BOOT] デバッグLED GP28 初期化完了")

# 起動画面（共有バッファのため1画面ずつ描画→転送）
for lcd in [disp.lcd0, disp.lcd1]:
    lcd.fill(0x0000)
    lcd.text("StreamDeck v4", 8, 70, 0xFFFF)
    lcd.small_text("Initializing...", 8, 95, 0x7BEF)
    lcd.show()
time.sleep(1)

print(f"[RUN] 起動完了 プロファイル: {profile_name()}")

# ===== デバウンス =====
_sw_last  = [0] * 8
_enc_last = [0] * 4

def sw_ok(idx):
    now = time.ticks_ms()
    if time.ticks_diff(now, _sw_last[idx]) > SWITCH_DEBOUNCE_MS:
        _sw_last[idx] = now; return True
    return False

def enc_ok(idx):
    now = time.ticks_ms()
    if time.ticks_diff(now, _enc_last[idx]) > ENCODER_DEBOUNCE_MS:
        _enc_last[idx] = now; return True
    return False

# ===== メインループ =====
_draw_cnt = 0

while True:
    # ── PC からシリアル受信
    msg = serial_recv()
    if msg:
        t = msg.get("type")
        if t == "info":
            state.volume     = msg.get("volume",     -1)
            state.mic_volume = msg.get("mic_volume", -1)
            state.apps       = msg.get("apps",       [])
            state.weather    = msg.get("weather",    {})
            state.dirty0     = True
            state.dirty1     = True
        elif t == "set_profile":
            set_profile_by(msg.get("profile"), msg.get("index"))
        elif t == "config":
            apply_live_config(msg)

    # ── タッチ
    #   タップ → 次のプロファイル（プリセット）へ切替（各画面右上のバッジ表示）
    #   スワイプ左右 → ページ送り
    g0, g1 = touch_mgr.update_all()
    if g0 == GESTURE_TAP or g1 == GESTURE_TAP:
        next_profile()

    if g0 == GESTURE_SWIPE_LEFT:
        page_next(0)
    elif g0 == GESTURE_SWIPE_RIGHT:
        page_prev(0)

    if g1 == GESTURE_SWIPE_LEFT:
        page_next(1)
    elif g1 == GESTURE_SWIPE_RIGHT:
        page_prev(1)

    # ── スイッチ
    for idx in mcp.get_switch_events():
        if sw_ok(idx):
            sws    = current_switches()
            action = sws[idx] if idx < len(sws) else None
            dbg_led.flash()          # デバッグLED: ワンショット点灯
            serial_send({"type": "button", "sw": idx,
                         "action": action or "", "profile": profile_name()})
            handle_action(action)
            # スイッチ押下では表示内容は変わらないので再描画しない（追従性優先）。
            # プロファイル切替(SW1=PROFILE_NEXT)は next_profile 側で dirty を立てる。

    # ── エンコーダ Push
    for idx in mcp.get_push_events():
        encs = current_encoders()
        if idx < len(encs) and encs[idx]:
            action = encs[idx][2]
            print(f"[ENC{idx+1} Push] {action}")
            dbg_led.flash()          # デバッグLED: ワンショット点灯
            serial_send({"type": "button", "enc": idx, "dir": "push",
                         "action": action or "", "profile": profile_name()})
            handle_action(action)

    # ── エンコーダ回転
    for i, rot in enumerate(enc_mgr.update_all()):
        if rot != 0 and enc_ok(i):
            encs = current_encoders()
            if i < len(encs) and encs[i]:
                action    = encs[i][0] if rot > 0 else encs[i][1]
                direction = "cw"       if rot > 0 else "ccw"
                # デバッグLED: CW=明るく / CCW=暗く
                if rot > 0:
                    dbg_led.enc_brighter()
                else:
                    dbg_led.enc_dimmer()
                serial_send({"type": "button", "enc": i, "dir": direction,
                             "action": action or "", "profile": profile_name()})
                handle_action(action)

    # ── 画面更新
    # 基本は dirty（状態変化時）のみ再描画。描画はSPI転送でループをブロックする
    # ため、変化が無い時は描画しない＝入力(ボタン/タッチ/エンコーダ)の追従が良い。
    # force は保険の定期リフレッシュ（低頻度）。共有バッファのため1画面ずつ処理。
    _draw_cnt += 1
    force = _draw_cnt >= 200      # 保険の全画面リフレッシュ（頻度は低く）

    if state.dirty0 or force:
        draw_page(disp.lcd0, state.page0, state)
        disp.lcd0.show()
        state.dirty0 = False

    if state.dirty1 or force:
        draw_page(disp.lcd1, state.page1, state)
        disp.lcd1.show()
        state.dirty1 = False

    if force:
        _draw_cnt = 0

    dbg_led.update()     # デバッグLED ワンショット消灯チェック
    time.sleep_ms(3)     # 入力の追従性向上（旧10ms→3ms）
