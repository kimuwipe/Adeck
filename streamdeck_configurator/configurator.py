# configurator.py  v1.1
# StreamDeck GUI 設定アプリ（Windows / Python 3.10+）
# 依存: 標準ライブラリのみ（tkinter, json, pathlib）
#
# 起動: python configurator.py

from __future__ import annotations   # 古いPythonでも型注釈を許可

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
from pathlib import Path

APP_TITLE   = "StreamDeck 設定"
CONFIG_JSON = Path("streamdeck_config.json")

# プロファイル定義（config.py の PROFILES と一致させる）
PROFILES = ["汎用", "SolidWorks", "音声", "開発"]
SW_COUNT  = 8
ENC_COUNT = 4

# キー選択肢
KEY_OPTIONS = [
    "（なし）",
    # ファンクション
    "F1","F2","F3","F4","F5","F6","F7","F8",
    "F9","F10","F11","F12",
    "F13","F14","F15","F16","F17","F18","F19","F20",
    # メディア
    "VOLUME_UP","VOLUME_DOWN","MUTE",
    "MEDIA_PLAY","MEDIA_NEXT","MEDIA_PREV",
    # 汎用操作
    "UNDO","REDO","SAVE",
    "ZOOM_IN","ZOOM_OUT","ZOOM_FIT",
    "TAB_NEXT","TAB_PREV","NEW_TAB",
    # Windows
    "WIN_SNIP","VDESK_NEXT","VDESK_PREV",
    "WIN_MAX","TASK_MGR","WIN_LOCK",
    # SolidWorks
    "SW_SHORTCUT_BAR","SW_REBUILD","SW_REBUILD_FULL",
    "SW_NORMAL_TO","SW_FILTER_CLEAR","SW_DISPLAY_CYCLE",
    "SW_MAGNIFIER","SW_ISO","SW_VIEW_NEXT","SW_VIEW_PREV",
    # 開発
    "SHIFT_F5","DEV_TERMINAL","DEV_COMMENT","DEV_GOTO_DEF",
    "FONT_UP","FONT_DOWN",
    # エージェント経由
    "MIC_UP","MIC_DOWN","MIC_MUTE","APP_CALC",
    # アプリ起動
    "APP_LAUNCH",
    # プロファイル
    "PROFILE_NEXT",
]


# ===== デフォルト設定 =====
def default_config() -> dict:
    sw_maps = [
        ["PROFILE_NEXT","WIN_SNIP","VDESK_NEXT","VDESK_PREV",
         "WIN_MAX","TASK_MGR","APP_CALC","WIN_LOCK"],
        ["PROFILE_NEXT","SW_SHORTCUT_BAR","SW_REBUILD","SW_REBUILD_FULL",
         "SW_NORMAL_TO","SW_FILTER_CLEAR","SW_DISPLAY_CYCLE","SW_MAGNIFIER"],
        ["PROFILE_NEXT","MEDIA_PLAY","MEDIA_NEXT","MEDIA_PREV",
         "MUTE","F13","F14","F15"],
        ["PROFILE_NEXT","F5","SHIFT_F5","F9",
         "F10","F11","DEV_TERMINAL","DEV_COMMENT"],
    ]
    enc_maps = [
        [("VOLUME_UP","VOLUME_DOWN","MUTE"),
         ("UNDO","REDO","SAVE"),
         ("ZOOM_IN","ZOOM_OUT","ZOOM_FIT"),
         ("TAB_NEXT","TAB_PREV","NEW_TAB")],
        [("VOLUME_UP","VOLUME_DOWN","MUTE"),
         ("UNDO","REDO","SAVE"),
         ("ZOOM_IN","ZOOM_OUT","ZOOM_FIT"),
         ("SW_VIEW_NEXT","SW_VIEW_PREV","SW_ISO")],
        [("VOLUME_UP","VOLUME_DOWN","MUTE"),
         ("UNDO","REDO","SAVE"),
         ("ZOOM_IN","ZOOM_OUT","ZOOM_FIT"),
         ("MIC_UP","MIC_DOWN","MIC_MUTE")],
        [("VOLUME_UP","VOLUME_DOWN","MUTE"),
         ("UNDO","REDO","SAVE"),
         ("ZOOM_IN","ZOOM_OUT","ZOOM_FIT"),
         ("FONT_UP","FONT_DOWN","DEV_GOTO_DEF")],
    ]
    return {
        "profiles": PROFILES,
        "switches": [
            [{"key": k, "app": ""} for k in sw_maps[p]]
            for p in range(len(PROFILES))
        ],
        "encoders": [
            [{"cw": cw, "ccw": ccw, "push": push, "app_cw": "",
              "app_ccw": "", "app_push": ""}
             for cw, ccw, push in enc_maps[p]]
            for p in range(len(PROFILES))
        ],
        "display": {"brightness": 80},
    }


