# streamdeck_app.py  v1
# 統合UI：常駐エージェント（Pico通信）＋ 設定GUI を1つのウィンドウに統合
#
# 起動: python streamdeck_app.py
# 依存: pip install -r requirements.txt
#   pyserial, pycaw, psutil, comtypes, requests, pyautogui
#
# 特徴:
#   - 起動すると裏でPicoと自動接続・常駐（音量/マイク/天気/アプリを送信）
#   - タブUIで「状態」「プロファイル設定」「ディスプレイ」「ログ」を切替
#   - スレッド↔GUIは queue で安全に連携
#   - 接続状態・現在値をリアルタイム表示

from __future__ import annotations

import json
import time
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

# ===== agent.py の機能を再利用 =====
# 同じフォルダの agent.py から関数群を import する
try:
    import agent as ag
    AGENT_OK = True
except Exception as e:
    AGENT_OK = False
    print(f"[WARN] agent.py を読み込めません: {e}")

# ===== configurator.py の設定機能を再利用 =====
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

CONFIG_PATH = "streamdeck_config.json"


# ============================================================
#  常駐エージェント（GUIと連携するスレッド版）
# ============================================================
class AgentThread:
    """agent.py の StreamDeckAgent をGUI連携用にラップしたもの。
    ログとステータスを queue 経由でGUIに渡す。"""

    def __init__(self, log_q: queue.Queue, status_q: queue.Queue):
        self._log_q = log_q
        self._status_q = status_q
        self._ser = None
        self._running = False
        self._config = {}
        self._weather = {}
        self._weather_at = 0
        self._threads = []
        self._send_lock = threading.Lock()   # info/auto/live の書き込み競合を防ぐ
        self._current_profile = None      # 現在のプロファイル名（自動切替の重複送信防止）
        self._auto_enabled = False        # 前面アプリ連動 自動切替の有効/無効
        self._auto_rules = {}             # {exe名(小文字): プロファイル名}
        self._load_config()
        self._load_auto_profile()

    # ---- 自動切替ルールの読み込み ----
    def _load_auto_profile(self):
        ap = self._config.get("auto_profile") or {}
        self._auto_enabled = bool(ap.get("enabled", False))
        rules = ap.get("rules")
        if not rules and CFG_OK:
            rules = cfgmod.DEFAULT_AUTO_RULES
        self._auto_rules = {str(k).lower(): v for k, v in (rules or {}).items()}

    # ---- ログ/ステータス送信 ----
    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self._log_q.put(f"[{ts}] {msg}")

    def _status(self, **kwargs):
        self._status_q.put(kwargs)

    # ---- 設定読み込み ----
    def _load_config(self):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                self._config = json.load(f)
            self._log(f"設定 {CONFIG_PATH} を読み込みました")
        except FileNotFoundError:
            self._log(f"設定ファイルが無いのでデフォルトで動作します")
            self._config = {}

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

    # ---- 受信ループ ----
    def _receive_loop(self):
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
            self._current_profile = pf     # 手動(SW1)切替に追従
            self._log(f"プロファイル → {pf}")
            self._status(profile=pf)
        elif t == "button":
            sw = msg.get("sw")
            enc = msg.get("enc")
            d = msg.get("dir", "")
            pf = msg.get("profile", "")
            action = msg.get("action", "")
            if sw is not None:
                self._log(f"SW{sw+1} [{pf}] {action}")
                if action and AGENT_OK:
                    ag.send_key(action)
            elif enc is not None:
                self._log(f"ENC{enc+1} {d} [{pf}] {action}")
                if action and AGENT_OK:
                    ag.send_key(action)

    # ---- 情報送信ループ ----
    def _get_weather_cached(self) -> dict:
        now = time.time()
        interval = getattr(ag, "WEATHER_INTERVAL", 600) if AGENT_OK else 600
        if not self._weather or now - self._weather_at > interval:
            if AGENT_OK:
                self._weather = ag.get_weather()
                self._weather_at = now
                self._log(f"天気更新: {self._weather.get('desc','?')}")
        return self._weather

    def _info_loop(self):
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
            payload = {
                "type": "info",
                "volume": vol,
                "mic_volume": mic,
                "apps": apps,
                "weather": wx,
            }
            self._send(payload)
            # GUIのステータス更新
            self._status(volume=vol, mic_volume=mic,
                         weather=wx.get("desc", "—"),
                         temp=wx.get("temp", "—"))
            time.sleep(interval)

    # ---- 起動/停止 ----
    def start(self):
        if self._running:
            return
        self._running = True
        self._connect()
        rx = threading.Thread(target=self._receive_loop, daemon=True)
        info = threading.Thread(target=self._info_loop, daemon=True)
        auto = threading.Thread(target=self._auto_profile_loop, daemon=True)
        rx.start()
        info.start()
        auto.start()
        self._threads = [rx, info, auto]
        self._log("エージェント開始")

    def stop(self):
        self._running = False
        if self._ser and self._ser.is_open:
            self._ser.close()
        self._status(connected=False, port="—")
        self._log("エージェント停止")

    def reload_config(self):
        self._load_config()
        self._load_auto_profile()

    # ---- ライブ設定反映（config.py書き込みなしで即反映） ----
    def send_live_config(self, cfg: dict) -> bool:
        if not (self._ser and self._ser.is_open):
            self._log("Pico未接続のためライブ反映できません")
            return False
        if not CFG_OK:
            self._log("configurator.py が無いためライブ反映できません")
            return False
        try:
            profiles, sm, em = cfgmod.expand_maps(cfg)
        except Exception as e:
            self._log(f"設定展開エラー: {e}")
            return False
        self._send({"type": "config", "profiles": profiles,
                    "switches": sm, "encoders": em})
        self._log("ライブ設定を送信しました（書込なし即反映）")
        # 自動切替ルールも最新化
        ap = cfg.get("auto_profile") or {}
        rules = ap.get("rules") or {}
        if rules:
            self._auto_rules = {str(k).lower(): v for k, v in rules.items()}
        return True

    # ---- 前面アプリ連動 自動プロファイル切替 ----
    def set_auto_enabled(self, enabled: bool):
        self._auto_enabled = bool(enabled)
        self._log(f"自動プロファイル切替: {'ON' if enabled else 'OFF'}")

    def set_profile_remote(self, name: str):
        if self._ser and self._ser.is_open:
            self._send({"type": "set_profile", "profile": name})

    def _foreground_proc_name(self):
        """最前面ウィンドウのプロセス実行ファイル名を返す（Windows専用）"""
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
        """1秒ごとに前面アプリを監視し、ルールに一致したらプロファイルを切替える。
        前面アプリが変わった時だけ判定するので手動切替と競合しにくい。"""
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


