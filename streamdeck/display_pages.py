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
    """カラーヘッダバー（small_text=8px で描画）"""
    lcd.rect(0, 0, W, HDR_H, color, fill=True)
    lcd.small_text(title[:38], PAD, 5, BLACK)
    hint = "< swipe >"
    lcd.small_text(hint, W - len(hint) * 8 - PAD, 5, 0x3186)

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


# ===== ページ0: 音量・マイク・天気 =====
def draw_page0(lcd: LCD, page: int, state) -> None:
    lcd.fill(BLACK)
    _header(lcd, "VOL & WEATHER", TEAL)
    _vline(lcd)

    # ── 左カラム: 音量
    y = BODY_Y
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

    # ミュート表示
    if vol == 0:
        lcd.text("MUTED", PAD, y, RED)

    # ── 右カラム: 天気
    y = BODY_Y
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
    y += SH

    desc = str(w.get("desc", "------"))[:10]
    lcd.small_text(desc, COL_R, y, WHITE)

    _dots(lcd, page)


# ===== ページ1: 起動中アプリ =====
def draw_page1(lcd: LCD, page: int, state) -> None:
    lcd.fill(BLACK)
    _header(lcd, "RUNNING APPS", NAVY)
    _vline(lcd)

    apps  = state.apps or []
    # 左カラム: 先頭4件（scale=2で表示）
    y = BODY_Y
    y = _section(lcd, PAD, y, "ACTIVE")
    for app in apps[:4]:
        lcd.text(app[:8], PAD, y, WHITE)
        y += CH
        if y > DOT_Y - CH:
            break

    # 右カラム: 5件目以降（small_textで多めに表示）
    y = BODY_Y
    y = _section(lcd, COL_R, y, "MORE")
    rest = apps[4:12]
    if rest:
        for app in rest:
            lcd.small_text(app[:18], COL_R, y, GRAY)
            y += SH
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
    pcol = PROFILE_COLORS[pi]
    _header(lcd, "PROFILE", pcol)
    _vline(lcd)

    # 左カラム: 現在
    y = BODY_Y
    y = _section(lcd, PAD, y, "NOW")
    lcd.text(PROFILES[pi][:8], PAD, y, pcol)
    y += CH + 4
    lcd.small_text("SW1:next", PAD, y, DKGRAY)

    # 右カラム: 一覧
    y = BODY_Y
    y = _section(lcd, COL_R, y, "ALL")
    for i, p in enumerate(PROFILES):
        arrow = ">" if i == pi else " "
        col   = pcol if i == pi else GRAY
        lcd.small_text(f"{arrow}{p[:14]}", COL_R, y, col)
        y += SH + 2

    _dots(lcd, page)


# ===== ページ3: スイッチ割り当て =====
def draw_page3(lcd: LCD, page: int, state) -> None:
    from config import SWITCH_MAP, PROFILES
    lcd.fill(BLACK)
    pi   = state.profile
    pcol = PROFILE_COLORS[pi]
    _header(lcd, f"SW:{PROFILES[pi]}", pcol)

    sws    = SWITCH_MAP[pi]
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

        # アクション（scale=2、長い場合は短縮）
        action = sws[i]
        if action is None:
            label = "--"
        elif action == "PROFILE_NEXT":
            label = "PROF.NXT"
        else:
            label = action[:8]
        lcd.text(label, cx + 2, cy + 12, WHITE)

    _dots(lcd, page)


# ===== ページ4: エンコーダ割り当て =====
def draw_page4(lcd: LCD, page: int, state) -> None:
    from config import ENCODER_MAP, PROFILES
    lcd.fill(BLACK)
    pi   = state.profile
    pcol = PROFILE_COLORS[pi]
    _header(lcd, f"ENC:{PROFILES[pi]}", pcol)
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