# ===== JSON → config.py 変換 =====
def config_to_py(cfg: dict) -> str:
    lines = [
        "# config.py  (configurator.py により自動生成)",
        "# 手動編集は configurator.py で上書きされます",
        "",
        f'PROFILES = {json.dumps(cfg["profiles"], ensure_ascii=False)}',
        "",
        "SWITCH_MAP = [",
    ]
    for p_sws in cfg["switches"]:
        lines.append("    [")
        for sw in p_sws:
            k = sw.get("key", "（なし）")
            if k == "APP_LAUNCH" and sw.get("app"):
                val = f'"APP:{sw["app"]}"'
            elif k in ("（なし）", None):
                val = "None"
            else:
                val = f'"{k}"'
            lines.append(f"        {val},")
        lines.append("    ],")
    lines.append("]")
    lines.append("")
    lines.append("_ENC_COMMON = [")
    # ENC1〜3 は全プロファイル同じ（プロファイル0から取得）
    for i in range(3):
        enc = cfg["encoders"][0][i]
        cw   = f'"{enc["cw"]}"'   if enc["cw"]   not in ("（なし）", None) else "None"
        ccw  = f'"{enc["ccw"]}"'  if enc["ccw"]  not in ("（なし）", None) else "None"
        push = f'"{enc["push"]}"' if enc["push"] not in ("（なし）", None) else "None"
        lines.append(f"    ({cw}, {ccw}, {push}),")
    lines.append("]")
    lines.append("")
    lines.append("_ENC4_BY_PROFILE = [")
    for p in range(len(PROFILES)):
        enc  = cfg["encoders"][p][3]
        cw   = f'"{enc["cw"]}"'   if enc["cw"]   not in ("（なし）", None) else "None"
        ccw  = f'"{enc["ccw"]}"'  if enc["ccw"]  not in ("（なし）", None) else "None"
        push = f'"{enc["push"]}"' if enc["push"] not in ("（なし）", None) else "None"
        lines.append(f"    ({cw}, {ccw}, {push}),  # {PROFILES[p]}")
    lines.append("]")
    lines.append("")
    lines.append("ENCODER_MAP = [")
    lines.append("    _ENC_COMMON + [_ENC4_BY_PROFILE[i]]")
    lines.append("    for i in range(len(PROFILES))")
    lines.append("]")
    lines.append("")
    br = cfg.get("display", {}).get("brightness", 80)
    lines += [
        f"DISPLAY_BRIGHTNESS = {br}",
        "DISPLAY_ROTATION   = 0",
        "SWITCH_DEBOUNCE_MS  = 20",
        "ENCODER_DEBOUNCE_MS = 5",
        "",
    ]
    return "\n".join(lines)


# ===== Pico ドライブ検出 =====
def find_pico_drive() -> Path | None:
    import string
    for letter in string.ascii_uppercase:
        drive = Path(f"{letter}:\\")
        if drive.exists() and ((drive/"main.py").exists() or (drive/"boot.py").exists()):
            return drive
    return None


