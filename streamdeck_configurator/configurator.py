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
    # 記録したキーコンビネーション（⌨記録ボタンで設定）
    "HOTKEY",
    # プロファイル
    "PROFILE_NEXT",
]

# 入力欄（arg）に値を入れて使うアクション
ARG_ACTIONS = {"URL_OPEN", "CMD_RUN", "TEXT_INPUT"}

# キー種別 → config.py に書き出すプレフィックス
_ARG_PREFIX = {"URL_OPEN": "URL", "CMD_RUN": "CMD", "TEXT_INPUT": "TEXT"}

# プリセット最大数
MAX_PRESETS = 32

# プロファイル最大数（タップ/SW1での順送りが実用的な範囲。必要なら増やせる）
MAX_PROFILES = 8

# ファイル選択で許可する拡張子（アプリ / ショートカット）
APP_FILETYPES = [
    ("プログラム/ショートカット", "*.exe;*.lnk;*.url;*.bat;*.cmd"),
    ("ショートカット", "*.lnk;*.url"),
    ("実行ファイル", "*.exe"),
    ("全ファイル", "*.*"),
]

# ===== キー記録（tkinter keysym → pyautogui キー名）=====
_KEYSYM_MAP = {
    "Return": "enter", "Escape": "esc", "Tab": "tab", "BackSpace": "backspace",
    "Delete": "delete", "space": "space", "Up": "up", "Down": "down",
    "Left": "left", "Right": "right", "Home": "home", "End": "end",
    "Prior": "pageup", "Next": "pagedown", "Insert": "insert",
    "comma": ",", "period": ".", "slash": "/", "backslash": "\\",
    "minus": "-", "plus": "+", "equal": "=", "semicolon": ";", "colon": ":",
    "apostrophe": "'", "quotedbl": '"', "bracketleft": "[", "bracketright": "]",
    "grave": "`", "asterisk": "*", "numbersign": "#", "exclam": "!", "at": "@",
    "dollar": "$", "percent": "%", "ampersand": "&", "parenleft": "(",
    "parenright": ")", "underscore": "_", "question": "?",
}
_MODIFIER_KEYSYMS = {
    "Control_L", "Control_R", "Shift_L", "Shift_R", "Alt_L", "Alt_R",
    "Meta_L", "Meta_R", "Super_L", "Super_R", "Win_L", "Win_R",
}


def _keysym_to_key(ks: str):
    """tkinter の keysym を pyautogui のキー名に変換（不明なら None）。"""
    if ks in _KEYSYM_MAP:
        return _KEYSYM_MAP[ks]
    if len(ks) == 1:
        return ks.lower()
    if len(ks) >= 2 and ks[0] == "F" and ks[1:].isdigit():
        return ks.lower()            # F1〜F24
    if ks.startswith("KP_") and ks[3:].isdigit():
        return ks[3:]                # テンキー数字
    return None


def combo_from_event(ev):
    """キーイベントから "ctrl shift c" 形式（空白区切り）のコンビネーションを返す。
    修飾キー単体や不明キーは None。"""
    if ev.keysym in _MODIFIER_KEYSYMS:
        return None
    key = _keysym_to_key(ev.keysym)
    if not key:
        return None
    mods = []
    st = ev.state
    if st & 0x0004:   mods.append("ctrl")
    if st & 0x20000:  mods.append("alt")     # Windows: Alt = Mod1(0x20000)
    if st & 0x0001:   mods.append("shift")
    return " ".join(mods + [key])

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
    if key == "HOTKEY" and arg:
        return f"KEY:{arg}"
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
    if v.startswith("KEY:"):
        return "⌨ " + v[4:].replace(" ", "+")[:14]
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


# ===== AI（Copilot / Claude Code）用プロファイル =====
# キー割り当ては VS Code 標準ショートカット前提。環境に合わせてエディタで調整可。
def _ai_switches():
    return [
        {"key": "PROFILE_NEXT", "app": "", "arg": ""},        # SW1: プロファイル切替
        {"key": "HOTKEY", "app": "", "arg": "ctrl i"},        # SW2: インラインチャット
        {"key": "HOTKEY", "app": "", "arg": "ctrl alt i"},    # SW3: Copilotチャット
        {"key": "HOTKEY", "app": "", "arg": "ctrl shift p"},  # SW4: コマンドパレット
        {"key": "HOTKEY", "app": "", "arg": "ctrl `"},        # SW5: ターミナル開閉
        {"key": "HOTKEY", "app": "", "arg": "ctrl shift `"},  # SW6: 新規ターミナル
        {"key": "CMD_RUN", "app": "", "arg": "wt claude"},    # SW7: Claude Code起動
        {"key": "HOTKEY", "app": "", "arg": "esc"},           # SW8: 却下/中断
    ]


