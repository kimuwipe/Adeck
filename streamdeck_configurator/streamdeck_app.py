# streamdeck_app.py  v2  (統合UI・CustomTkinter)
# コントローラ（常駐エージェント）と設定エディタを1つのウィンドウに統合。
#
# 起動: python streamdeck_app.py
# 依存: pip install -r requirements.txt
#   pyserial, pycaw, psutil, comtypes, pyautogui, pystray, Pillow,
#   customtkinter, pyperclip
#
# 構成:
#   - 上部に接続状態・音量/マイク/天気/プロファイルを常時表示
#   - タブ「設定」= グリッド型エディタ（configurator.EditorFrame を埋め込み）
#   - タブ「オプション」= 自動起動・前面アプリ自動切替
#   - タブ「ログ」= 動作ログ
#   - システムトレイ常駐、×でトレイ最小化

from __future__ import annotations

import json
import sys
import time
import threading
import queue

import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox

# ===== agent.py / configurator.py の機能を再利用 =====
try:
    import agent as ag
    AGENT_OK = True
except Exception as e:
    AGENT_OK = False
    print(f"[WARN] agent.py を読み込めません: {e}")

try:
    import configurator as cfgmod
    CFG_OK = True
except Exception as e:
    CFG_OK = False
    print(f"[WARN] configurator.py を読み込めません: {e}")

import serial  # 再接続制御に使用

# ===== システムトレイ（pystray）=====
try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_OK = True
except Exception as e:
    TRAY_OK = False
    print(f"[WARN] pystray/Pillow が無いためトレイ常駐は無効: {e}")

# ===== 自動起動 =====
try:
    import autostart
    AUTOSTART_OK = True
except Exception as e:
    AUTOSTART_OK = False
    print(f"[WARN] autostart.py が読み込めません: {e}")


