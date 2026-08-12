# fontgen.py
# 設定で実際に使う文字だけの 16x16 日本語フォント（Pico用 jpfont.py）を生成する。
# 「Picoに書き込む」時に config.py と一緒に書き出すことで、
# プロファイル名・プリセット名など任意の日本語が LCD で確実に表示できるようにする。
#
# 収録対象（非ASCIIのみ。ASCIIは Pico 内蔵フォントで描くため不要）:
#   - 基本セット（曜日・記号・時計まわり）
#   - 天気語（agent._WMO_TO_DESC の全値）
#   - cfg 由来（profiles / スイッチ・エンコーダの label / presets の name）
from __future__ import annotations

import sys
from pathlib import Path

WIDTH  = 16
HEIGHT = 16

# Windows の日本語 TTF 候補（上から順に使用）
_FONT_CANDIDATES = [
    (r"C:\Windows\Fonts\msgothic.ttc", 0),     # MS ゴシック（小サイズが読みやすい）
    (r"C:\Windows\Fonts\YuGothM.ttc",  0),     # 游ゴシック Medium
    (r"C:\Windows\Fonts\meiryo.ttc",   0),     # メイリオ
    (r"C:\Windows\Fonts\BIZ-UDGothicR.ttc", 0),
]

# 天気/日付/UI でランタイムに使う基本文字（cfg に現れない分をここで担保）
_BASE_CHARS = "月火水木金土日年月分秒時（）／：・、。％？！ー～＋－＝"


def _weather_chars() -> str:
    """agent の天気語（_WMO_TO_DESC の全値）を取り込む。読めなければ既定語。"""
    try:
        import agent
        return "".join(agent._WMO_TO_DESC.values())
    except Exception:
        return "晴曇時々雨大雪霧にわか激しい雷取得失敗不明"


def collect_chars(cfg: dict) -> list[str]:
    """cfg とランタイム由来から、必要な非ASCII文字の集合（ソート済み）を返す。"""
    buf = [_BASE_CHARS, _weather_chars()]
    buf += list(cfg.get("profiles", []))
    for prof in cfg.get("switches", []):
        for sw in prof:
            buf.append(sw.get("label", "") or "")
    for prof in cfg.get("encoders", []):
        for enc in prof:
            for dk in ("cw", "ccw", "push"):
                buf.append(enc.get(f"label_{dk}", "") or "")
    for pr in cfg.get("presets", []):
        buf.append(pr.get("name", "") or "")
    chars = set()
    for s in buf:
        for ch in s:
            if ord(ch) >= 128:      # ASCII は内蔵フォントで描くので除外
                chars.add(ch)
    return sorted(chars)


def _load_font():
    from PIL import ImageFont
    for path, idx in _FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, HEIGHT, index=idx)
    raise FileNotFoundError("日本語 TTF が見つかりません（msgothic/YuGoth/meiryo）")


def _glyph_bytes(font, ch: str) -> bytes:
    """1文字を 16x16 MONO_HLSB（32バイト, bit7=左端）へ。中央寄せ。"""
    from PIL import Image, ImageDraw
    img = Image.new("L", (WIDTH, HEIGHT), 0)
    d = ImageDraw.Draw(img)
    try:
        bb = d.textbbox((0, 0), ch, font=font)
    except Exception:
        bb = (0, 0, WIDTH, HEIGHT)
    gw = bb[2] - bb[0]; gh = bb[3] - bb[1]
    ox = (WIDTH  - gw) // 2 - bb[0]
    oy = (HEIGHT - gh) // 2 - bb[1]
    d.text((ox, oy), ch, font=font, fill=255)
    px = img.load()
    out = bytearray(HEIGHT * 2)
    for y in range(HEIGHT):
        b0 = 0; b1 = 0
        for x in range(WIDTH):
            if px[x, y] > 110:
                if x < 8:
                    b0 |= 0x80 >> x
                else:
                    b1 |= 0x80 >> (x - 8)
        out[y * 2] = b0
        out[y * 2 + 1] = b1
    return bytes(out)


def build_jpfont_text(cfg: dict):
    """cfg から必要文字だけの jpfont.py ソース文字列を生成。
    戻り値: (source_text, char_count)。PIL/TTF が無ければ例外。"""
    font  = _load_font()
    chars = collect_chars(cfg)
    lines = [
        "# jpfont.py  16x16 日本語ビットマップフォント（設定から自動生成）",
        "# MONO_HLSB・32バイト/字。実際に使う文字のみ収録。display.text_jp が参照。",
        "WIDTH = 16",
        "HEIGHT = 16",
        "",
        "FONT = {",
    ]
    for ch in chars:
        lines.append("    %r: %r," % (ch, _glyph_bytes(font, ch)))
    lines.append("}")
    lines.append("")
    return "\n".join(lines), len(chars)


def static_jpfont_path() -> Path | None:
    """フォールバック用：同梱の静的 jpfont.py の場所（exe/ソース両対応）。"""
    candidates = []
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        candidates.append(Path(meipass) / "jpfont.py")
    candidates.append(Path(__file__).resolve().parent.parent / "streamdeck" / "jpfont.py")
    for p in candidates:
        if p.exists():
            return p
    return None


def write_jpfont(cfg: dict, drive: Path):
    """jpfont.py を Pico ドライブへ書き込む。
    まず cfg から動的生成、失敗時は静的版をコピー、それも無ければスキップ。
    戻り値: 人間向けメッセージ文字列。"""
    try:
        text, n = build_jpfont_text(cfg)
        with open(drive / "jpfont.py", "w", encoding="utf-8") as f:
            f.write(text)
        return f"日本語フォント jpfont.py を生成しました（使用 {n} 字）。"
    except Exception as e:
        src = static_jpfont_path()
        if src:
            try:
                import shutil
                shutil.copyfile(src, drive / "jpfont.py")
                return f"フォント自動生成に失敗（{e}）。同梱の jpfont.py をコピーしました。"
            except Exception as e2:
                return f"フォント書き込み失敗（{e2}）。Pico の既存 jpfont.py を使用します。"
        return f"フォント自動生成に失敗（{e}）。Pico の既存 jpfont.py を使用します。"
