# display.py  v4
# Waveshare 1.9inch Touch LCD (ST7789V2) ドライバ
# ソフト回転方式：物理は縦向き(170x320)、論理は横向き(320x170)
#
# 【確定した正解構成（実機検証済み）】
#   物理パネル: 170(W) x 320(H) 縦向き
#   MADCTL = 0x00（縦向き）
#   INVON  = ON（色反転）
#   列オフセット = 35（CASET側、240-170=70の半分）
#   バイトスワップ = なし
#
# 論理座標（横向き320x170）→ 物理座標（縦170x320）の変換：
#   物理縦バッファに直接描画することで回転ループを不要にし高速化。
#   論理(lx, ly) → 物理(px, py):  px = ly,  py = (LOGICAL_W-1) - lx
#   ※実機で確定した回転方向 dfb.pixel(y, W-1-x) と同じ

from machine import SPI, Pin, PWM
import time
import framebuf
import micropython

# ピン定義
_SCK  = 18
_MOSI = 19
_DC   = 20
_RST  = 21
_CS0  = 17
_CS1  = 16
_BL0  = 26
_BL1  = 27

# 論理解像度（横向き）
W = 320   # 論理幅
H = 170   # 論理高さ

# 物理解像度（縦向きパネル）
_PW = 170
_PH = 320
_PANEL_OFFSET = 35   # ST7789V2: (240-170)/2

# LCDを180°逆向きに取り付けた場合、描画を180°回転して補正する。
# 画面が上下逆に見える時は True。画面ごとに個別設定できる。
LCD0_FLIP180 = True   # LCD① (CS=GP17)
LCD1_FLIP180 = True   # LCD② (CS=GP16)

# show() の内訳（回転 vs SPI転送）を計測してログ出力（計測時のみ True に）
_SHOW_PERF = False

# 日本語ビットマップフォント（jpfont.py があれば読み込む。無ければASCIIのみ）
try:
    import jpfont
    _JPFONT = jpfont.FONT
except Exception:
    _JPFONT = {}
# 日本語グリフ(MONO)を色付きblitするための2色パレット（描画時にindex1へ色をセット）。
# 透明キーは番兵色 0x0001（ほぼ黒・実描画しない）にする。こうすると前景に黒
# (0x0000) を指定しても keyと一致せず描画できる（バッジの黒文字対策）。
# ※blitのkeyはパレット適用「後」の色と比較される（MicroPython仕様）。
_JP_KEY = 0x0001
_jp_pal = framebuf.FrameBuffer(bytearray(4), 2, 1, framebuf.RGB565)
_jp_pal.pixel(0, 0, _JP_KEY)   # index0=背景=透明キー番兵

# ST7789V2 コマンド
_SWRESET = 0x01
_SLPOUT  = 0x11
_COLMOD  = 0x3A
_MADCTL  = 0x36
_CASET   = 0x2A
_RASET   = 0x2B
_RAMWR   = 0x2C
_INVON   = 0x21
_NORON   = 0x13
_DISPON  = 0x29

_MADCTL_PORTRAIT = 0x00   # 縦向き固定


