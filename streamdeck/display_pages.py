# display_pages.py  v3
# 横画面（320×170px）5ページ描画
# text()はデフォルトscale=2（16px）、small_text()は8px
#
# レイアウト基準
#   1文字 = 16px幅×16px高（scale=2）
#   画面幅320px → 1行最大20文字
#   画面高170px
#   ヘッダ高 18px、フッター（ドット）8px
#   コンテンツエリア 170-18-8 = 144px → 行数 144//18 = 8行

from display import LCD, W, H

PAGE_VOL_WEATHER = 0
PAGE_APPS        = 1
PAGE_PROFILE     = 2
PAGE_SW_MAP      = 3
PAGE_ENC_MAP     = 4
PAGE_COUNT       = 5

# ===== 色定数（RGB565）=====
BLACK  = 0x0000
WHITE  = 0xFFFF
GRAY   = 0x7BEF
DKGRAY = 0x2965
CYAN   = 0x07FF
YELLOW = 0xFFE0
GREEN  = 0x07E0
RED    = 0xF800
ORANGE = 0xFD20
BLUE   = 0x001F
TEAL   = 0x0540
NAVY   = 0x000D
GOLD   = 0xFEA0
PURPLE = 0x801F
MAROON = 0x8000   # 濃い赤（SWマップのヘッダ）
DGREEN = 0x0340   # 濃い緑（ENCマップのヘッダ）

PROFILE_COLORS = [CYAN, GREEN, YELLOW, ORANGE]

WEATHER_ICON = {
    "sunny":   "SUNNY",
    "cloudy":  "CLOUD",
    "rainy":   "RAIN",
    "snowy":   "SNOW",
    "unknown": "?????",
}

# レイアウト定数
HDR_H   = 18     # ヘッダ高さ（small_text=8px + 余白）
DOT_Y   = H - 9  # ページドット Y座標
BODY_Y  = HDR_H + 2          # コンテンツ開始Y
BODY_H  = DOT_Y - BODY_Y     # コンテンツ高さ（約144px）
CH      = 18     # scale=2 の1行高さ（16px + 2px余白）
SH      = 10     # small_text の1行高さ（8px + 2px余白）
COL_DIV = 152    # 左右カラム境界X
COL_R   = COL_DIV + 3
PAD     = 4


# ===== 共通パーツ =====

def _header(lcd: LCD, title: str, color: int):
    """カラーヘッダバー（濃色＋白文字で読みやすく）。
    右上は現在プロファイル（プリセット）バッジ用に空けておく。"""
    lcd.rect(0, 0, W, HDR_H, color, fill=True)
    lcd.small_text(title[:22], PAD, 5, WHITE)