# ===== GUI アプリ =====
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.resizable(False, False)
        self.configure(bg="#F4F4F0")

        self.cfg            = default_config()
        self._current_prof  = 0   # 表示中のプロファイル index
        self._sw_vars       = []  # [profile][sw] = {key, app}
        self._enc_vars      = []  # [profile][enc] = {cw,ccw,push, app_*}

        self._load_json()
        self._build_ui()
        self._refresh_ui()

    # ---------- JSON ----------
    def _load_json(self):
        if CONFIG_JSON.exists():
            try:
                with open(CONFIG_JSON, encoding="utf-8") as f:
                    self.cfg = json.load(f)
            except Exception:
                pass

    def _save_json(self):
        with open(CONFIG_JSON, "w", encoding="utf-8") as f:
            json.dump(self.cfg, f, ensure_ascii=False, indent=2)

    # ---------- UI 構築 ----------
    def _build_ui(self):
        # タイトルバー
        bar = tk.Frame(self, bg="#E8E8E4", pady=8)
        bar.pack(fill="x")
        tk.Label(bar, text=APP_TITLE, font=("Yu Gothic UI",13,"bold"),
                 bg="#E8E8E4").pack(side="left", padx=14)
        self._conn_lbl = tk.Label(bar, text="● Pico未接続",
                                  font=("Yu Gothic UI",10),
                                  bg="#E8E8E4", fg="#999")
        self._conn_lbl.pack(side="right", padx=14)
        tk.Button(bar, text="接続確認", font=("Yu Gothic UI",9),
                  relief="flat", bg="#D8D8D4",
                  command=self._check_pico).pack(side="right", padx=4)

        # プロファイルタブ
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook",     background="#F4F4F0", borderwidth=0)
        style.configure("TNotebook.Tab", background="#E0E0DC", foreground="#555",
                        padding=[14,6], font=("Yu Gothic UI",10))
        style.map("TNotebook.Tab",
                  background=[("selected","#FFFFFF")],
                  foreground=[("selected","#1A1A1A")])

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        # 各プロファイルタブ
        self._sw_vars  = [[] for _ in PROFILES]
        self._enc_vars = [[] for _ in PROFILES]
        for pi, pname in enumerate(PROFILES):
            frame = tk.Frame(nb, bg="#FFFFFF")
            nb.add(frame, text=f"  {pname}  ")
            self._build_profile_tab(frame, pi)

        # ディスプレイタブ
        disp_frame = tk.Frame(nb, bg="#FFFFFF")
        nb.add(disp_frame, text="  ディスプレイ  ")
        self._build_display_tab(disp_frame)

        # フッター
        footer = tk.Frame(self, bg="#E8E8E4", pady=8)
        footer.pack(fill="x")
        tk.Button(footer, text="リセット", font=("Yu Gothic UI",10),
                  relief="flat", bg="#D8D8D4",
                  command=self._reset, padx=10).pack(side="left", padx=12)
        tk.Button(footer, text="Picoに書き込む",
                  font=("Yu Gothic UI",10,"bold"),
                  relief="flat", bg="#2563EB", fg="white",
                  activebackground="#1D4ED8",
                  command=self._write_to_pico, padx=14).pack(side="right", padx=12)
        tk.Button(footer, text="設定を保存", font=("Yu Gothic UI",10),
                  relief="flat", bg="#D8D8D4",
                  command=self._save, padx=10).pack(side="right", padx=4)

    def _build_profile_tab(self, parent: tk.Frame, pi: int):
        canvas = tk.Canvas(parent, bg="#FFFFFF", highlightthickness=0)
        scroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True)

        inner = tk.Frame(canvas, bg="#FFFFFF")
        canvas.create_window((0,0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        # スイッチ
        tk.Label(inner, text="スイッチ（8個）",
                 font=("Yu Gothic UI",10,"bold"),
                 bg="#FFFFFF", fg="#555").pack(anchor="w", padx=16, pady=(12,4))
        for si in range(SW_COUNT):
            self._build_sw_row(inner, pi, si)

        # エンコーダ
        tk.Label(inner, text="エンコーダ（4個）",
                 font=("Yu Gothic UI",10,"bold"),
                 bg="#FFFFFF", fg="#555").pack(anchor="w", padx=16, pady=(14,4))
        for ei in range(ENC_COUNT):
            self._build_enc_row(inner, pi, ei)

    def _build_sw_row(self, parent, pi, si):
        row = tk.Frame(parent, bg="#FFFFFF")
        row.pack(fill="x", padx=16, pady=2)
        tk.Frame(row, bg="#EAEAE6", height=1).pack(fill="x", pady=(0,4))

        inner = tk.Frame(row, bg="#FFFFFF")
        inner.pack(fill="x")

        tk.Label(inner, text=f"SW{si+1}", font=("Yu Gothic UI",10,"bold"),
                 bg="#FFFFFF", width=5, anchor="w").pack(side="left")

        key_var = tk.StringVar()
        key_cb  = ttk.Combobox(inner, textvariable=key_var,
                                values=KEY_OPTIONS, width=20, state="readonly",
                                font=("Yu Gothic UI",10))
        key_cb.pack(side="left", padx=(8,6))

        app_var = tk.StringVar()
        app_btn = tk.Button(inner, text="📁 .exe",
                            font=("Yu Gothic UI",9), relief="flat",
                            bg="#EEEEE8", activebackground="#DDDDD8",
                            command=lambda p=pi, s=si: self._browse_sw(p, s))
        app_btn.pack(side="left", padx=4)

        app_lbl = tk.Label(inner, textvariable=app_var,
                           font=("Yu Gothic UI",9), fg="#2563EB",
                           bg="#FFFFFF", anchor="w")
        app_lbl.pack(side="left", padx=4, fill="x", expand=True)

        self._sw_vars[pi].append({"key": key_var, "app": app_var})

    def _build_enc_row(self, parent, pi, ei):
        row = tk.Frame(parent, bg="#FFFFFF")
        row.pack(fill="x", padx=16, pady=2)
        tk.Frame(row, bg="#EAEAE6", height=1).pack(fill="x", pady=(0,4))

        header = tk.Frame(row, bg="#FFFFFF")
        header.pack(fill="x")
        tk.Label(header, text=f"ENC{ei+1}",
                 font=("Yu Gothic UI",10,"bold"),
                 bg="#FFFFFF").pack(side="left")

        dirs   = [("CW（時計回り）","cw"), ("CCW（反時計回り）","ccw"), ("Push（押し込み）","push")]
        d_vars = {}
        for dlabel, dkey in dirs:
            sub = tk.Frame(row, bg="#FFFFFF")
            sub.pack(fill="x", padx=24, pady=2)

            tk.Label(sub, text=dlabel, font=("Yu Gothic UI",9),
                     fg="#666", bg="#FFFFFF", width=16,
                     anchor="w").pack(side="left")

            kv  = tk.StringVar()
            kcb = ttk.Combobox(sub, textvariable=kv,
                                values=KEY_OPTIONS, width=20, state="readonly",
                                font=("Yu Gothic UI",10))
            kcb.pack(side="left", padx=(4,6))

            av   = tk.StringVar()
            abtn = tk.Button(sub, text="📁 .exe",
                             font=("Yu Gothic UI",9), relief="flat",
                             bg="#EEEEE8", activebackground="#DDDDD8",
                             command=lambda p=pi, e=ei, d=dkey: self._browse_enc(p,e,d))
            abtn.pack(side="left", padx=4)

            al = tk.Label(sub, textvariable=av,
                          font=("Yu Gothic UI",9), fg="#2563EB",
                          bg="#FFFFFF", anchor="w")
            al.pack(side="left", padx=4)

            d_vars[dkey] = {"key": kv, "app": av}

        self._enc_vars[pi].append(d_vars)

    def _build_display_tab(self, parent):
        frame = tk.Frame(parent, bg="#FFFFFF", padx=24, pady=24)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="バックライト輝度",
                 font=("Yu Gothic UI",10), bg="#FFFFFF").pack(anchor="w")

        self._brightness_var = tk.IntVar(value=80)
        sf = tk.Frame(frame, bg="#FFFFFF")
        sf.pack(fill="x", pady=8)
        sl = tk.Scale(sf, from_=0, to=100, orient="horizontal",
                      variable=self._brightness_var,
                      font=("Yu Gothic UI",9), bg="#FFFFFF",
                      highlightthickness=0, length=300,
                      command=lambda v: self._brl.config(text=f"{int(float(v))}%"))
        sl.pack(side="left")
        self._brl = tk.Label(sf, text="80%", font=("Yu Gothic UI",10),
                             bg="#FFFFFF", fg="#2563EB", width=5)
        self._brl.pack(side="left", padx=8)

    # ---------- UI ↔ cfg 同期 ----------
    def _refresh_ui(self):
        for pi in range(len(PROFILES)):
            sws = self.cfg["switches"][pi]
            for si, sw in enumerate(sws):
                if si >= len(self._sw_vars[pi]):
                    break
                v = self._sw_vars[pi][si]
                k = sw.get("key","（なし）") or "（なし）"
                v["key"].set(k)
                v["app"].set(Path(sw.get("app","")).name if sw.get("app") else "")

            encs = self.cfg["encoders"][pi]
            for ei, enc in enumerate(encs):
                if ei >= len(self._enc_vars[pi]):
                    break
                dv = self._enc_vars[pi][ei]
                for dk in ("cw","ccw","push"):
                    k = enc.get(dk,"（なし）") or "（なし）"
                    dv[dk]["key"].set(k)
                    akey = f"app_{dk}"
                    dv[dk]["app"].set(
                        Path(enc.get(akey,"")).name if enc.get(akey) else "")

        self._brightness_var.set(self.cfg.get("display",{}).get("brightness",80))
        self._brl.config(text=f"{self._brightness_var.get()}%")

    def _sync_cfg(self):
        for pi in range(len(PROFILES)):
            for si in range(SW_COUNT):
                if si >= len(self._sw_vars[pi]):
                    break
                v = self._sw_vars[pi][si]
                k = v["key"].get()
                self.cfg["switches"][pi][si]["key"] = k

            for ei in range(ENC_COUNT):
                if ei >= len(self._enc_vars[pi]):
                    break
                dv = self._enc_vars[pi][ei]
                for dk in ("cw","ccw","push"):
                    self.cfg["encoders"][pi][ei][dk] = dv[dk]["key"].get()

        self.cfg["display"]["brightness"] = self._brightness_var.get()

    # ---------- ファイル選択 ----------
    def _browse_sw(self, pi, si):
        path = filedialog.askopenfilename(
            title="アプリを選択",
            filetypes=[("実行ファイル","*.exe"),("全ファイル","*.*")])
        if path:
            self.cfg["switches"][pi][si]["app"] = path
            self.cfg["switches"][pi][si]["key"] = "APP_LAUNCH"
            self._sw_vars[pi][si]["app"].set(Path(path).name)
            self._sw_vars[pi][si]["key"].set("APP_LAUNCH")

    def _browse_enc(self, pi, ei, dk):
        path = filedialog.askopenfilename(
            title="アプリを選択",
            filetypes=[("実行ファイル","*.exe"),("全ファイル","*.*")])
        if path:
            akey = f"app_{dk}"
            self.cfg["encoders"][pi][ei][akey] = path
            self.cfg["encoders"][pi][ei][dk]   = "APP_LAUNCH"
            self._enc_vars[pi][ei][dk]["app"].set(Path(path).name)
            self._enc_vars[pi][ei][dk]["key"].set("APP_LAUNCH")

    # ---------- Pico 操作 ----------
    def _check_pico(self):
        drive = find_pico_drive()
        if drive:
            self._conn_lbl.config(text=f"● Pico接続中 ({drive})", fg="#16A34A")
        else:
            self._conn_lbl.config(text="● Pico未接続", fg="#DC2626")
            messagebox.showwarning("未接続",
                "Pico が見つかりません。\n"
                "MicroPython を書き込み済みの Pico を USB で接続してください。")

    def _save(self):
        self._sync_cfg()
        self._save_json()
        messagebox.showinfo("保存完了", f"{CONFIG_JSON} に保存しました。")

    def _reset(self):
        if messagebox.askyesno("リセット", "全プロファイルをデフォルトに戻しますか？"):
            self.cfg = default_config()
            self._refresh_ui()

    def _write_to_pico(self):
        self._sync_cfg()
        self._save_json()
        drive = find_pico_drive()
        if not drive:
            messagebox.showerror("エラー",
                "Pico が見つかりません。USB 接続を確認してください。")
            return
        py_text = config_to_py(self.cfg)
        dst = drive / "config.py"
        try:
            with open(dst, "w", encoding="utf-8") as f:
                f.write(py_text)
            messagebox.showinfo("書き込み完了",
                f"config.py を {drive} に書き込みました。\n"
                "Pico を再起動すると設定が反映されます。")
        except Exception as e:
            messagebox.showerror("書き込みエラー", str(e))


if __name__ == "__main__":
    app = App()
    app.mainloop()
