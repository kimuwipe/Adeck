# configurator.py  v2  (CustomTkinter グリッドUI版)
# StreamDeck GUI 設定アプリ（Windows / Python 3.12）
# 依存: customtkinter（pip install customtkinter）
#
# 起動: python configurator.py
# UI: Elgato Stream Deck 風。スイッチ2×4／エンコーダ4個をボタングリッドで表示し、
#     クリックで選択→下パネルで設定、右パレットからアクションを割り当てる。

from __future__ import annotations   # 古いPythonでも型注釈を許可

import tkinter as tk
from tkinter import filedialog, messagebox
import json
from pathlib import Path

import customtkinter as ctk

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
    # 値入力アクション（右の入力欄に URL / コマンド / テキストを入力）
    "URL_OPEN","CMD_RUN","TEXT_INPUT",
    # プロファイル
    "PROFILE_NEXT",
]

# 入力欄（arg）に値を入れて使うアクション
ARG_ACTIONS = {"URL_OPEN", "CMD_RUN", "TEXT_INPUT"}

# キー種別 → config.py に書き出すプレフィックス
_ARG_PREFIX = {"URL_OPEN": "URL", "CMD_RUN": "CMD", "TEXT_INPUT": "TEXT"}

# プロファイル別アクセント色（Pico の PROFILE_COLORS と対応）
PROFILE_ACCENTS = ["#22d3ee", "#22c55e", "#eab308", "#f97316"]

# 右パレット用のカテゴリ分け（Elgato のアクション一覧風）
KEY_CATEGORIES = [
    ("特殊アクション", ["APP_LAUNCH", "URL_OPEN", "CMD_RUN", "TEXT_INPUT"]),
    ("プロファイル", ["PROFILE_NEXT"]),
    ("メディア・音量", ["VOLUME_UP", "VOLUME_DOWN", "MUTE",
                        "MEDIA_PLAY", "MEDIA_NEXT", "MEDIA_PREV"]),
    ("汎用操作", ["UNDO", "REDO", "SAVE", "ZOOM_IN", "ZOOM_OUT", "ZOOM_FIT",
                  "TAB_NEXT", "TAB_PREV", "NEW_TAB"]),
    ("Windows", ["WIN_SNIP", "VDESK_NEXT", "VDESK_PREV",
                 "WIN_MAX", "TASK_MGR", "WIN_LOCK"]),
    ("SolidWorks", ["SW_SHORTCUT_BAR", "SW_REBUILD", "SW_REBUILD_FULL",
                    "SW_NORMAL_TO", "SW_FILTER_CLEAR", "SW_DISPLAY_CYCLE",
                    "SW_MAGNIFIER", "SW_ISO", "SW_VIEW_NEXT", "SW_VIEW_PREV"]),
    ("開発", ["SHIFT_F5", "DEV_TERMINAL", "DEV_COMMENT", "DEV_GOTO_DEF",
              "FONT_UP", "FONT_DOWN"]),
    ("エージェント", ["MIC_UP", "MIC_DOWN", "MIC_MUTE", "APP_CALC"]),
    ("ファンクション", ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10",
                        "F11", "F12", "F13", "F14", "F15", "F16", "F17", "F18",
                        "F19", "F20"]),
    ("無効", ["（なし）"]),
]


def action_value(key, app: str = "", arg: str = ""):
    """キー種別・アプリパス・入力値から、Picoに渡す実際のアクション文字列
    （またはNone）を返す。ライブ反映（シリアル送信）でも使う。"""
    if key == "APP_LAUNCH" and app:
        return f"APP:{app}"
    if key in _ARG_PREFIX and arg:
        return f"{_ARG_PREFIX[key]}:{arg}"
    if key in ("（なし）", None, ""):
        return None
    return key


def short_label(key, app: str = "", arg: str = "") -> str:
    """グリッドボタンに表示する短いアクション名を返す。"""
    v = action_value(key, app, arg)
    if v is None:
        return "—"
    if v.startswith("APP:"):
        return "APP:" + Path(v[4:]).name[:12]
    if v.startswith("URL:"):
        return "URL:" + v[4:][:12]
    if v.startswith("CMD:"):
        return "CMD:" + v[4:][:12]
    if v.startswith("TEXT:"):
        return "TXT:" + v[5:][:12]
    return v[:16]