def _profile_badge(lcd: LCD, state) -> None:
    """全ページ共通：右上に現在プロファイルをバッジ表示（プロファイル色）。
    画面タップで次プロファイルへ切替わる（タップ処理は main.py 側）。
    ASCII名は8pxで最大8字、日本語を含む名前は16px日本語フォントで最大4字表示。"""
    from config import PROFILES
    pi   = state.profile
    col  = PROFILE_COLORS[pi % len(PROFILE_COLORS)]
    name = PROFILES[pi] if pi < len(PROFILES) else ""
    is_ascii = bool(name) and all(ord(c) < 128 for c in name)
    bw  = W * 2 // 5              # バッジ領域は画面の約2/5で固定
    x0  = W - bw
    pad = 6
    # ページ名とプロファイルバッジの境界線（白の縦線）＋バッジ背景
    lcd.rect(x0 - 2, 0, 2, HDR_H, WHITE, fill=True)
    lcd.rect(x0, 0, bw, HDR_H, col, fill=True)
    if is_ascii:
        label = name[:(bw - pad * 2) // 8]       # 領域に収まる最大長
        lcd.small_text(label, W - len(label) * 8 - pad, 5, BLACK)   # 右詰め
    else:
        label = (name or "P{}".format(pi + 1))[:(bw - pad * 2) // 16]
        lcd.text_jp(label, W - len(label) * 16 - pad, 1, BLACK)     # 右詰め

def _vline(lcd: LCD):
    """垂直区切り線"""
    lcd.rect(COL_DIV, HDR_H, 1, DOT_Y - HDR_H, DKGRAY, fill=True)

def _hline(lcd: LCD, y: int, x0: int = 0, x1: int = W):
    lcd.rect(x0, y, x1 - x0, 1, DKGRAY, fill=True)

def _dots(lcd: LCD, current: int):
    """下部ページドットインジケータ"""
    spacing = 14
    start_x = (W - PAGE_COUNT * spacing) // 2
    for i in range(PAGE_COUNT):
        col = WHITE if i == current else DKGRAY
        lcd.rect(start_x + i * spacing, DOT_Y, 6, 6, col, fill=True)

def _bar(lcd: LCD, x: int, y: int, w: int, h: int, value: int, color: int):
    """値バー 0〜100"""
    lcd.rect(x, y, w, h, DKGRAY, fill=True)
    filled = max(0, min(w, int(w * value / 100)))
    if filled:
        lcd.rect(x, y, filled, h, color, fill=True)

def _section(lcd: LCD, x: int, y: int, label: str) -> int:
    """セクションラベル（small_text）→ 次のY座標を返す"""
    lcd.small_text(label, x, y, DKGRAY)
    _hline(lcd, y + 9, x, x + min(len(label) * 8 + 4, W - x))
    return y + SH

def _name_line(lcd: LCD, s: str, x: int, y: int, color: int,
               ascii_max: int = 14, jp_max: int = 8) -> int:
    """名前行を描画：英字(ASCII)のみなら10px(scaled_text)、日本語を含めば16px(text_jp)。
    日本語フォントは16pxのみのため文字種で自動選択する。使用した行高さを返す。"""
    for ch in s:
        if ord(ch) >= 128:
            lcd.text_jp(s[:jp_max], x, y, color)
            return CH
    lcd.scaled_text(s[:ascii_max], x, y, color)
    return 12


# ===== ページ0: 日付時刻・音量・マイク・天気 =====
def draw_page0(lcd: LCD, page: int, state) -> None:
    lcd.fill(BLACK)
    _header(lcd, "CLOCK / VOL / WX", TEAL)

    # ── 日付/時刻（16px・曜日は漢字。PC未接続時はプレースホルダ）
    dt = state.datetime if state.datetime else "--/--(-) --:--"
    lcd.text_jp(dt, PAD, BODY_Y, WHITE)

    top = BODY_Y + 20                       # 日付行の下からカラム開始
    lcd.rect(COL_DIV, top, 1, DOT_Y - top, DKGRAY, fill=True)  # 縦区切り

    # ── 左カラム: 音量
    y = top
    y = _section(lcd, PAD, y, "VOLUME")
    vol = state.volume
    if vol < 0:
        lcd.text("---%", PAD, y, GRAY)
    else:
        vcol = RED if vol > 80 else (ORANGE if vol > 50 else GREEN)
        lcd.text(f"{vol:3d}%", PAD, y, vcol)
        _bar(lcd, PAD, y + 18, COL_DIV - PAD * 2, 5, vol, vcol)
    y += CH + 6

    mic = state.mic_volume
    y = _section(lcd, PAD, y, "MIC")
    if mic < 0:
        lcd.text("---%", PAD, y, GRAY)
    else:
        lcd.text(f"{mic:3d}%", PAD, y, GREEN)
        _bar(lcd, PAD, y + 18, COL_DIV - PAD * 2, 5, mic, GREEN)
    y += CH + 6

    if vol == 0:
        lcd.text("MUTED", PAD, y, RED)

    # ── 右カラム: 天気
    y = top
    y = _section(lcd, COL_R, y, "WEATHER")
    w   = state.weather
    con = w.get("condition", "unknown")
    lcd.text(WEATHER_ICON.get(con, "?????"), COL_R, y, CYAN)
    y += CH
    temp = w.get("temp", "--")
    lcd.text(f"{temp}C", COL_R, y, YELLOW)
    y += CH
    hum = w.get("humidity", "--")
    lcd.small_text(f"HUM:{hum}%", COL_R, y, 0x82B1FF)
    y += SH + 2
    # 天気説明（日本語・16px）
    desc = str(w.get("desc", "----"))[:8]
    lcd.text_jp(desc, COL_R, y, WHITE)

    _dots(lcd, page)


# ===== ページ1: 起動中アプリ =====
def draw_page1(lcd: LCD, page: int, state) -> None:
    lcd.fill(BLACK)
    _header(lcd, "RUNNING APPS", NAVY)
    _vline(lcd)

    apps  = state.apps or []
    # 左カラム: 先頭8件（small_textで小さく表示）
    y = BODY_Y
    y = _section(lcd, PAD, y, "ACTIVE")
    for app in apps[:8]:
        lcd.scaled_text(app[:14], PAD, y, WHITE)   # 10px（8pxより少し大きく）
        y += 12
        if y > DOT_Y - 12:
            break

    # 右カラム: 9件目以降（small_textで多めに表示）
    y = BODY_Y
    y = _section(lcd, COL_R, y, "MORE")
    rest = apps[8:16]
    if rest:
        for app in rest:
            lcd.small_text(app[:18], COL_R, y, GRAY)
            y += SH + 2
            if y > DOT_Y - SH:
                break
    else:
        lcd.small_text("--", COL_R, y, DKGRAY)

    _dots(lcd, page)


# ===== ページ2: 現在プロファイル =====
def draw_page2(lcd: LCD, page: int, state) -> None:
    from config import PROFILES
    lcd.fill(BLACK)
    pi   = state.profile
    pcol = PROFILE_COLORS[pi % len(PROFILE_COLORS)]
    _header(lcd, "PROFILE", PURPLE)   # ヘッダは固定色（プロファイル色はバッジ側）
    _vline(lcd)

    # 左カラム: 現在（日本語対応・16px）
    y = BODY_Y
    y = _section(lcd, PAD, y, "NOW")
    lcd.text_jp((PROFILES[pi] if pi < len(PROFILES) else "")[:6], PAD, y, pcol)
    y += CH + 4
    lcd.small_text("TAP:next", PAD, y, DKGRAY)

    # 右カラム: 一覧（英字は8px・日本語は16px。多い場合は現在位置が入る窓で表示）
    y = BODY_Y
    y = _section(lcd, COL_R, y, "ALL")
    maxrows = 8
    start   = 0
    if pi >= maxrows:
        start = pi - maxrows + 1
    for i in range(start, min(len(PROFILES), start + maxrows)):
        arrow = ">" if i == pi else " "
        col   = pcol if i == pi else GRAY
        y += _name_line(lcd, f"{arrow}{PROFILES[i]}", COL_R, y, col)
        if y > DOT_Y - SH:
            break

    _dots(lcd, page)


# ===== ページ3: スイッチ割り当て =====
def draw_page3(lcd: LCD, page: int, state) -> None:
    import config as _cfg
    from config import SWITCH_MAP, PROFILES
    lcd.fill(BLACK)
    pi   = state.profile
    pcol = PROFILE_COLORS[pi % len(PROFILE_COLORS)]
    _header(lcd, "SWITCH MAP", MAROON)   # ヘッダは固定色（プロファイルはバッジ）

    sws    = SWITCH_MAP[pi]
    # スイッチのプリセット名（設定アプリで付与。無ければアクション文字列を表示）
    labels = getattr(_cfg, "SWITCH_LABELS", None)
    plabels = labels[pi] if (labels and pi < len(labels)) else None
    # 4行×2列グリッド
    cw     = (W - PAD * 3) // 2   # セル幅
    cell_h = (DOT_Y - HDR_H - 2) // 4

    for i in range(min(8, len(sws))):
        col_i = i % 2
        row_i = i // 2
        cx    = PAD + col_i * (cw + PAD)
        cy    = HDR_H + 2 + row_i * cell_h

        # セル背景
        lcd.rect(cx, cy, cw, cell_h - 2, 0x18C6, fill=True)

        # SW番号（small_text）
        lcd.small_text(f"SW{i+1}", cx + 2, cy + 2, DKGRAY)

        # プリセット名（あれば）→ 無ければアクション文字列。
        # 英字は8px、日本語(プリセット名)は16pxで自動表示。
        lab = plabels[i] if (plabels and i < len(plabels)) else None
        if lab:
            disp = str(lab)
        else:
            action = sws[i]
            if action is None:
                disp = "--"
            elif action == "PROFILE_NEXT":
                disp = "PROF.NXT"
            else:
                disp = action
        _name_line(lcd, disp, cx + 2, cy + 13, WHITE, ascii_max=16, jp_max=7)

    _dots(lcd, page)


# ===== ページ4: エンコーダ割り当て =====
def draw_page4(lcd: LCD, page: int, state) -> None:
    from config import ENCODER_MAP, PROFILES
    lcd.fill(BLACK)
    pi   = state.profile
    pcol = PROFILE_COLORS[pi % len(PROFILE_COLORS)]
    _header(lcd, "ENCODER MAP", DGREEN)   # ヘッダは固定色（プロファイルはバッジ）
    _vline(lcd)

    encs   = ENCODER_MAP[pi]
    labels = ["VOL", "EDIT", "ZOOM", "ENC4"]

    # 左カラム: ENC1・ENC2
    y = BODY_Y
    for i in range(2):
        enc = encs[i] if i < len(encs) else None
        lcd.text(labels[i], PAD, y, GOLD)
        y += CH
        if enc:
            cw, ccw, push = enc
            lcd.small_text(f">{(cw  or '--')[:16]}", PAD, y, CYAN);  y += SH
            lcd.small_text(f"P:{(push or '--')[:15]}", PAD, y, GREEN); y += SH
        else:
            lcd.small_text("--", PAD, y, DKGRAY); y += SH
        _hline(lcd, y + 1, PAD, COL_DIV - PAD); y += 4

    # 右カラム: ENC3・ENC4
    y = BODY_Y
    for i in range(2, 4):
        enc = encs[i] if i < len(encs) else None
        lcd.text(labels[i], COL_R, y, GOLD)
        y += CH
        if enc:
            cw, ccw, push = enc
            lcd.small_text(f">{(cw  or '--')[:16]}", COL_R, y, CYAN);  y += SH
            lcd.small_text(f"P:{(push or '--')[:15]}", COL_R, y, GREEN); y += SH
        else:
            lcd.small_text("--", COL_R, y, DKGRAY); y += SH
        _hline(lcd, y + 1, COL_R, W - PAD); y += 4

    _dots(lcd, page)


# ===== ディスパッチャ =====
_DRAW_FUNCS = [
    draw_page0,
    draw_page1,
    draw_page2,
    draw_page3,
    draw_page4,
]

def draw_page(lcd: LCD, page: int, state) -> None:
    _DRAW_FUNCS[page % PAGE_COUNT](lcd, page, state)
    _profile_badge(lcd, state)   # 全ページ共通：現在プロファイルのバッジ