# ============================================================
#  統合GUIアプリ
# ============================================================
class StreamDeckApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("StreamDeck Controller")
        self.geometry("640x560")

        self._log_q = queue.Queue()
        self._status_q = queue.Queue()
        self._agent = AgentThread(self._log_q, self._status_q)

        # 設定データ
        self._cfg = self._load_config()

        # 状態フラグ
        self._connected = False
        self._tray_icon = None

        self._build_ui()
        self._poll_queues()

        # 起動時に自動でエージェント開始
        self.after(500, self._agent.start)

        # トレイアイコン起動
        if TRAY_OK:
            self._setup_tray()

        # ×ボタンはトレイに最小化（TRAY_OKなら）
        if TRAY_OK:
            self.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        else:
            self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- 設定ロード ----
    def _load_config(self) -> dict:
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg = json.load(f)
        except FileNotFoundError:
            cfg = cfgmod.default_config() if CFG_OK else {}
        # auto_profile が無い古い設定にデフォルトを補完
        if "auto_profile" not in cfg:
            default_rules = dict(cfgmod.DEFAULT_AUTO_RULES) if CFG_OK else {}
            cfg["auto_profile"] = {"enabled": False, "rules": default_rules}
        return cfg

    def _save_config(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self._cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror("保存エラー", str(e))

    # ---- UI構築 ----
    def _build_ui(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        self.tab_status = ttk.Frame(nb)
        self.tab_profile = ttk.Frame(nb)
        self.tab_display = ttk.Frame(nb)
        self.tab_log = ttk.Frame(nb)

        nb.add(self.tab_status, text="状態")
        nb.add(self.tab_profile, text="プロファイル設定")
        nb.add(self.tab_display, text="ディスプレイ")
        nb.add(self.tab_log, text="ログ")

        self._build_status_tab()
        self._build_profile_tab()
        self._build_display_tab()
        self._build_log_tab()

    # ---- 状態タブ ----
    def _build_status_tab(self):
        f = self.tab_status
        pad = {"padx": 10, "pady": 6}

        # 接続状態
        self.var_conn = tk.StringVar(value="● 未接続")
        self.lbl_conn = tk.Label(f, textvariable=self.var_conn,
                                 font=("", 14, "bold"), fg="gray")
        self.lbl_conn.grid(row=0, column=0, columnspan=2, sticky="w", **pad)

        self.var_port = tk.StringVar(value="ポート: —")
        tk.Label(f, textvariable=self.var_port).grid(
            row=1, column=0, columnspan=2, sticky="w", **pad)

        ttk.Separator(f, orient="horizontal").grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=8)

        # リアルタイム値
        self.var_vol = tk.StringVar(value="音量: —")
        self.var_mic = tk.StringVar(value="マイク: —")
        self.var_wx = tk.StringVar(value="天気: —")
        self.var_profile = tk.StringVar(value="プロファイル: —")

        for i, v in enumerate([self.var_vol, self.var_mic,
                               self.var_wx, self.var_profile]):
            tk.Label(f, textvariable=v, font=("", 11)).grid(
                row=3+i, column=0, sticky="w", **pad)

        ttk.Separator(f, orient="horizontal").grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=8)

        # 接続/切断ボタン
        btnf = tk.Frame(f)
        btnf.grid(row=8, column=0, columnspan=2, sticky="w", **pad)
        ttk.Button(btnf, text="接続", command=self._agent.start).pack(side="left", padx=4)
        ttk.Button(btnf, text="切断", command=self._agent.stop).pack(side="left", padx=4)
        ttk.Button(btnf, text="再接続", command=self._reconnect).pack(side="left", padx=4)

        ttk.Separator(f, orient="horizontal").grid(
            row=9, column=0, columnspan=2, sticky="ew", pady=8)

        # 自動起動チェックボックス
        init_auto = autostart.is_enabled() if AUTOSTART_OK else False
        self.var_autostart = tk.BooleanVar(value=init_auto)
        chk = ttk.Checkbutton(
            f, text="Windows起動時に自動で起動する",
            variable=self.var_autostart, command=self._toggle_autostart)
        chk.grid(row=10, column=0, columnspan=2, sticky="w", **pad)
        if not AUTOSTART_OK:
            chk.config(state="disabled")

        # 前面アプリ連動 自動プロファイル切替
        init_auto = bool(self._cfg.get("auto_profile", {}).get("enabled", False))
        self.var_autoprofile = tk.BooleanVar(value=init_auto)
        self._agent.set_auto_enabled(init_auto)
        autof = tk.Frame(f)
        autof.grid(row=11, column=0, columnspan=2, sticky="w", **pad)
        ttk.Checkbutton(
            autof, text="前面アプリで自動プロファイル切替",
            variable=self.var_autoprofile,
            command=self._toggle_autoprofile).pack(side="left")
        ttk.Button(autof, text="ルール編集",
                   command=self._edit_auto_rules).pack(side="left", padx=8)

        # トレイ常駐の説明
        note = "※ ×ボタンでタスクトレイに最小化します（常駐継続）" \
            if TRAY_OK else "※ pystray未導入のためトレイ常駐は無効です"
        tk.Label(f, text=note, fg="gray").grid(
            row=12, column=0, columnspan=2, sticky="w", **pad)

    def _toggle_autoprofile(self):
        en = self.var_autoprofile.get()
        self._agent.set_auto_enabled(en)
        self._cfg.setdefault("auto_profile", {})["enabled"] = en
        self._save_config()

    def _edit_auto_rules(self):
        """自動切替ルール（JSON）を既定のエディタで開く。編集後は再読込で反映。"""
        import os
        self._save_config()   # 最新状態をファイルに落としてから開く
        try:
            os.startfile(CONFIG_PATH)   # type: ignore[attr-defined]
            messagebox.showinfo(
                "ルール編集",
                "streamdeck_config.json の \"auto_profile\" → \"rules\" を編集してください。\n"
                "（\"プロセス名.exe\": \"プロファイル名\" の形式）\n\n"
                "編集・保存したら「プロファイル設定」タブの「設定を再読込」を押すと反映されます。")
        except Exception as e:
            messagebox.showerror("ルール編集", str(e))

    def _toggle_autostart(self):
        if not AUTOSTART_OK:
            return
        ok = autostart.toggle(self.var_autostart.get())
        if ok:
            state = "登録" if self.var_autostart.get() else "解除"
            messagebox.showinfo("自動起動", f"自動起動を{state}しました")
        else:
            messagebox.showerror("自動起動", "設定に失敗しました")
            # 失敗時はチェックを戻す
            self.var_autostart.set(autostart.is_enabled())

    def _reconnect(self):
        self._agent.stop()
        self.after(500, self._agent.start)

    # ---- プロファイルタブ（configuratorの簡易版を埋め込み） ----
    def _build_profile_tab(self):
        f = self.tab_profile
        if not CFG_OK:
            tk.Label(f, text="configurator.py が読み込めないため\n設定機能は利用できません",
                     fg="red").pack(padx=20, pady=20)
            return

        info = tk.Label(
            f,
            text="キー割り当ての詳細設定は configurator を使います。\n"
                 "ここではプロファイル一覧の確認と、設定ファイルの再読込ができます。",
            justify="left")
        info.pack(anchor="w", padx=12, pady=8)

        # プロファイル一覧表示
        profiles = self._cfg.get("profiles", [])
        lf = ttk.LabelFrame(f, text="プロファイル")
        lf.pack(fill="x", padx=12, pady=6)
        for i, p in enumerate(profiles):
            tk.Label(lf, text=f"{i+1}. {p}").pack(anchor="w", padx=10, pady=2)

        # ボタン
        btnf = tk.Frame(f)
        btnf.pack(anchor="w", padx=12, pady=10)
        ttk.Button(btnf, text="設定エディタを開く",
                   command=self._open_configurator).pack(side="left", padx=4)
        ttk.Button(btnf, text="設定を再読込",
                   command=self._reload_config).pack(side="left", padx=4)
        ttk.Button(btnf, text="ライブ反映（書込なし）",
                   command=self._live_reflect).pack(side="left", padx=4)

        tk.Label(f, text="※「ライブ反映」は保存済み設定をPicoへ即送信します"
                        "（config.py書き込み・再起動は不要）",
                 fg="gray", justify="left").pack(anchor="w", padx=12)

    def _open_configurator(self):
        """別ウィンドウでconfiguratorのフルGUIを開く。
        ライブ反映コールバックを渡し、エディタ内から即反映できるようにする。"""
        if not CFG_OK:
            return
        try:
            win = cfgmod.App(on_live_apply=self._live_apply_from_editor)
            win.mainloop()
        except Exception as e:
            messagebox.showerror("エラー", f"設定エディタを開けません:\n{e}")

    def _live_apply_from_editor(self, cfg: dict) -> bool:
        """configurator の「ライブ反映」ボタンから呼ばれる。
        （configurator 側で既に JSON 保存済み）"""
        self._cfg = cfg
        self._agent.reload_config()
        return self._agent.send_live_config(cfg)

    def _live_reflect(self):
        """保存済み設定を読み直してPicoへライブ送信する"""
        self._cfg = self._load_config()
        self._agent.reload_config()
        if self._agent.send_live_config(self._cfg):
            messagebox.showinfo("ライブ反映",
                "Picoへ即時反映しました（config.py書き込み・再起動は不要）。")
        else:
            messagebox.showwarning("ライブ反映",
                "Picoへ反映できませんでした。接続状態を確認してください。")

    def _reload_config(self):
        self._cfg = self._load_config()
        self._agent.reload_config()
        messagebox.showinfo("再読込", "設定を再読込しました")

    # ---- ディスプレイタブ ----
    def _build_display_tab(self):
        f = self.tab_display
        tk.Label(f, text="ディスプレイの明るさ", font=("", 11)).pack(
            anchor="w", padx=12, pady=8)

        cur = self._cfg.get("display", {}).get("brightness", 80)
        self.var_bright = tk.IntVar(value=cur)
        scale = ttk.Scale(f, from_=0, to=100, orient="horizontal",
                          variable=self.var_bright, length=300,
                          command=lambda v: self.var_bright_lbl.set(
                              f"{int(float(v))}%"))
        scale.pack(anchor="w", padx=12)

        self.var_bright_lbl = tk.StringVar(value=f"{cur}%")
        tk.Label(f, textvariable=self.var_bright_lbl).pack(anchor="w", padx=12)

        tk.Label(f, text="※ 変更を反映するには Pico への書き込みが必要です",
                 fg="gray").pack(anchor="w", padx=12, pady=8)

    # ---- ログタブ ----
    def _build_log_tab(self):
        f = self.tab_log
        self.txt_log = tk.Text(f, height=20, wrap="word", state="disabled",
                               font=("Consolas", 9))
        self.txt_log.pack(fill="both", expand=True, padx=8, pady=8)

        btnf = tk.Frame(f)
        btnf.pack(anchor="e", padx=8, pady=4)
        ttk.Button(btnf, text="クリア", command=self._clear_log).pack(side="right")

    def _clear_log(self):
        self.txt_log.config(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.config(state="disabled")

    def _append_log(self, line: str):
        self.txt_log.config(state="normal")
        self.txt_log.insert("end", line + "\n")
        self.txt_log.see("end")
        self.txt_log.config(state="disabled")

    # ---- queue ポーリング（GUIスレッドで実行） ----
    def _poll_queues(self):
        # ログ
        while not self._log_q.empty():
            try:
                self._append_log(self._log_q.get_nowait())
            except queue.Empty:
                break
        # ステータス
        while not self._status_q.empty():
            try:
                st = self._status_q.get_nowait()
                self._apply_status(st)
            except queue.Empty:
                break
        self.after(200, self._poll_queues)

    def _apply_status(self, st: dict):
        if "connected" in st:
            self._connected = st["connected"]
            if st["connected"]:
                self.var_conn.set("● 接続中")
                self.lbl_conn.config(fg="green")
            else:
                self.var_conn.set("● 未接続")
                self.lbl_conn.config(fg="gray")
            # トレイアイコンの色も更新
            if TRAY_OK:
                self._update_tray_icon()
        if "port" in st:
            self.var_port.set(f"ポート: {st['port']}")
        if "volume" in st:
            self.var_vol.set(f"音量: {st['volume']}%")
        if "mic_volume" in st:
            self.var_mic.set(f"マイク: {st['mic_volume']}%")
        if "weather" in st:
            temp = st.get("temp", "—")
            self.var_wx.set(f"天気: {st['weather']} {temp}℃")
        if "profile" in st:
            self.var_profile.set(f"プロファイル: {st['profile']}")

    # ---- システムトレイ ----
    def _make_tray_image(self, connected: bool):
        """トレイアイコン画像を生成（接続=緑, 未接続=灰）"""
        img = Image.new("RGB", (64, 64), (40, 40, 40))
        d = ImageDraw.Draw(img)
        # 外枠（StreamDeck風の四角ボタン配置イメージ）
        color = (60, 200, 90) if connected else (130, 130, 130)
        for gx in range(2):
            for gy in range(2):
                x = 12 + gx * 26
                y = 12 + gy * 26
                d.rounded_rectangle([x, y, x+18, y+18], radius=4, fill=color)
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
            "streamdeck",
            self._make_tray_image(False),
            "StreamDeck Controller",
            menu,
        )
        # トレイは別スレッドで動かす
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    def _update_tray_icon(self):
        if self._tray_icon:
            self._tray_icon.icon = self._make_tray_image(self._connected)

    def _hide_to_tray(self):
        """×ボタン: ウィンドウを隠してトレイに常駐"""
        self.withdraw()

    def _show_window(self, icon=None, item=None):
        """トレイから表示"""
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


if __name__ == "__main__":
    app = StreamDeckApp()
    app.mainloop()