def action_literal(key: str, app: str, arg: str) -> str:
    """action_value を config.py に埋め込む Python 文字列リテラル
    （またはNone）へ変換する。json.dumps で安全にエスケープするため、
    テキストに引用符・改行が含まれていても壊れない。"""
    v = action_value(key, app, arg)
    return "None" if v is None else json.dumps(v, ensure_ascii=False)


def expand_maps(cfg: dict):
    """cfg から Pico ランタイム形式の (profiles, switch_map, encoder_map) を
    生成する。config_to_py と同じ展開ロジック（ENC1〜3共通・ENC4別）。
    ライブ反映のシリアル送信用に JSON 可能な素のリストを返す。"""
    profiles = cfg.get("profiles", PROFILES)
    n = len(profiles)
    switch_map = [
        [action_value(sw.get("key", "（なし）"), sw.get("app", ""), sw.get("arg", ""))
         for sw in cfg["switches"][p]]
        for p in range(n)
    ]

    def _triple(enc: dict):
        return [
            action_value(enc.get("cw"),   enc.get("app_cw", ""),   enc.get("arg_cw", "")),
            action_value(enc.get("ccw"),  enc.get("app_ccw", ""),  enc.get("arg_ccw", "")),
            action_value(enc.get("push"), enc.get("app_push", ""), enc.get("arg_push", "")),
        ]

    common = [_triple(cfg["encoders"][0][i]) for i in range(3)]
    encoder_map = [common + [_triple(cfg["encoders"][p][3])] for p in range(n)]
    return profiles, switch_map, encoder_map


# ===== 前面アプリ → プロファイル 自動切替 デフォルトルール =====
# キー: プロセス実行ファイル名（小文字）  値: プロファイル名（PROFILESと一致）
DEFAULT_AUTO_RULES = {
    "sldworks.exe":        "SolidWorks",
    "code.exe":            "開発",
    "devenv.exe":          "開発",
    "pycharm64.exe":       "開発",
    "idea64.exe":          "開発",
    "windowsterminal.exe": "開発",
    "obs64.exe":           "音声",
    "discord.exe":         "音声",
    "zoom.exe":            "音声",
    "ms-teams.exe":        "音声",
}


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
            [{"key": k, "app": "", "arg": ""} for k in sw_maps[p]]
            for p in range(len(PROFILES))
        ],
        "encoders": [
            [{"cw": cw, "ccw": ccw, "push": push,
              "app_cw": "", "app_ccw": "", "app_push": "",
              "arg_cw": "", "arg_ccw": "", "arg_push": ""}
             for cw, ccw, push in enc_maps[p]]
            for p in range(len(PROFILES))
        ],
        "display": {"brightness": 80},
        "auto_profile": {"enabled": False, "rules": dict(DEFAULT_AUTO_RULES)},
    }


# ===== JSON → config.py 変換 =====
def config_to_py(cfg: dict) -> str:
    lines = [
        "# config.py  (configurator.py により自動生成)",
        "# 手動編集は configurator.py で上書きされます",
        "#",
        "# アクション記法:",
        "#   \"KEY_NAME\"   → キー送信（PC側 agent.py）",
        "#   \"APP:path\"   → アプリ起動",
        "#   \"URL:...\"    → 既定ブラウザでURLを開く",
        "#   \"CMD:...\"    → シェルコマンド実行",
        "#   \"TEXT:...\"   → テキスト入力（\\n=改行）",
        "",
        f'PROFILES = {json.dumps(cfg["profiles"], ensure_ascii=False)}',
        "",
        "SWITCH_MAP = [",
    ]
    for p_sws in cfg["switches"]:
        lines.append("    [")
        for sw in p_sws:
            val = action_literal(sw.get("key", "（なし）"),
                                 sw.get("app", ""), sw.get("arg", ""))
            lines.append(f"        {val},")
        lines.append("    ],")
    lines.append("]")
    lines.append("")

    def _enc_tuple(enc: dict) -> str:
        cw   = action_literal(enc.get("cw"),   enc.get("app_cw", ""),   enc.get("arg_cw", ""))
        ccw  = action_literal(enc.get("ccw"),  enc.get("app_ccw", ""),  enc.get("arg_ccw", ""))
        push = action_literal(enc.get("push"), enc.get("app_push", ""), enc.get("arg_push", ""))
        return f"({cw}, {ccw}, {push})"

    lines.append("_ENC_COMMON = [")
    # ENC1〜3 は全プロファイル同じ（プロファイル0から取得）
    for i in range(3):
        lines.append(f"    {_enc_tuple(cfg['encoders'][0][i])},")
    lines.append("]")
    lines.append("")
    lines.append("_ENC4_BY_PROFILE = [")
    for p in range(len(PROFILES)):
        lines.append(f"    {_enc_tuple(cfg['encoders'][p][3])},  # {PROFILES[p]}")
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


