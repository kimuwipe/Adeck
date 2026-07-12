# config.py  v3.1
# プロファイル対応版
# configurator.py から自動生成される場合は上書きされます

# ===== プロファイル名一覧（SW1で順繰り切替）=====
PROFILES = ["汎用", "SolidWorks", "音声", "開発"]

# ===== キー定義凡例 =====
# "ACTION_NAME"          → hid.py で定義されたアクション（PC側でキー送信）
# "APP:C:/path/to/app"   → PC側でアプリ/ショートカット(.lnk/.url)起動
# "URL:https://..."      → PC側で既定ブラウザでURLを開く
# "CMD:command args"     → PC側でシェルコマンド実行
# "TEXT:入力文字列"       → PC側でテキスト入力（\n=改行、日本語対応）
# "KEY:ctrl c"           → PC側でキーコンビ送信（空白区切り・記録ボタンで設定）
# "PROFILE_NEXT"         → プロファイル順繰り切替（SW1固定推奨）
# None                   → 無効

# ==========================================
# スイッチ割り当て  SWITCH_MAP[profile][sw 0-7]
# ==========================================
SWITCH_MAP = [
    # ---- 汎用 ----
    [
        "PROFILE_NEXT",     # SW1: プロファイル順繰り切替
        "WIN_SNIP",         # SW2: スクリーンショット (Win+Shift+S)
        "VDESK_NEXT",       # SW3: 仮想デスク→ (Ctrl+Win+→)
        "VDESK_PREV",       # SW4: 仮想デスク← (Ctrl+Win+←)
        "WIN_MAX",          # SW5: ウィンドウ最大化 (Win+↑)
        "TASK_MGR",         # SW6: タスクマネージャ (Ctrl+Shift+Esc)
        "APP_CALC",         # SW7: 電卓起動（エージェント経由）
        "WIN_LOCK",         # SW8: ロック画面 (Win+L)
    ],
    # ---- SolidWorks ----
    [
        "PROFILE_NEXT",     # SW1: プロファイル順繰り切替
        "SW_SHORTCUT_BAR",  # SW2: ショートカットバー (S)
        "SW_REBUILD",       # SW3: 再ビルド (Ctrl+B)
        "SW_REBUILD_FULL",  # SW4: 強制再ビルド (Ctrl+Q)
        "SW_NORMAL_TO",     # SW5: Normal To (Ctrl+8)
        "SW_FILTER_CLEAR",  # SW6: 選択フィルタ解除 (F6)
        "SW_DISPLAY_CYCLE", # SW7: 表示スタイル順繰り切替
        "SW_MAGNIFIER",     # SW8: マグニファイア (G)
    ],
    # ---- 音声 ----
    [
        "PROFILE_NEXT",     # SW1: プロファイル順繰り切替
        "MEDIA_PLAY",       # SW2: 再生/停止
        "MEDIA_NEXT",       # SW3: 次の曲
        "MEDIA_PREV",       # SW4: 前の曲
        "MUTE",             # SW5: マスターミュート
        "F13",              # SW6: カスタム（配信ソフト用）
        "F14",              # SW7: カスタム
        "F15",              # SW8: カスタム
    ],
    # ---- 開発 ----
    [
        "PROFILE_NEXT",     # SW1: プロファイル順繰り切替
        "F5",               # SW2: 実行/デバッグ開始
        "SHIFT_F5",         # SW3: デバッグ停止
        "F9",               # SW4: ブレークポイント切替
        "F10",              # SW5: ステップオーバー
        "F11",              # SW6: ステップイン
        "DEV_TERMINAL",     # SW7: ターミナル表示 (Ctrl+`)
        "DEV_COMMENT",      # SW8: コメントアウト (Ctrl+/)
    ],
]

# ==========================================
# エンコーダ割り当て  ENCODER_MAP[profile][enc 0-3] = (CW, CCW, Push)
# ENC1〜3は全プロファイル共通、ENC4のみプロファイル別
# ==========================================

_ENC_COMMON = [
    ("VOLUME_UP",    "VOLUME_DOWN", "MUTE"),     # ENC1: マスター音量
    ("UNDO",         "REDO",        "SAVE"),      # ENC2: Undo/Redo・保存
    ("ZOOM_IN",      "ZOOM_OUT",    "ZOOM_FIT"),  # ENC3: ズーム
]

_ENC4_BY_PROFILE = [
    ("TAB_NEXT",     "TAB_PREV",    "NEW_TAB"),       # 汎用: タブ切替
    ("SW_VIEW_NEXT", "SW_VIEW_PREV","SW_ISO"),         # SW: 標準ビュー順送り
    ("MIC_UP",       "MIC_DOWN",    "MIC_MUTE"),       # 音声: マイクゲイン
    ("FONT_UP",      "FONT_DOWN",   "DEV_GOTO_DEF"),   # 開発: フォントサイズ
]

# リスト結合（各プロファイルで4要素のリストを生成）
ENCODER_MAP = [
    _ENC_COMMON + [_ENC4_BY_PROFILE[i]]
    for i in range(len(PROFILES))
]

# ==========================================
# ディスプレイ設定
# ==========================================
DISPLAY_BRIGHTNESS = 80   # 0〜100
DISPLAY_ROTATION   = 0    # 0 / 90 / 180 / 270

# ==========================================
# デバウンス設定（ms）
# ==========================================
SWITCH_DEBOUNCE_MS  = 20
ENCODER_DEBOUNCE_MS = 5