class LCD:
    """
    論理的には横向き320x170として描画APIを提供するが、
    内部の framebuffer は物理縦向き170x320 で保持する。
    描画メソッドは論理座標→物理座標へ変換して縦バッファに直接描く。
    """
    def __init__(self, spi, cs_pin, bl_pin, log_buf, log_fb, tx_buf, do_reset=True,
                 flip180=False):
        self._spi = spi
        self._flip180 = flip180
        self._cs  = Pin(cs_pin, Pin.OUT, value=1)
        self._dc  = Pin(_DC,  Pin.OUT)
        self._rst = Pin(_RST, Pin.OUT)
        self._bl  = PWM(Pin(bl_pin))
        self._bl.freq(1000)
        self.set_brightness(80)
        # 論理(横向き320x170)フレームバッファ（2画面で共有）に直接描画し、
        # show() で物理(縦170x320)へ回転＋バイトスワップして転送する。
        # これで文字描画のピクセル単位ソフト回転(遅い)が不要になり高速化。
        self._lbuf  = log_buf
        self._fb    = log_fb
        self._txbuf = tx_buf   # 物理転送バッファ（回転+スワップ結果・共有）
        # RSTは全画面共有なので、最初の1枚だけハードリセットを行う。
        # レジスタ設定は各画面のCSを選択して個別に流す。
        if do_reset:
            self._hard_reset()
        self._init_regs()

    def _cs_low(self):  self._cs.value(0)
    def _cs_high(self): self._cs.value(1)

    def _write_cmd(self, cmd):
        self._dc.value(0); self._cs_low()
        self._spi.write(bytes([cmd]))
        self._cs_high()

    def _write_data(self, data):
        self._dc.value(1); self._cs_low()
        self._spi.write(
            data if isinstance(data, (bytes, bytearray)) else bytes([data]))
        self._cs_high()

    def _hard_reset(self):
        # RSTピンは全画面共有。ハードリセットは1回だけ実行する。
        self._rst.value(0); time.sleep_ms(150)
        self._rst.value(1); time.sleep_ms(150)

    def _init_regs(self):
        # このLCDのCSを選択してレジスタを個別設定する。
        # （_write_cmd/_write_data が自分のCSだけLOWにするので画面別に効く）
        self._write_cmd(_SLPOUT);  time.sleep_ms(150)
        self._write_cmd(_COLMOD);  self._write_data(0x55)
        self._write_cmd(_MADCTL);  self._write_data(_MADCTL_PORTRAIT)
        self._write_cmd(_INVON)
        self._write_cmd(_DISPON);  time.sleep_ms(10)

    def set_brightness(self, pct):
        # 負論理（LOWで点灯）：duty反転
        pct  = max(0, min(100, pct))
        duty = int(65535 * (100 - pct) / 100)
        self._bl.duty_u16(duty)

    # ---------- 描画API（論理座標で framebuf に直接描く＝ネイティブ・高速）----------
    def fill(self, color):
        self._fb.fill(color)

    def small_text(self, s, x, y, color):
        # 8pxフォントはネイティブ描画（回転はshow時にまとめて行う）
        self._fb.text(s, x, y, color)

    def text_jp(self, s, x, y, color):
        """ASCIIと日本語(16x16)の混在文字列を16px等幅で描く。
        ASCIIは scale=2 の内蔵フォント、日本語は jpfont のグリフを blit。
        未収録の日本語文字は '?' で表示。"""
        cx = x
        for ch in s:
            if ord(ch) < 128:
                self.text(ch, cx, y, color, scale=2)
            else:
                g = _JPFONT.get(ch)
                if g:
                    gfb = framebuf.FrameBuffer(bytearray(g), 16, 16,
                                               framebuf.MONO_HLSB)
                    _jp_pal.pixel(1, 0, color)   # 前景色（黒も可）
                    self._fb.blit(gfb, cx, y, _JP_KEY, _jp_pal)  # 背景のみ透過
                else:
                    self.text("?", cx, y, color, scale=2)
            cx += 16

    def text(self, s, x, y, color, scale=2):
        """論理座標(x,y)に文字。scale=1はネイティブ、scale>=2は8pxグリフを
        fill_rectで拡大（ピクセル単位の座標変換が無いので従来より大幅に高速）。"""
        if scale == 1:
            self._fb.text(s, x, y, color)
            return
        n = len(s)
        tw = 8 * n
        tmp = bytearray(tw * 8 * 2)
        tfb = framebuf.FrameBuffer(tmp, tw, 8, framebuf.RGB565)
        tfb.fill(0x0000)
        tfb.text(s, 0, 0, color)
        fb = self._fb
        for cy in range(8):
            yy = y + cy * scale
            for cx in range(tw):
                if tfb.pixel(cx, cy):
                    fb.fill_rect(x + cx * scale, yy, scale, scale, color)

    def rect(self, x, y, w, h, color, fill=False):
        if fill:
            self._fb.fill_rect(x, y, w, h, color)
        else:
            self._fb.rect(x, y, w, h, color)

    def hline(self, x, y, w, color):
        self._fb.hline(x, y, w, color)

    # ---------- 転送 ----------
    def show(self):
        """論理(横向き)バッファを物理(縦向き)へ 90°回転(＋flipで180°)＋
        バイトスワップして転送用バッファへ書き、パネルへ一括転送する。"""
        _t0 = time.ticks_us()
        self._rotate_swap(self._lbuf, self._txbuf, 1 if self._flip180 else 0)
        _t1 = time.ticks_us()
        x0 = _PANEL_OFFSET
        x1 = _PANEL_OFFSET + _PW - 1
        y0 = 0
        y1 = _PH - 1
        self._write_cmd(_CASET)
        self._write_data(bytes([x0>>8, x0&0xFF, x1>>8, x1&0xFF]))
        self._write_cmd(_RASET)
        self._write_data(bytes([y0>>8, y0&0xFF, y1>>8, y1&0xFF]))
        self._write_cmd(_RAMWR)
        self._dc.value(1); self._cs_low()
        self._spi.write(self._txbuf)
        self._cs_high()
        if _SHOW_PERF:
            _t2 = time.ticks_us()
            print("[SHOW] 回転=%.1fms SPI=%.1fms" % (
                time.ticks_diff(_t1, _t0) / 1000,
                time.ticks_diff(_t2, _t1) / 1000))

    @staticmethod
    @micropython.viper
    def _rotate_swap(src: ptr16, dst: ptr16, flip: int):
        # 論理(横320x170) src → 物理(縦170x320) dst へ、90°回転（flipで更に180°）
        # しつつバイトスワップ。16bitワード単位＋インナーループは加算のみ。
        # 定数はローカルintに束ね、条件式での int() 変換(毎ループ)を排除して高速化。
        #   非flip: 物理(px,py) ← 論理(lx=W-1-py, ly=px)   → 行内 src は +W ずつ
        #   flip  : 物理(px,py) ← 論理(lx=py,   ly=PW-1-px) → 行内 src は -W ずつ
        pw = 170
        ph = 320
        w = 320
        py = 0
        while py < ph:
            didx = py * pw
            if flip != 0:
                sidx = (pw - 1) * w + py
                step = 0 - w
            else:
                sidx = (w - 1) - py
                step = w
            px = 0
            while px < pw:
                v = int(src[sidx])
                dst[didx] = ((v << 8) & 0xff00) | (v >> 8)
                sidx += step
                didx += 1
                px += 1
            py += 1

    @staticmethod
    def rgb(r, g, b):
        return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