# ============================================================
#  GUI アプリ（CustomTkinter・グリッド型）
# ============================================================
CARD_BG   = "#2b2b2b"
CARD_SEL  = "#3a3a3a"
PANEL_BG  = "#242424"


class App(ctk.CTk):
    def __init__(self, on_live_apply=None):
        super().__init__()
        ctk.set_appearance_mode("dark")
        try:
            ctk.set_default_color_theme("dark-blue")
        except Exception:
            pass

        self.title(APP_TITLE)
        self.geometry("1080x780")
        self.minsize(960, 700)

        # 常駐エージェント経由でPicoへ即時反映するコールバック（統合UIから渡される）
        self._on_live_apply = on_live_apply
        self.cfg    = default_config()
        self._pi    = 0                 # 表示中プロファイル index
        self._sel   = ("sw", 0)         # 選択中の要素
        self._active_slot = None        # 右パレットの割り当て先スロット
        self._sw_buttons = []
        self._enc_cards  = []

        self._load_json()
        self._normalize_cfg()
        self._build_ui()
        self._select(("sw", 0))

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

    def _normalize_cfg(self):
        """古い設定ファイルに欠けているフィールドを補完する。"""
        self.cfg.setdefault("profiles", list(PROFILES))
        self.cfg.setdefault("display", {"brightness": 80})
        self.cfg.setdefault("auto_profile",
                            {"enabled": False, "rules": dict(DEFAULT_AUTO_RULES)})
        n = len(self.cfg["profiles"])
        for p in range(n):
            for sw in self.cfg["switches"][p]:
                sw.setdefault("app", "")
                sw.setdefault("arg", "")
            for enc in self.cfg["encoders"][p]:
                for dk in ("cw", "ccw", "push"):
                    enc.setdefault(f"app_{dk}", "")
                    enc.setdefault(f"arg_{dk}", "")

    # ---------- スロット（cfg 内の1アクション）参照 ----------
    def _slot_fields(self, slot):
        """slot -> (dict, key_field, app_field, arg_field)"""
        if slot[0] == "sw":
            _, pi, si = slot
            d = self.cfg["switches"][pi][si]
            return d, "key", "app", "arg"
        _, pi, ei, dk = slot
        d = self.cfg["encoders"][pi][ei]
        return d, dk, f"app_{dk}", f"arg_{dk}"

    def _mirror_enc_common(self, slot, field, value):
        """ENC1〜3 は全プロファイル共通（config_to_py は profile0 を使う）なので、
        編集を全プロファイルへ反映して混乱を防ぐ。"""
        if slot[0] == "enc" and slot[2] < 3:
            ei = slot[2]
            for p in range(len(self.cfg["profiles"])):
                self.cfg["encoders"][p][ei][field] = value

    # ---------- UI 構築 ----------
    def _build_ui(self):
        # ---- トップバー ----
        top = ctk.CTkFrame(self, height=60, corner_radius=0)
        top.pack(fill="x")
        ctk.CTkLabel(top, text="🎛  StreamDeck 設定",
                     font=ctk.CTkFont(size=18, weight="bold")
                     ).pack(side="left", padx=18, pady=12)
        self._prof_seg = ctk.CTkSegmentedButton(
            top, values=self.cfg["profiles"], command=self._on_profile_change)
        self._prof_seg.set(self.cfg["profiles"][self._pi])
        self._prof_seg.pack(side="left", padx=10)

        self._conn_lbl = ctk.CTkLabel(top, text="● Pico未接続", text_color="#888")
        self._conn_lbl.pack(side="right", padx=14)
        ctk.CTkButton(top, text="接続確認", width=80,
                      command=self._check_pico).pack(side="right", padx=4)

        # ---- 本体：左=エディタ / 右=パレット ----
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=8)

        right = ctk.CTkFrame(body, width=260)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        self._build_palette(right)

        left = ctk.CTkFrame(body, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # スイッチグリッド 2×4
        ctk.CTkLabel(left, text="スイッチ",
                     font=ctk.CTkFont(size=13, weight="bold")
                     ).pack(anchor="w", padx=6, pady=(6, 4))
        swgrid = ctk.CTkFrame(left, fg_color="transparent")
        swgrid.pack()
        for si in range(SW_COUNT):
            r, c = si // 4, si % 4
            btn = ctk.CTkButton(swgrid, text="", width=118, height=66,
                                corner_radius=12, fg_color=CARD_BG,
                                hover_color=CARD_SEL,
                                font=ctk.CTkFont(size=12),
                                command=lambda s=si: self._select(("sw", s)))
            btn.grid(row=r, column=c, padx=6, pady=6)
            self._sw_buttons.append(btn)

        # エンコーダカード 1×4
        ctk.CTkLabel(left, text="エンコーダ",
                     font=ctk.CTkFont(size=13, weight="bold")
                     ).pack(anchor="w", padx=6, pady=(12, 4))
        encgrid = ctk.CTkFrame(left, fg_color="transparent")
        encgrid.pack()
        for ei in range(ENC_COUNT):
            card = ctk.CTkButton(encgrid, text="", width=118, height=80,
                                 corner_radius=12, fg_color=CARD_BG,
                                 hover_color=CARD_SEL,
                                 font=ctk.CTkFont(size=11),
                                 command=lambda e=ei: self._select(("enc", e)))
            card.grid(row=0, column=ei, padx=6, pady=6)
            self._enc_cards.append(card)

        # 選択要素の設定パネル
        self._detail = ctk.CTkFrame(left)
        self._detail.pack(fill="both", expand=True, pady=(12, 0))

        # ---- フッター ----
        footer = ctk.CTkFrame(self, height=54, corner_radius=0)
        footer.pack(fill="x")

        bf = ctk.CTkFrame(footer, fg_color="transparent")
        bf.pack(side="left", padx=14, pady=8)
        ctk.CTkButton(bf, text="リセット", width=80, fg_color="#555",
                      hover_color="#666", command=self._reset).pack(side="left")
        ctk.CTkLabel(bf, text="  LCD輝度").pack(side="left", padx=(12, 4))
        self._bright = ctk.CTkSlider(bf, from_=0, to=100, number_of_steps=100,
                                     width=130, command=self._on_bright)
        cur_br = int(self.cfg.get("display", {}).get("brightness", 80))
        self._bright.set(cur_br)
        self._bright.pack(side="left")
        self._bright_lbl = ctk.CTkLabel(bf, text=f"{cur_br}%", width=44)
        self._bright_lbl.pack(side="left", padx=6)

        ctk.CTkButton(footer, text="Picoに書き込む",
                      command=self._write_to_pico).pack(side="right", padx=12, pady=8)
        if self._on_live_apply:
            ctk.CTkButton(footer, text="ライブ反映", fg_color="#16a34a",
                          hover_color="#15803d",
                          command=self._live_apply).pack(side="right", padx=4)
        ctk.CTkButton(footer, text="設定を保存", fg_color="#555", hover_color="#666",
                      command=self._save).pack(side="right", padx=4)

        self._refresh_grid()

    def _build_palette(self, parent):
        ctk.CTkLabel(parent, text="アクション一覧",
                     font=ctk.CTkFont(size=13, weight="bold")
                     ).pack(anchor="w", padx=12, pady=(10, 0))
        ctk.CTkLabel(parent, text="クリックで選択中の要素へ割り当て",
                     font=ctk.CTkFont(size=10), text_color="#888"
                     ).pack(anchor="w", padx=12, pady=(0, 4))
        sf = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        sf.pack(fill="both", expand=True, padx=4, pady=4)
        for cat, keys in KEY_CATEGORIES:
            ctk.CTkLabel(sf, text=cat, font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#8ab4d8").pack(anchor="w", padx=6, pady=(8, 2))
            for k in keys:
                ctk.CTkButton(sf, text=k, height=26, anchor="w",
                              fg_color="#333333", hover_color="#2f5d3a",
                              font=ctk.CTkFont(size=11),
                              command=lambda kk=k: self._assign_to_active(kk)
                              ).pack(fill="x", padx=6, pady=1)

    # ---------- 選択・詳細パネル ----------
    def _select(self, sel):
        self._sel = sel
        if sel[0] == "sw":
            self._active_slot = ("sw", self._pi, sel[1])
        else:
            self._active_slot = ("enc", self._pi, sel[1], "push")
        self._refresh_grid()
        self._build_detail()

    def _build_detail(self):
        for w in self._detail.winfo_children():
            w.destroy()

        accent = PROFILE_ACCENTS[self._pi % len(PROFILE_ACCENTS)]
        if self._sel[0] == "sw":
            si = self._sel[1]
            ctk.CTkLabel(self._detail, text=f"SW{si+1} の設定",
                         font=ctk.CTkFont(size=15, weight="bold"),
                         text_color=accent).pack(anchor="w", padx=14, pady=(12, 6))
            self._make_action_editor(self._detail, ("sw", self._pi, si), "アクション")
        else:
            ei = self._sel[1]
            note = "（ENC1〜3は全プロファイル共通）" if ei < 3 else ""
            ctk.CTkLabel(self._detail, text=f"ENC{ei+1} の設定 {note}",
                         font=ctk.CTkFont(size=15, weight="bold"),
                         text_color=accent).pack(anchor="w", padx=14, pady=(12, 6))
            for dk, dlabel in [("cw", "CW 右回し"),
                               ("ccw", "CCW 左回し"),
                               ("push", "Push 押込み")]:
                self._make_action_editor(
                    self._detail, ("enc", self._pi, ei, dk), dlabel)

    def _make_action_editor(self, parent, slot, title):
        d, kf, af, argf = self._slot_fields(slot)
        row = ctk.CTkFrame(parent, fg_color=PANEL_BG, corner_radius=8)
        row.pack(fill="x", padx=14, pady=4)

        ctk.CTkLabel(row, text=title, width=96, anchor="w"
                     ).pack(side="left", padx=(10, 6), pady=8)

        key_var = tk.StringVar(value=d.get(kf) or "（なし）")
        ctk.CTkOptionMenu(row, values=KEY_OPTIONS, variable=key_var, width=170,
                          command=lambda v, s=slot: self._on_key_change(s, v)
                          ).pack(side="left", padx=4)

        ctk.CTkButton(row, text="📁", width=38,
                      command=lambda s=slot: self._browse(s)).pack(side="left", padx=4)

        arg_var = tk.StringVar(value=d.get(argf, ""))
        ent = ctk.CTkEntry(row, textvariable=arg_var,
                           placeholder_text="URL / コマンド / テキスト")
        ent.pack(side="left", padx=6, fill="x", expand=True)
        ent.bind("<KeyRelease>",
                 lambda e, s=slot, v=arg_var: self._on_arg_change(s, v.get()))

        appname = Path(d.get(af, "")).name if d.get(af) else ""
        if appname:
            ctk.CTkLabel(row, text=appname, text_color="#7aa2f7", width=90,
                         anchor="w").pack(side="left", padx=4)

    # ---------- 変更ハンドラ ----------
    def _on_key_change(self, slot, value):
        d, kf, af, argf = self._slot_fields(slot)
        d[kf] = value
        self._mirror_enc_common(slot, kf, value)
        self._active_slot = slot
        self._refresh_grid()

    def _on_arg_change(self, slot, text):
        d, kf, af, argf = self._slot_fields(slot)
        d[argf] = text
        self._mirror_enc_common(slot, argf, text)
        self._active_slot = slot
        self._refresh_grid()

    def _browse(self, slot):
        path = filedialog.askopenfilename(
            title="アプリを選択",
            filetypes=[("実行ファイル", "*.exe"), ("全ファイル", "*.*")])
        if not path:
            return
        d, kf, af, argf = self._slot_fields(slot)
        d[af] = path
        d[kf] = "APP_LAUNCH"
        self._mirror_enc_common(slot, af, path)
        self._mirror_enc_common(slot, kf, "APP_LAUNCH")
        self._active_slot = slot
        self._build_detail()
        self._refresh_grid()

    def _assign_to_active(self, key):
        if not self._active_slot:
            return
        d, kf, af, argf = self._slot_fields(self._active_slot)
        d[kf] = key
        self._mirror_enc_common(self._active_slot, kf, key)
        self._build_detail()
        self._refresh_grid()

    def _on_bright(self, v):
        b = int(float(v))
        self.cfg.setdefault("display", {})["brightness"] = b
        self._bright_lbl.configure(text=f"{b}%")

    # ---------- グリッド表示更新 ----------
    def _refresh_grid(self):
        accent = PROFILE_ACCENTS[self._pi % len(PROFILE_ACCENTS)]
        sws = self.cfg["switches"][self._pi]
        for si, btn in enumerate(self._sw_buttons):
            sw = sws[si]
            lbl = short_label(sw.get("key"), sw.get("app", ""), sw.get("arg", ""))
            selected = (self._sel == ("sw", si))
            btn.configure(text=f"SW{si+1}\n{lbl}",
                          fg_color=(CARD_SEL if selected else CARD_BG),
                          border_width=(2 if selected else 0),
                          border_color=accent)
        encs = self.cfg["encoders"][self._pi]
        for ei, card in enumerate(self._enc_cards):
            enc = encs[ei]
            cw = short_label(enc.get("cw"), enc.get("app_cw", ""), enc.get("arg_cw", ""))
            pu = short_label(enc.get("push"), enc.get("app_push", ""), enc.get("arg_push", ""))
            selected = (self._sel == ("enc", ei))
            card.configure(text=f"ENC{ei+1}\n↻ {cw}\nP {pu}",
                           fg_color=(CARD_SEL if selected else CARD_BG),
                           border_width=(2 if selected else 0),
                           border_color=accent)

    # ---------- プロファイル切替 ----------
    def _on_profile_change(self, name):
        try:
            self._pi = self.cfg["profiles"].index(name)
        except ValueError:
            self._pi = 0
        self._select(("sw", 0))

    # ---------- Pico 操作 ----------
    def _check_pico(self):
        drive = find_pico_drive()
        if drive:
            self._conn_lbl.configure(text=f"● Pico接続中 ({drive})",
                                     text_color="#22c55e")
        else:
            self._conn_lbl.configure(text="● Pico未接続", text_color="#ef4444")
            messagebox.showwarning(
                "未接続",
                "Pico が見つかりません。\n"
                "MicroPython を書き込み済みの Pico を USB で接続してください。")

    def _save(self):
        self._save_json()
        messagebox.showinfo("保存完了", f"{CONFIG_JSON} に保存しました。")

    def _reset(self):
        if messagebox.askyesno("リセット", "全プロファイルをデフォルトに戻しますか？"):
            self.cfg = default_config()
            self._pi = 0
            self._prof_seg.set(self.cfg["profiles"][0])
            self._bright.set(self.cfg["display"]["brightness"])
            self._bright_lbl.configure(text=f"{self.cfg['display']['brightness']}%")
            self._select(("sw", 0))

    def _live_apply(self):
        """常駐エージェント経由でPicoへ即時反映（config.py書き込み・再起動不要）"""
        if not self._on_live_apply:
            return
        self._save_json()
        try:
            ok = self._on_live_apply(self.cfg)
        except Exception as e:
            messagebox.showerror("ライブ反映", f"反映に失敗しました:\n{e}")
            return
        if ok:
            messagebox.showinfo("ライブ反映",
                "Picoへ即時反映しました（config.py書き込み・再起動は不要）。")
        else:
            messagebox.showwarning("ライブ反映",
                "Picoへ反映できませんでした。\n"
                "統合アプリでPicoに接続されているか確認してください。")

    def _write_to_pico(self):
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
