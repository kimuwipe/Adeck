# mcp23017.py
# MCP23017 I2Cエキスパンダ ドライバ
# GPA0〜7: タクトスイッチ×8
# GPB0〜3: エンコーダPush×4

from machine import I2C
import time

# レジスタアドレス
_IODIRA   = 0x00   # ポートA方向（1=入力）
_IODIRB   = 0x01   # ポートB方向
_IPOLA    = 0x02   # ポートA極性反転
_IPOLB    = 0x03   # ポートB極性反転
_GPINTENA = 0x04   # ポートA割り込み有効
_GPINTENB = 0x05   # ポートB割り込み有効
_GPPUA    = 0x0C   # ポートA プルアップ（念のため有効化）
_GPPUB    = 0x0D   # ポートB プルアップ
_GPIOA    = 0x12   # ポートA 読み取り
_GPIOB    = 0x13   # ポートB 読み取り

class MCP23017:
    def __init__(self, i2c: I2C, addr: int = 0x20):
        self._i2c   = i2c
        self._addr  = addr
        self._prev_a = 0xFF   # 前回値（全HIGH=未押下）
        self._prev_b = 0xFF
        self._init()

    def _write(self, reg: int, val: int):
        self._i2c.writeto_mem(self._addr, reg, bytes([val]))

    def _read(self, reg: int) -> int:
        return self._i2c.readfrom_mem(self._addr, reg, 1)[0]

    def _init(self):
        # 全ピンを入力に設定
        self._write(_IODIRA, 0xFF)
        self._write(_IODIRB, 0xFF)
        # 極性反転（LOWで押下→HIGHで返す）
        self._write(_IPOLA, 0xFF)
        self._write(_IPOLB, 0xFF)
        # 内蔵プルアップも念のため有効（外付け抵抗が主体）
        self._write(_GPPUA, 0xFF)
        self._write(_GPPUB, 0xFF)

    def read_switches(self) -> list[bool]:
        """スイッチ×8の押下状態を返す（True=押下）"""
        val = self._read(_GPIOA)
        return [(val >> i) & 1 == 1 for i in range(8)]

    def read_pushes(self) -> list[bool]:
        """エンコーダPush×4の押下状態を返す（True=押下）"""
        val = self._read(_GPIOB)
        return [(val >> i) & 1 == 1 for i in range(4)]

    def get_switch_events(self) -> list[int]:
        """エッジ検出：押下したスイッチのインデックスリストを返す"""
        val = self._read(_GPIOA)
        events = []
        for i in range(8):
            curr = (val >> i) & 1
            prev = (self._prev_a >> i) & 1
            if curr == 1 and prev == 0:   # 立ち上がりエッジ（押下）
                events.append(i)
        self._prev_a = val
        return events

    def get_push_events(self) -> list[int]:
        """エッジ検出：押下したPushのインデックスリストを返す"""
        val = self._read(_GPIOB)
        events = []
        for i in range(4):
            curr = (val >> i) & 1
            prev = (self._prev_b >> i) & 1
            if curr == 1 and prev == 0:
                events.append(i)
        self._prev_b = val
        return events
