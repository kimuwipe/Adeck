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
    def __init__(self, spi, cs_pin, bl_pin, phys_buf, phys_fb, tx_buf, do_reset=True,
                 flip180=False):
        self._spi = spi
        self._flip180 = flip180
        self._cs  = Pin(cs_pin, Pin.OUT, value=1)
        self._dc  = Pin(_DC,  Pin.OUT)
        self._rst = Pin(_RST, Pin.OUT)
        self._bl  = PWM(Pin(bl_pin))
        self._bl.freq(1000)
        self.set_brightness(80)
        # 物理縦向きフレームバッファ（2画面で共有）
        self._buf = phys_buf
        self._fb  = phys_fb
        self._txbuf = tx_buf   # 転送用バッファ（スワップ済みコピー先・共有）
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

    # ---------- 論理→物理 座標変換 ----------
    # 論理(lx,ly) 横向き320x170 → 物理(px,py) 縦向き170x320
    #   px = ly
    #   py = (W-1) - lx
    def _map(self, lx, ly):
        if self._flip180:
            # 180°回転（点対称）：LCDを上下逆に取り付けた場合の補正
            return (_PW - 1) - ly, lx
        return ly, (W - 1) - lx

    # ---------- 描画API（論理座標で受ける）----------
    def fill(self, color):
        self._fb.fill(color)

    def text(self, s, x, y, color, scale=2):
        """論理座標(x,y)に文字。物理バッファへ回転して描く。"""
        # 8x8フォントを一時バッファに描き、ピクセルを回転転写
        n = len(s)
        tw = 8 * n
        tmp = bytearray(tw * 8 * 2)
        tfb = framebuf.FrameBuffer(tmp, tw, 8, framebuf.RGB565)
        tfb.fill(0x0000)
        tfb.text(s, 0, 0, color)
        for cy in range(8):
            for cx in range(tw):
                if tfb.pixel(cx, cy):
                    # 論理座標
                    lx = x + cx * scale
                    ly = y + cy * scale
                    for dx in range(scale):
                        for dy in range(scale):
                            px, py = self._map(lx + dx, ly + dy)
                            if 0 <= px < _PW and 0 <= py < _PH:
                                self._fb.pixel(px, py, color)

    def small_text(self, s, x, y, color):
        n = len(s)
        tw = 8 * n
        tmp = bytearray(tw * 8 * 2)
        tfb = framebuf.FrameBuffer(tmp, tw, 8, framebuf.RGB565)
        tfb.fill(0x0000)
        tfb.text(s, 0, 0, color)
        for cy in range(8):
            for cx in range(tw):
                if tfb.pixel(cx, cy):
                    px, py = self._map(x + cx, y + cy)
                    if 0 <= px < _PW and 0 <= py < _PH:
                        self._fb.pixel(px, py, color)

    def rect(self, x, y, w, h, color, fill=False):
        if fill:
            # 論理矩形 → 物理では回転した矩形。1pxずつ変換すると遅いので
            # 物理座標系での矩形範囲を計算して fill_rect する
            # 論理(x,y)-(x+w,y+h) の4隅を変換
            px0, py0 = self._map(x, y)
            px1, py1 = self._map(x + w - 1, y + h - 1)
            rx = min(px0, px1); ry = min(py0, py1)
            rw = abs(px1 - px0) + 1; rh = abs(py1 - py0) + 1
            self._fb.fill_rect(rx, ry, rw, rh, color)
        else:
            # 枠線は4辺を個別に
            self.rect(x, y, w, 1, color, True)
            self.rect(x, y + h - 1, w, 1, color, True)
            self.rect(x, y, 1, h, color, True)
            self.rect(x + w - 1, y, 1, h, color, True)

    def hline(self, x, y, w, color):
        self.rect(x, y, w, 1, color, True)

    # ---------- 転送 ----------
    def show(self):
        """物理縦バッファをパネルへ一括転送（バイトスワップ込み）。
        元バッファは変更せず、転送用バッファへスワップコピーして送る。"""
        self._swap_copy(self._buf, self._txbuf, len(self._buf))
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

    @staticmethod
    @micropython.viper
    def _swap_copy(src: ptr8, dst: ptr8, n: int):
        # srcの16bitワードをバイトスワップしながらdstへコピー（元は不変）
        i = 0
        while i < n:
            dst[i]     = src[i + 1]
            dst[i + 1] = src[i]
            i += 2

    @staticmethod
    def rgb(r, g, b):
        return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


class DisplayManager:
    def __init__(self):
        # SPIは高速化で描画レスポンス改善（8MHz→40MHz）。PCBのGNDベタ前提。
        # 表示に乱れ（ノイズ/化け）が出る場合は 32_000_000 / 24_000_000 へ下げる。
        spi = SPI(0, baudrate=40_000_000, sck=Pin(_SCK), mosi=Pin(_MOSI))
        # 物理縦バッファを1枚だけ確保して2画面で共有
        self._buf = bytearray(_PW * _PH * 2)
        self._fb  = framebuf.FrameBuffer(self._buf, _PW, _PH, framebuf.RGB565)
        # 転送用バッファ（スワップ済みコピー先）も1枚確保して共有
        self._txbuf = bytearray(_PW * _PH * 2)
        # lcd0でハードリセット(1回)、lcd1はリセットせずレジスタ設定のみ。
        self.lcd0 = LCD(spi, _CS0, _BL0, self._buf, self._fb, self._txbuf,
                        do_reset=True,  flip180=LCD0_FLIP180)
        self.lcd1 = LCD(spi, _CS1, _BL1, self._buf, self._fb, self._txbuf,
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