class DisplayManager:
    def __init__(self):
        # SPIは高速化で描画レスポンス改善（8MHz→40MHz）。PCBのGNDベタ前提。
        # 表示に乱れ（ノイズ/化け）が出る場合は 32_000_000 / 24_000_000 へ下げる。
        spi = SPI(0, baudrate=40_000_000, sck=Pin(_SCK), mosi=Pin(_MOSI))
        # 論理(横向き320x170)バッファを1枚確保して2画面で共有（描画先）
        self._lbuf = bytearray(W * H * 2)
        self._fb   = framebuf.FrameBuffer(self._lbuf, W, H, framebuf.RGB565)
        # 物理(縦170x320)転送バッファも1枚確保して共有（回転+スワップ結果）
        self._txbuf = bytearray(_PW * _PH * 2)
        # lcd0でハードリセット(1回)、lcd1はリセットせずレジスタ設定のみ。
        self.lcd0 = LCD(spi, _CS0, _BL0, self._lbuf, self._fb, self._txbuf,
                        do_reset=True,  flip180=LCD0_FLIP180)
        self.lcd1 = LCD(spi, _CS1, _BL1, self._lbuf, self._fb, self._txbuf,
                        do_reset=False, flip180=LCD1_FLIP180)
        # lcd1の初期化がlcd0の設定に干渉するため、
        # 両画面初期化後にlcd0のレジスタを流し直して確定させる。
        time.sleep_ms(20)
        self.lcd0._init_regs()

    def show_all(self):
        self.lcd0.show()
        self.lcd1.show()

    def set_brightness(self, pct):
        self.lcd0.set_brightness(pct)
        self.lcd1.set_brightness(pct)