def _ai_encoders():
    # ENC1〜3は全プロファイル共通（config_to_pyがprofile0を使う）なので合わせる。
    common = [("VOLUME_UP", "VOLUME_DOWN", "MUTE"),
              ("UNDO", "REDO", "SAVE"),
              ("ZOOM_IN", "ZOOM_OUT", "ZOOM_FIT")]
    encs = [{"cw": cw, "ccw": ccw, "push": push,
             "app_cw": "", "app_ccw": "", "app_push": "",
             "arg_cw": "", "arg_ccw": "", "arg_push": ""}
            for cw, ccw, push in common]
    # ENC4: 回す=Copilot候補 次/前(Alt+]/Alt+[), 押す=確定(Tab)
    encs.append({"cw": "HOTKEY", "ccw": "HOTKEY", "push": "HOTKEY",
                 "app_cw": "", "app_ccw": "", "app_push": "",
                 "arg_cw": "alt ]", "arg_ccw": "alt [", "arg_push": "tab"})
    return encs


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
    switches = [
        [{"key": k, "app": "", "arg": ""} for k in sw_maps[p]]
        for p in range(len(PROFILES))
    ]
    encoders = [
        [{"cw": cw, "ccw": ccw, "push": push,
          "app_cw": "", "app_ccw": "", "app_push": "",
          "arg_cw": "", "arg_ccw": "", "arg_push": ""}
         for cw, ccw, push in enc_maps[p]]
        for p in range(len(PROFILES))
    ]
    # AI（Copilot / Claude Code）プロファイルを標準で追加
    switches.append(_ai_switches())
    encoders.append(_ai_encoders())
    return {
        "profiles": list(PROFILES) + ["AI"],
        "switches": switches,
        "encoders": encoders,
        "display": {"brightness": 80},
        "auto_profile": {"enabled": False, "rules": dict(DEFAULT_AUTO_RULES)},
        "presets": [],
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
        "#   \"KEY:...\"    → キーコンビ送信（例 KEY:ctrl c）",
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
    for p in range(len(cfg["profiles"])):
        lines.append(f"    {_enc_tuple(cfg['encoders'][p][3])},  # {cfg['profiles'][p]}")
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


# ===== 設定ファイル ロード/正規化 =====
def normalize_config(cfg: dict) -> dict:
    """古い/欠損した設定ファイルに不足フィールドを補完する。"""
    cfg.setdefault("profiles", list(PROFILES))
    cfg.setdefault("display", {"brightness": 80})
    cfg.setdefault("auto_profile",
                   {"enabled": False, "rules": dict(DEFAULT_AUTO_RULES)})
    cfg.setdefault("presets", [])
    for p in range(len(cfg["profiles"])):
        for sw in cfg["switches"][p]:
            sw.setdefault("app", "")
            sw.setdefault("arg", "")
        for enc in cfg["encoders"][p]:
            for dk in ("cw", "ccw", "push"):
                enc.setdefault(f"app_{dk}", "")
                enc.setdefault(f"arg_{dk}", "")
    return cfg


def load_config() -> dict:
    """streamdeck_config.json を読み込み（無ければデフォルト）、正規化して返す。"""
    cfg = default_config()
    if CONFIG_JSON.exists():
        try:
            with open(CONFIG_JSON, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            pass
    return normalize_config(cfg)


def save_config(cfg: dict):
    with open(CONFIG_JSON, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ============================================================
#  GUI アプリ（CustomTkinter・グリッド型）
# ============================================================
CARD_BG   = "#2b2b2b"
CARD_SEL  = "#3a3a3a"
PANEL_BG  = "#242424"


class EditorFrame(ctk.CTkFrame):
    """グリッド型 設定エディタ（単体ウィンドウにも統合UIのタブにも埋め込める）。
    cfg は呼び出し側が load_config() で用意した dict を共有参照する。"""

    def __init__(self, master, cfg, on_live_apply=None):
        super().__init__(master, fg_color="transparent")

        # 常駐エージェント経由でPicoへ即時反映するコールバック（統合UIから渡される）
        self._on_live_apply = on_live_apply
        self.cfg    = cfg
        self._pi    = 0                 # 表示中プロファイル index
        self._sel   = ("sw", 0)         # 選択中の要素
        self._active_slot = None        # 右パレットの割り当て先スロット
        self._sw_buttons = []
        self._enc_cards  = []

        self._build_ui()
        self._select(("sw", 0))

    # ---------- JSON ----------
    def _save_json(self):
        save_config(self.cfg)

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
        ctk.CTkLabel(top, text="プロファイル:").pack(side="left", padx=(6, 2))
        self._prof_menu = ctk.CTkOptionMenu(
            top, values=self.cfg["profiles"], width=150,
            command=self._on_profile_change)
        self._prof_menu.set(self.cfg["profiles"][self._pi])
        self._prof_menu.pack(side="left", padx=2)
        ctk.CTkButton(top, text="プロファイル管理", width=118, fg_color="#555",
                      hover_color="#666",
                      command=self._manage_profiles).pack(side="left", padx=6)

        self._conn_lbl = ctk.CTkLabel(top, text="● ドライブ未検出", text_color="#888")
        self._conn_lbl.pack(side="right", padx=14)
        ctk.CTkButton(top, text="ドライブ確認", width=90,
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

        # プリセット（動的・上部）
        self._preset_frame = ctk.CTkFrame(sf, fg_color="transparent")
        self._preset_frame.pack(fill="x")
        self._refresh_presets()

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
        header = ctk.CTkFrame(self._detail, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(12, 4))
        if self._sel[0] == "sw":
            si = self._sel[1]
            ctk.CTkLabel(header, text=f"SW{si+1} の設定",
                         font=ctk.CTkFont(size=15, weight="bold"),
                         text_color=accent).pack(side="left")
        else:
            ei = self._sel[1]
            note = "（ENC1〜3は全プロファイル共通）" if ei < 3 else ""
            ctk.CTkLabel(header, text=f"ENC{ei+1} の設定 {note}",
                         font=ctk.CTkFont(size=15, weight="bold"),
                         text_color=accent).pack(side="left")

        # プリセット保存/管理（選択中アクティブスロットの内容を保存）
        ctk.CTkButton(header, text="プリセット管理", width=100, fg_color="#555",
                      hover_color="#666",
                      command=self._manage_presets).pack(side="right", padx=2)
        ctk.CTkButton(header, text="＋ プリセット保存", width=120,
                      fg_color="#7c3aed", hover_color="#6d28d9",
                      command=self._save_preset).pack(side="right", padx=2)

        if self._sel[0] == "sw":
            self._make_action_editor(self._detail, ("sw", self._pi, self._sel[1]),
                                     "アクション")
        else:
            ei = self._sel[1]
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
        ctk.CTkButton(row, text="⌨ 記録", width=64, fg_color="#4a3a5a",
                      hover_color="#5a4a6a",
                      command=lambda s=slot: self._record(s)).pack(side="left", padx=2)

        arg_var = tk.StringVar(value=d.get(argf, ""))
        ent = ctk.CTkEntry(row, textvariable=arg_var,
                           placeholder_text="URL / コマンド / テキスト / キー(ctrl c)")
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
            title="アプリ / ショートカットを選択",
            filetypes=APP_FILETYPES)
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

    # ---------- キー記録（ホットキー） ----------
    def _record(self, slot):
        self._active_slot = slot
        self._open_recorder(lambda combo: self._apply_hotkey(slot, combo))

    def _apply_hotkey(self, slot, combo):
        if not combo:
            return
        d, kf, af, argf = self._slot_fields(slot)
        d[kf] = "HOTKEY"
        d[argf] = combo
        self._mirror_enc_common(slot, kf, "HOTKEY")
        self._mirror_enc_common(slot, argf, combo)
        self._active_slot = slot
        self._build_detail()
        self._refresh_grid()

    def _open_recorder(self, callback):
        """小窓を開き、押されたキーコンビネーションを記録して callback へ渡す。"""
        win = ctk.CTkToplevel(self)
        win.title("キー記録")
        win.geometry("360x160")
        win.transient(self)
        ctk.CTkLabel(win, text="登録したいキーを押してください",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(22, 4))
        ctk.CTkLabel(win, text="修飾キー＋キー（例: Ctrl+C）／ Esc で中止",
                     font=ctk.CTkFont(size=11), text_color="#888").pack()
        preview = ctk.CTkLabel(win, text="―", font=ctk.CTkFont(size=18, weight="bold"),
                               text_color="#22c55e")
        preview.pack(pady=12)

        def _done(combo):
            try:
                win.grab_release()
            except Exception:
                pass
            win.destroy()
            callback(combo)

        def on_key(ev):
            if ev.keysym == "Escape":
                _done(None)
                return
            combo = combo_from_event(ev)
            if combo:
                preview.configure(text=combo.replace(" ", "+"))
                win.after(220, lambda: _done(combo))

        win.bind("<KeyPress>", on_key)
        win.after(60, lambda: (win.grab_set(), win.focus_force()))

    # ---------- 入力ダイアログ（CustomTkinter・大きめ） ----------
    def _ask_string(self, title, prompt, initial=""):
        """テーマ付きの大きめ文字列入力モーダル。OK=文字列 / キャンセル=None。"""
        win = ctk.CTkToplevel(self)
        win.title(title)
        win.geometry("480x240")
        win.resizable(False, False)
        win.transient(self)
        result = {"value": None}

        ctk.CTkLabel(win, text=prompt, font=ctk.CTkFont(size=15),
                     wraplength=430, justify="left").pack(padx=24, pady=(26, 12))
        var = tk.StringVar(value=initial)
        ent = ctk.CTkEntry(win, textvariable=var, width=420, height=44,
                           font=ctk.CTkFont(size=17))
        ent.pack(padx=24)

        btns = ctk.CTkFrame(win, fg_color="transparent")
        btns.pack(pady=22)

        def _ok():
            result["value"] = var.get()
            win.destroy()

        def _cancel():
            result["value"] = None
            win.destroy()

        ctk.CTkButton(btns, text="キャンセル", width=130, height=42,
                      fg_color="#555", hover_color="#666",
                      font=ctk.CTkFont(size=15), command=_cancel).pack(side="left", padx=10)
        ctk.CTkButton(btns, text="OK", width=130, height=42,
                      font=ctk.CTkFont(size=15, weight="bold"),
                      command=_ok).pack(side="left", padx=10)

        ent.bind("<Return>", lambda e: _ok())
        win.bind("<Escape>", lambda e: _cancel())
        ent.select_range(0, "end")
        win.after(60, lambda: (win.grab_set(), ent.focus_set()))
        self.wait_window(win)
        return result["value"]

    # ---------- プリセット ----------
    def _save_preset(self):
        if not self._active_slot:
            return
        d, kf, af, argf = self._slot_fields(self._active_slot)
        key = d.get(kf)
        app = d.get(af, "")
        arg = d.get(argf, "")
        if action_value(key, app, arg) is None:
            messagebox.showwarning(
                "プリセット", "先に有効なアクションを設定してください。")
            return
        presets = self.cfg.setdefault("presets", [])
        if len(presets) >= MAX_PRESETS:
            messagebox.showwarning(
                "プリセット", f"プリセットは最大 {MAX_PRESETS} 個までです。")
            return
        name = self._ask_string(
            "プリセット保存", "プリセット名を入力してください:",
            short_label(key, app, arg))
        if not name or not name.strip():
            return
        name = name.strip()
        presets.append({"name": name, "key": key, "app": app, "arg": arg})
        self._refresh_presets()
        messagebox.showinfo("プリセット", f"「{name}」を保存しました。")

    def _assign_preset(self, preset):
        if not self._active_slot:
            messagebox.showinfo("プリセット",
                                "先にスイッチ/エンコーダを選択してください。")
            return
        d, kf, af, argf = self._slot_fields(self._active_slot)
        d[kf]   = preset.get("key", "（なし）")
        d[af]   = preset.get("app", "")
        d[argf] = preset.get("arg", "")
        self._mirror_enc_common(self._active_slot, kf, d[kf])
        self._mirror_enc_common(self._active_slot, af, d[af])
        self._mirror_enc_common(self._active_slot, argf, d[argf])
        self._build_detail()
        self._refresh_grid()

    def _refresh_presets(self):
        if not hasattr(self, "_preset_frame"):
            return
        for w in self._preset_frame.winfo_children():
            w.destroy()
        presets = self.cfg.get("presets", [])
        ctk.CTkLabel(self._preset_frame, text=f"プリセット ({len(presets)})",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#c084fc").pack(anchor="w", padx=6, pady=(4, 2))
        if not presets:
            ctk.CTkLabel(self._preset_frame, text="「＋プリセット保存」で追加",
                         font=ctk.CTkFont(size=10), text_color="#777"
                         ).pack(anchor="w", padx=8)
        for p in presets:
            ctk.CTkButton(self._preset_frame, text="★ " + p.get("name", "?"),
                          height=26, anchor="w", fg_color="#3a2f4a",
                          hover_color="#4a3a5a", font=ctk.CTkFont(size=11),
                          command=lambda pp=p: self._assign_preset(pp)
                          ).pack(fill="x", padx=6, pady=1)

    def _manage_presets(self):
        win = ctk.CTkToplevel(self)
        win.title("プリセット管理")
        win.geometry("380x440")
        win.transient(self)
        ctk.CTkLabel(win, text="プリセット一覧",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(12, 6))
        sf = ctk.CTkScrollableFrame(win)
        sf.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        def render():
            for w in sf.winfo_children():
                w.destroy()
            presets = self.cfg.get("presets", [])
            if not presets:
                ctk.CTkLabel(sf, text="プリセットはありません",
                             text_color="#888").pack(pady=12)
            for i, p in enumerate(presets):
                rowf = ctk.CTkFrame(sf)
                rowf.pack(fill="x", pady=2)
                ctk.CTkLabel(rowf, text=p.get("name", "?"), anchor="w"
                             ).pack(side="left", padx=8, fill="x", expand=True)
                ctk.CTkLabel(rowf, text=short_label(p.get("key"), p.get("app", ""),
                                                    p.get("arg", "")),
                             text_color="#888", anchor="e"
                             ).pack(side="left", padx=6)
                ctk.CTkButton(rowf, text="削除", width=50, fg_color="#b91c1c",
                              hover_color="#991b1b",
                              command=lambda idx=i: _delete(idx)).pack(side="right", padx=6)

        def _delete(idx):
            try:
                self.cfg["presets"].pop(idx)
            except (IndexError, KeyError):
                pass
            render()
            self._refresh_presets()

        render()
        win.after(60, lambda: (win.grab_set(), win.focus_force()))

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

    # ---------- プロファイル切替・管理 ----------
    def _on_profile_change(self, name):
        try:
            self._pi = self.cfg["profiles"].index(name)
        except ValueError:
            self._pi = 0
        self._select(("sw", 0))

    def _add_profile(self):
        import copy
        profs = self.cfg["profiles"]
        if len(profs) >= MAX_PROFILES:
            messagebox.showwarning(
                "プロファイル", f"プロファイルは最大 {MAX_PROFILES} 個までです。")
            return False
        n = len(profs) + 1
        name = f"プロファイル{n}"
        while name in profs:
            n += 1
            name = f"プロファイル{n}"
        profs.append(name)
        # スイッチ：SW1=プロファイル切替、残りは無効
        self.cfg["switches"].append(
            [{"key": "PROFILE_NEXT" if i == 0 else "（なし）", "app": "", "arg": ""}
             for i in range(SW_COUNT)])
        # エンコーダ：ENC1〜3共通を揃えるためプロファイル0をコピー
        self.cfg["encoders"].append(copy.deepcopy(self.cfg["encoders"][0]))
        return True

    def _delete_profile(self, idx):
        profs = self.cfg["profiles"]
        if len(profs) <= 1:
            messagebox.showwarning("プロファイル", "最低1つは必要です。")
            return False
        profs.pop(idx)
        self.cfg["switches"].pop(idx)
        self.cfg["encoders"].pop(idx)
        if self._pi >= len(profs):
            self._pi = len(profs) - 1
        return True

    def _manage_profiles(self):
        win = ctk.CTkToplevel(self)
        win.title("プロファイル管理")
        win.geometry("440x480")
        win.transient(self)
        ctk.CTkLabel(win, text="プロファイル（名前の変更・追加・削除）",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(12, 6))
        sf = ctk.CTkScrollableFrame(win)
        sf.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        bottom = ctk.CTkFrame(win, fg_color="transparent")
        bottom.pack(fill="x", padx=10, pady=(0, 10))

        def commit_rename(idx, var):
            new = var.get().strip()
            if not new:
                var.set(self.cfg["profiles"][idx])
                return
            if new in self.cfg["profiles"] and self.cfg["profiles"].index(new) != idx:
                messagebox.showwarning("プロファイル", "同名のプロファイルがあります。")
                var.set(self.cfg["profiles"][idx])
                return
            self.cfg["profiles"][idx] = new
            self._refresh_profile_menu()
            self._refresh_grid()

        def render():
            for w in sf.winfo_children():
                w.destroy()
            profs = self.cfg["profiles"]
            for i, p in enumerate(profs):
                rowf = ctk.CTkFrame(sf)
                rowf.pack(fill="x", pady=3)
                accent = PROFILE_ACCENTS[i % len(PROFILE_ACCENTS)]
                ctk.CTkLabel(rowf, text=f"P{i+1}", width=32, text_color=accent,
                             font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(8, 4))
                var = tk.StringVar(value=p)
                ent = ctk.CTkEntry(rowf, textvariable=var)
                ent.pack(side="left", padx=4, fill="x", expand=True)
                ent.bind("<Return>", lambda e, idx=i, v=var: commit_rename(idx, v))
                ent.bind("<FocusOut>", lambda e, idx=i, v=var: commit_rename(idx, v))
                ctk.CTkButton(rowf, text="削除", width=48, fg_color="#b91c1c",
                              hover_color="#991b1b",
                              command=lambda idx=i: _do_delete(idx)).pack(side="right", padx=6)
            info.configure(text=f"{len(profs)} / {MAX_PROFILES} プロファイル")

        def _do_delete(idx):
            if self._delete_profile(idx):
                render()
                self._refresh_profile_menu()
                self._select(("sw", 0))

        def _do_add():
            if self._add_profile():
                render()
                self._refresh_profile_menu()

        info = ctk.CTkLabel(bottom, text="", text_color="#888")
        info.pack(side="left")
        ctk.CTkButton(bottom, text="＋ プロファイル追加", fg_color="#16a34a",
                      hover_color="#15803d", command=_do_add).pack(side="right")

        render()
        win.after(60, lambda: (win.grab_set(), win.focus_force()))

    # ---------- Pico 操作 ----------
    def _check_pico(self):
        drive = find_pico_drive()
        if drive:
            self._conn_lbl.configure(text=f"● ドライブ: {drive}",
                                     text_color="#22c55e")
        else:
            self._conn_lbl.configure(text="● ドライブ未検出", text_color="#ef4444")
            messagebox.showwarning(
                "未検出",
                "Pico のドライブ（USBストレージ）が見つかりません。\n"
                "config.py 書き込みには MicroPython の Pico を USB 接続してください。")

    def _save(self):
        self._save_json()
        messagebox.showinfo("保存完了", f"{CONFIG_JSON} に保存しました。")

    def _reset(self):
        if messagebox.askyesno("リセット", "全プロファイルをデフォルトに戻しますか？"):
            # cfg は統合UIやエージェントと共有参照のため、差し替えず中身を置換する
            self.cfg.clear()
            self.cfg.update(default_config())
            self._pi = 0
            self._refresh_profile_menu()
            self._bright.set(self.cfg["display"]["brightness"])
            self._bright_lbl.configure(text=f"{self.cfg['display']['brightness']}%")
            self._select(("sw", 0))

    def _refresh_profile_menu(self):
        self._prof_menu.configure(values=self.cfg["profiles"])
        self._prof_menu.set(self.cfg["profiles"][self._pi])

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


# ===== 単体起動用 薄いラッパー（統合UIからは EditorFrame を直接埋め込む）=====
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
        cfg = load_config()
        self.editor = EditorFrame(self, cfg, on_live_apply=on_live_apply)
        self.editor.pack(fill="both", expand=True)


if __name__ == "__main__":
    app = App()
    app.mainloop()