# ============================================================
#  常駐エージェント（GUI連携スレッド版）
# ============================================================
class AgentThread:
    """agent.py の機能をGUI連携用にラップ。ログ/状態を queue でGUIへ渡す。
    cfg は GUI・エディタと共有参照する（自動切替ルール等の同期のため）。"""

    def __init__(self, log_q: queue.Queue, status_q: queue.Queue, cfg: dict):
        self._log_q = log_q
        self._status_q = status_q
        self._cfg = cfg
        self._ser = None
        self._running = False
        self._weather = {}
        self._weather_at = 0
        self._threads = []
        self._send_lock = threading.Lock()
        self._current_profile = None
        self._auto_enabled = False
        self._auto_rules = {}
        self._load_auto_profile()

    # ---- ログ/ステータス ----
    def _log(self, msg: str):
        self._log_q.put(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def _status(self, **kwargs):
        self._status_q.put(kwargs)

    # ---- 自動切替設定 ----
    def _load_auto_profile(self):
        ap = (self._cfg or {}).get("auto_profile") or {}
        self._auto_enabled = bool(ap.get("enabled", False))
        rules = ap.get("rules")
        if not rules and CFG_OK:
            rules = cfgmod.DEFAULT_AUTO_RULES
        self._auto_rules = {str(k).lower(): v for k, v in (rules or {}).items()}

    def reload_config(self):
        self._load_auto_profile()

    # ---- 接続 ----
    def _connect(self) -> bool:
        if not AGENT_OK:
            self._log("agent.py が無いため接続できません")
            return False
        port = ag.find_pico_port()
        if not port:
            self._log("Pico が見つかりません")
            self._status(connected=False, port="—")
            return False
        try:
            self._ser = serial.Serial(port, baudrate=115200, timeout=1)
            self._log(f"{port} に接続しました")
            self._status(connected=True, port=port)
            return True
        except Exception as e:
            self._log(f"接続エラー: {e}")
            self._status(connected=False, port="—")
            return False

    def _send(self, data: dict):
        if self._ser and self._ser.is_open:
            payload = (json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8")
            try:
                with self._send_lock:
                    self._ser.write(payload)
            except Exception as e:
                self._log(f"送信エラー: {e}")
                self._ser = None
                self._status(connected=False, port="—")

    # ---- 受信 ----
    def _receive_loop(self):
        if AGENT_OK:
            ag.co_initialize()   # このスレッドで pycaw(マイク制御) を使うため
        while self._running:
            if not self._ser or not self._ser.is_open:
                time.sleep(0.5)
                continue
            try:
                line = self._ser.readline().decode("utf-8").strip()
                if line:
                    self._handle_message(json.loads(line))
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
            except Exception as e:
                self._log(f"受信エラー: {e}")
                time.sleep(0.5)

    def _handle_message(self, msg: dict):
        t = msg.get("type")
        if t == "app_launch":
            exe = msg.get("exe", "")
            if exe and AGENT_OK:
                ag.launch_app(exe)
                self._log(f"アプリ起動: {exe}")
        elif t == "action":
            a = msg.get("action", "")
            if AGENT_OK:
                if a == "MIC_UP":
                    ag.set_mic_volume(+5)
                elif a == "MIC_DOWN":
                    ag.set_mic_volume(-5)
                elif a == "MIC_MUTE":
                    ag.toggle_mic_mute()
                elif a == "APP_CALC":
                    ag.launch_app("calc.exe")
            self._log(f"アクション: {a}")
        elif t == "config_ack":
            self._log("Pico: ライブ設定を反映しました")
        elif t == "profile_change":
            pf = msg.get("profile", "?")
            self._current_profile = pf
            self._log(f"プロファイル → {pf}")
            self._status(profile=pf)
        elif t == "button":
            sw = msg.get("sw")
            enc = msg.get("enc")
            d = msg.get("dir", "")
            pf = msg.get("profile", "")
            action = msg.get("action", "")
            if sw is not None:
                label = f"SW{sw+1}"
            elif enc is not None:
                label = f"ENC{enc+1} {d}"
            else:
                label = None
            if label is not None:
                if action and AGENT_OK:
                    # PC側のキー送信にかかった時間を計測してログに出す（重さの切り分け用）
                    t0 = time.perf_counter()
                    ag.send_key(action)
                    dt = (time.perf_counter() - t0) * 1000.0
                    self._log(f"{label} [{pf}] {action}  (PC送信 {dt:.0f}ms)")
                else:
                    self._log(f"{label} [{pf}] {action}")

    # ---- 情報送信 ----
    def _get_weather_cached(self) -> dict:
        now = time.time()
        interval = getattr(ag, "WEATHER_INTERVAL", 600) if AGENT_OK else 600
        if not self._weather or now - self._weather_at > interval:
            if AGENT_OK:
                self._weather = ag.get_weather()
                self._weather_at = now
                self._log(f"天気更新: {self._weather.get('desc', '?')}")
        return self._weather

    def _info_loop(self):
        if AGENT_OK:
            ag.co_initialize()   # このスレッドで pycaw(音量/マイク取得) を使うため
        interval = getattr(ag, "SEND_INTERVAL", 2.0) if AGENT_OK else 2.0
        while self._running:
            if not self._ser or not self._ser.is_open:
                self._log("再接続を試みます...")
                self._connect()
                time.sleep(2)
                continue
            if not AGENT_OK:
                time.sleep(interval)
                continue
            vol = ag.get_volume()
            mic = ag.get_mic_volume()
            apps = ag.get_running_apps()
            wx = self._get_weather_cached()
            self._send({"type": "info", "volume": vol, "mic_volume": mic,
                        "apps": apps, "weather": wx})
            self._status(volume=vol, mic_volume=mic,
                         weather=wx.get("desc", "—"), temp=wx.get("temp", "—"))
            time.sleep(interval)

    # ---- ライブ設定反映 ----
    def send_live_config(self, cfg: dict) -> bool:
        if not (self._ser and self._ser.is_open):
            self._log("Pico未接続のためライブ反映できません")
            return False
        if not CFG_OK:
            return False
        try:
            profiles, sm, em = cfgmod.expand_maps(cfg)
        except Exception as e:
            self._log(f"設定展開エラー: {e}")
            return False
        self._send({"type": "config", "profiles": profiles,
                    "switches": sm, "encoders": em})
        self._log("ライブ設定を送信しました（書込なし即反映）")
        self._load_auto_profile()   # ルール等も最新化
        return True

    # ---- 前面アプリ連動 自動プロファイル切替 ----
    def set_auto_enabled(self, enabled: bool):
        self._auto_enabled = bool(enabled)
        self._log(f"自動プロファイル切替: {'ON' if enabled else 'OFF'}")

    def set_profile_remote(self, name: str):
        if self._ser and self._ser.is_open:
            self._send({"type": "set_profile", "profile": name})

    def _foreground_proc_name(self):
        try:
            import ctypes
            import psutil
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if not pid.value:
                return None
            return psutil.Process(pid.value).name()
        except Exception:
            return None

    def _auto_profile_loop(self):
        last_proc = None
        while self._running:
            if not self._auto_enabled:
                time.sleep(1.0)
                continue
            name = self._foreground_proc_name()
            if name and name != last_proc:
                last_proc = name
                target = self._auto_rules.get(name.lower())
                if target and target != self._current_profile:
                    self.set_profile_remote(target)
                    self._current_profile = target
                    self._status(profile=target)
                    self._log(f"自動切替: {name} → {target}")
            time.sleep(1.0)

    # ---- 起動/停止 ----
    def start(self):
        if self._running:
            return
        self._running = True
        self._connect()
        rx = threading.Thread(target=self._receive_loop, daemon=True)
        info = threading.Thread(target=self._info_loop, daemon=True)
        auto = threading.Thread(target=self._auto_profile_loop, daemon=True)
        rx.start(); info.start(); auto.start()
        self._threads = [rx, info, auto]
        self._log("エージェント開始")

    def stop(self):
        self._running = False
        if self._ser and self._ser.is_open:
            self._ser.close()
        self._status(connected=False, port="—")
        self._log("エージェント停止")


# ============================================================
#  統合GUIアプリ（CustomTkinter）
# ============================================================
class StreamDeckApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        try:
            ctk.set_default_color_theme("dark-blue")
        except Exception:
            pass
        self.title("StreamDeck Controller")
        self.geometry("1180x860")
        self.minsize(1000, 760)

        self._log_q = queue.Queue()
        self._status_q = queue.Queue()

        # 設定（エディタ・エージェントで共有）
        self._cfg = cfgmod.load_config() if CFG_OK else {}
        self._agent = AgentThread(self._log_q, self._status_q, self._cfg)

        self._connected = False
        self._tray_icon = None

        self._build_ui()
        self._poll_queues()
        self.after(500, self._agent.start)

        if TRAY_OK:
            self._setup_tray()
            self.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        else:
            self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- UI ----
    def _build_ui(self):
        # ===== 上部ステータスバー =====
        bar = ctk.CTkFrame(self, corner_radius=0)
        bar.pack(fill="x")

        self.lbl_conn = ctk.CTkLabel(bar, text="● 未接続",
                                     font=ctk.CTkFont(size=15, weight="bold"),
                                     text_color="#888")
        self.lbl_conn.pack(side="left", padx=(14, 8), pady=10)
        self.lbl_port = ctk.CTkLabel(bar, text="ポート: —", text_color="#aaa")
        self.lbl_port.pack(side="left", padx=6)

        # 接続操作
        ctk.CTkButton(bar, text="再接続", width=70, fg_color="#555",
                      hover_color="#666", command=self._reconnect).pack(side="right", padx=(4, 12))
        ctk.CTkButton(bar, text="切断", width=64, fg_color="#555",
                      hover_color="#666", command=self._agent.stop).pack(side="right", padx=4)
        ctk.CTkButton(bar, text="接続", width=64,
                      command=self._agent.start).pack(side="right", padx=4)

        # 値表示 ＋ タブ切替（同じ行の右側に配置）
        vals = ctk.CTkFrame(self, fg_color="transparent")
        vals.pack(fill="x", padx=14, pady=(4, 2))
        self._tabsel = ctk.CTkSegmentedButton(
            vals, values=["設定", "オプション"], command=self._select_tab)
        self._tabsel.set("設定")
        self._tabsel.pack(side="right")
        self.lbl_vol = ctk.CTkLabel(vals, text="音量: —")
        self.lbl_mic = ctk.CTkLabel(vals, text="マイク: —")
        self.lbl_wx = ctk.CTkLabel(vals, text="天気: —")
        self.lbl_prof = ctk.CTkLabel(vals, text="プロファイル: —",
                                     font=ctk.CTkFont(weight="bold"))
        for w in (self.lbl_vol, self.lbl_mic, self.lbl_wx, self.lbl_prof):
            w.pack(side="left", padx=(0, 20))

        # ===== 下部：常時表示ログパネル（どのタブでも見える）=====
        self._log_collapsed = False
        logwrap = ctk.CTkFrame(self)
        logwrap.pack(side="bottom", fill="x", padx=8, pady=(0, 8))
        loghdr = ctk.CTkFrame(logwrap, fg_color="transparent")
        loghdr.pack(fill="x")
        ctk.CTkLabel(loghdr, text="ログ",
                     font=ctk.CTkFont(size=12, weight="bold")
                     ).pack(side="left", padx=8, pady=2)
        ctk.CTkButton(loghdr, text="クリア", width=60, height=24, fg_color="#555",
                      hover_color="#666", command=self._clear_log
                      ).pack(side="right", padx=4)
        self._log_toggle_btn = ctk.CTkButton(
            loghdr, text="▼ 隠す", width=70, height=24, fg_color="#555",
            hover_color="#666", command=self._toggle_log)
        self._log_toggle_btn.pack(side="right", padx=4)
        self.txt_log = ctk.CTkTextbox(
            logwrap, height=150, font=ctk.CTkFont(family="Consolas", size=12))
        self.txt_log.pack(fill="x", padx=4, pady=(0, 4))

        # ===== コンテンツ（自前タブ切替でページを出し分け）=====
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self._pages = {}

        page_edit = ctk.CTkFrame(container, fg_color="transparent")
        if CFG_OK:
            self.editor = cfgmod.EditorFrame(
                page_edit, self._cfg, on_live_apply=self._on_live_apply)
            self.editor.pack(fill="both", expand=True)
        else:
            ctk.CTkLabel(page_edit, text="configurator.py を読み込めませんでした",
                         text_color="#ef4444").pack(pady=20)
        self._pages["設定"] = page_edit

        page_opt = ctk.CTkFrame(container, fg_color="transparent")
        self._build_options_tab(page_opt)
        self._pages["オプション"] = page_opt

        self._select_tab("設定")

    def _toggle_log(self):
        if self._log_collapsed:
            self.txt_log.pack(fill="x", padx=4, pady=(0, 4))
            self._log_toggle_btn.configure(text="▼ 隠す")
        else:
            self.txt_log.pack_forget()
            self._log_toggle_btn.configure(text="▲ 表示")
        self._log_collapsed = not self._log_collapsed

    def _select_tab(self, name):
        for fr in self._pages.values():
            fr.pack_forget()
        self._pages[name].pack(fill="both", expand=True)

    def _build_options_tab(self, f):
        pad = {"padx": 16, "pady": 10}

        # 自動起動
        init_auto = autostart.is_enabled() if AUTOSTART_OK else False
        self.var_autostart = tk.BooleanVar(value=init_auto)
        sw1 = ctk.CTkSwitch(f, text="Windows起動時に自動で起動する",
                            variable=self.var_autostart,
                            command=self._toggle_autostart)
        sw1.pack(anchor="w", **pad)
        if not AUTOSTART_OK:
            sw1.configure(state="disabled")

        # 前面アプリ連動
        init_ap = bool(self._cfg.get("auto_profile", {}).get("enabled", False))
        self.var_autoprofile = tk.BooleanVar(value=init_ap)
        self._agent.set_auto_enabled(init_ap)
        apf = ctk.CTkFrame(f, fg_color="transparent")
        apf.pack(anchor="w", **pad)
        ctk.CTkSwitch(apf, text="前面アプリで自動プロファイル切替",
                      variable=self.var_autoprofile,
                      command=self._toggle_autoprofile).pack(side="left")
        ctk.CTkButton(apf, text="ルール編集", width=100, fg_color="#555",
                      hover_color="#666",
                      command=self._edit_auto_rules).pack(side="left", padx=12)

        note = ("※ ×ボタンでタスクトレイに最小化して常駐します"
                if TRAY_OK else "※ pystray未導入のためトレイ常駐は無効です")
        ctk.CTkLabel(f, text=note, text_color="#888").pack(anchor="w", **pad)

    # ---- オプション操作 ----
    def _toggle_autostart(self):
        if not AUTOSTART_OK:
            return
        ok = autostart.toggle(self.var_autostart.get())
        if not ok:
            messagebox.showerror("自動起動", "設定に失敗しました")
            self.var_autostart.set(autostart.is_enabled())

    def _toggle_autoprofile(self):
        en = bool(self.var_autoprofile.get())
        self._agent.set_auto_enabled(en)
        self._cfg.setdefault("auto_profile", {})["enabled"] = en
        if CFG_OK:
            cfgmod.save_config(self._cfg)

    def _edit_auto_rules(self):
        """自動切替ルール（プロセス名→プロファイル）をJSONで編集するダイアログ。"""
        win = ctk.CTkToplevel(self)
        win.title("自動切替ルール")
        win.geometry("480x460")
        win.transient(self)
        ctk.CTkLabel(win, text='"プロセス名.exe": "プロファイル名" の形式（JSON）',
                     font=ctk.CTkFont(size=12)).pack(padx=12, pady=(12, 4))
        box = ctk.CTkTextbox(win, font=ctk.CTkFont(family="Consolas", size=13))
        box.pack(fill="both", expand=True, padx=12, pady=6)
        rules = self._cfg.get("auto_profile", {}).get("rules", {})
        box.insert("1.0", json.dumps(rules, ensure_ascii=False, indent=2))

        def _save():
            try:
                new = json.loads(box.get("1.0", "end"))
                if not isinstance(new, dict):
                    raise ValueError("辞書(JSONオブジェクト)である必要があります")
            except Exception as e:
                messagebox.showerror("ルール編集", f"JSONエラー:\n{e}")
                return
            self._cfg.setdefault("auto_profile", {})["rules"] = new
            if CFG_OK:
                cfgmod.save_config(self._cfg)
            self._agent.reload_config()
            win.destroy()
            messagebox.showinfo("ルール編集", "自動切替ルールを更新しました。")

        btns = ctk.CTkFrame(win, fg_color="transparent")
        btns.pack(pady=10)
        ctk.CTkButton(btns, text="キャンセル", width=110, fg_color="#555",
                      hover_color="#666", command=win.destroy).pack(side="left", padx=8)
        ctk.CTkButton(btns, text="保存", width=110, command=_save).pack(side="left", padx=8)
        win.after(60, lambda: (win.grab_set(), win.focus_force()))

    def _clear_log(self):
        self.txt_log.delete("1.0", "end")

    def _append_log(self, line: str):
        self.txt_log.insert("end", line + "\n")
        self.txt_log.see("end")

    # ---- ライブ反映（エディタから呼ばれる）----
    def _on_live_apply(self, cfg: dict) -> bool:
        return self._agent.send_live_config(cfg)

    def _reconnect(self):
        self._agent.stop()
        self.after(500, self._agent.start)

    # ---- queue ポーリング ----
    def _poll_queues(self):
        while not self._log_q.empty():
            try:
                self._append_log(self._log_q.get_nowait())
            except queue.Empty:
                break
        while not self._status_q.empty():
            try:
                self._apply_status(self._status_q.get_nowait())
            except queue.Empty:
                break
        self.after(200, self._poll_queues)

    def _apply_status(self, st: dict):
        if "connected" in st:
            self._connected = st["connected"]
            if st["connected"]:
                self.lbl_conn.configure(text="● 接続中", text_color="#22c55e")
            else:
                self.lbl_conn.configure(text="● 未接続", text_color="#888")
            if TRAY_OK:
                self._update_tray_icon()
        if "port" in st:
            self.lbl_port.configure(text=f"ポート: {st['port']}")
        if "volume" in st:
            self.lbl_vol.configure(text=f"音量: {st['volume']}%")
        if "mic_volume" in st:
            self.lbl_mic.configure(text=f"マイク: {st['mic_volume']}%")
        if "weather" in st:
            self.lbl_wx.configure(text=f"天気: {st['weather']} {st.get('temp', '—')}℃")
        if "profile" in st:
            self.lbl_prof.configure(text=f"プロファイル: {st['profile']}")

    # ---- システムトレイ ----
    def _make_tray_image(self, connected: bool):
        img = Image.new("RGB", (64, 64), (40, 40, 40))
        d = ImageDraw.Draw(img)
        color = (60, 200, 90) if connected else (130, 130, 130)
        for gx in range(2):
            for gy in range(2):
                x = 12 + gx * 26
                y = 12 + gy * 26
                d.rounded_rectangle([x, y, x + 18, y + 18], radius=4, fill=color)
        return img

    def _setup_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("表示", self._show_window, default=True),
            pystray.MenuItem("接続", lambda: self._agent.start()),
            pystray.MenuItem("切断", lambda: self._agent.stop()),
            pystray.MenuItem("再接続", lambda: self._reconnect()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("終了", self._quit_from_tray),
        )
        self._tray_icon = pystray.Icon(
            "streamdeck", self._make_tray_image(False),
            "StreamDeck Controller", menu)
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    def _update_tray_icon(self):
        if self._tray_icon:
            self._tray_icon.icon = self._make_tray_image(self._connected)

    def _hide_to_tray(self):
        self.withdraw()

    def _show_window(self, icon=None, item=None):
        self.after(0, self.deiconify)
        self.after(0, self.lift)

    def _quit_from_tray(self, icon=None, item=None):
        self._agent.stop()
        if self._tray_icon:
            self._tray_icon.stop()
        self.after(0, self.destroy)

    def _on_close(self):
        self._agent.stop()
        if self._tray_icon:
            self._tray_icon.stop()
        self.destroy()


# ============================================================
#  多重起動防止（Windows 名前付きミューテックス）
# ============================================================
_MUTEX_NAME = "StreamDeckController_SingleInstance_Mutex"
_single_instance_handle = None   # プロセス終了までミューテックスを保持


def acquire_single_instance() -> bool:
    """まだ起動していなければ True。既に起動中なら False。
    ミューテックスは _single_instance_handle でプロセス生存中ずっと保持する
    （ハンドルを開いている間だけ他プロセスから存在が見える）。"""
    global _single_instance_handle
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL,
                                          wintypes.LPCWSTR]
        ERROR_ALREADY_EXISTS = 183
        _single_instance_handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
        return kernel32.GetLastError() != ERROR_ALREADY_EXISTS
    except Exception:
        # ミューテックスが使えない環境ではチェックをスキップ（従来どおり起動）
        return True


def _focus_existing_window():
    """既存インスタンスのウィンドウを前面に復帰させる（ベストエフォート）。"""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, "StreamDeck Controller")
        if hwnd:
            user32.ShowWindow(hwnd, 9)        # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def _notify_already_running():
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            "StreamDeck Controller は既に起動しています。\n"
            "タスクトレイのアイコンから表示できます。",
            "StreamDeck Controller",
            0x40)   # MB_ICONINFORMATION
    except Exception:
        pass


if __name__ == "__main__":
    # 二重起動を防止：既に起動中なら既存ウィンドウを前面化して静かに終了
    if not acquire_single_instance():
        _focus_existing_window()
        _notify_already_running()
        sys.exit(0)
    app = StreamDeckApp()
    app.mainloop()
