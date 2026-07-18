# test_pcb.py
# ===== PCB実装確認 ブリングアップ診断 =====
# 新しく組み立てたPCBの各サブシステムを1つずつ検査する。
# 実装ミス（ハンダブリッジ/イモハンダ/部品向き/未接続）の切り分け用。
#
# 使い方（Thonny）:
#   import test_pcb          … メニュー起動
#   test_pcb.i2c_scan()      … 個別に呼ぶことも可能
#   test_pcb.run()           … メニューを再表示
#
# 検査順の推奨: [1]I2Cスキャン → [2]LED → [3]SW → [4]ENC押込 → [5]ENC回転
#               → [6]LCD → [7]タッチ → [8]総合ライブ
# 各対話テストは Ctrl+C で中断できます。

from machine import I2C, Pin
import time
import gc

# ---- ピン定義（CLAUDE.md / 01_netlist_connection.md 準拠）----
I2C0_SDA, I2C0_SCL = 4, 5     # MCP23017 + LCD1タッチ
I2C1_SDA, I2C1_SCL = 6, 7     # LCD2タッチ
LED_PIN            = 28

# 遅延初期化するハードウェア（一度作ったら使い回す）
_i2c0 = None
_i2c1 = None
_mcp  = None
_enc  = None
_disp = None


def _get_i2c0():
    global _i2c0
    if _i2c0 is None:
        _i2c0 = I2C(0, sda=Pin(I2C0_SDA), scl=Pin(I2C0_SCL), freq=400_000)
    return _i2c0


def _get_i2c1():
    global _i2c1
    if _i2c1 is None:
        _i2c1 = I2C(1, sda=Pin(I2C1_SDA), scl=Pin(I2C1_SCL), freq=400_000)
    return _i2c1


def _get_mcp():
    global _mcp
    if _mcp is None:
        from mcp23017 import MCP23017
        _mcp = MCP23017(_get_i2c0(), addr=0x20)
    return _mcp


def _get_enc():
    global _enc
    if _enc is None:
        from encoder import EncoderManager
        _enc = EncoderManager()
    return _enc


def _get_disp():
    global _disp
    if _disp is None:
        gc.collect()
        from display import DisplayManager
        _disp = DisplayManager()
        _disp.set_brightness(80)
    return _disp


# ============================================================
# [1] I2C バススキャン（最重要・実装ミスをまず切り分け）
# ============================================================
def i2c_scan():
    print("\n===== [1] I2C バススキャン =====")
    # タッチIC(CST816)はLCDのRST(GP21・2画面共有)配下にあり、RSTが未初期化
    # （フローティング/Low）だと応答しない。先にハードリセットを解除してから
    # スキャンする（ブレッドボードで動いていたのは表示初期化でRSTを上げていたため）。
    try:
        rst = Pin(21, Pin.OUT)
        rst.value(0); time.sleep_ms(120)
        rst.value(1); time.sleep_ms(250)
        print("  (LCD/タッチ RST(GP21)を解除してからスキャン)")
    except Exception as e:
        print("  (RST制御スキップ: {})".format(e))
    buses = (
        ("I2C0 (GP4/5)", _get_i2c0, {0x20: "MCP23017", 0x15: "LCD1タッチ(CST816)"}),
        ("I2C1 (GP6/7)", _get_i2c1, {0x15: "LCD2タッチ(CST816)"}),
    )
    all_ok = True
    for name, getter, expected in buses:
        try:
            found = getter().scan()
        except Exception as e:
            all_ok = False
            print("  {}: スキャン失敗 {}".format(name, e))
            print("     → SDA/SCL のハンダ、GNDショート、プルアップ抵抗を確認")
            continue
        print("  {}: 検出 {}".format(name, [hex(a) for a in found]))
        for addr, label in expected.items():
            ok = addr in found
            if not ok:
                all_ok = False
            print("     {} {} {}{}".format(
                "OK " if ok else "NG ", hex(addr), label,
                "" if ok else "  ← 見つからない！"))
    print("  ※ LCD本体(ST7789)はSPI接続なのでI2Cには現れません")
    if not all_ok:
        print("  【ヒント】NGのアドレス:")
        print("   - 0x20 MCP: VDD/VSS/A0-A2(GND)/RESET(プルアップ)/SDA/SCL のハンダ確認")
        print("   - 0x15 タッチ: LCDモジュールのFPC接触、TP_SDA/TP_SCL 確認")
        print("   - 何も出ない: SDA-SCL間ブリッジ、プルアップ未実装、GND未接続を疑う")
    else:
        print("  ✓ 期待した全デバイスを検出")
    return all_ok


# ============================================================
# [2] デバッグLED (GP28)
# ============================================================
def led_test(n=6):
    print("\n===== [2] デバッグLED (GP28) =====")
    led = Pin(LED_PIN, Pin.OUT)
    print("  {}回点滅します。GP28のLEDが点滅すればOK".format(n))
    for _ in range(n):
        led.value(1); time.sleep_ms(200)
        led.value(0); time.sleep_ms(200)
    print("  完了（光らない → LED向き/330Ω抵抗/GP28ハンダを確認）")


# ============================================================
# [3] スイッチ SW1-8 (MCP23017 GPA0-7)
# ============================================================
def switches_test():
    print("\n===== [3] スイッチ SW1-8 (MCP GPA0-7) =====")
    try:
        mcp = _get_mcp()
    except Exception as e:
        print("  MCP初期化失敗 {} → まず [1] I2Cスキャンを確認".format(e))
        return
    seen = set()
    print("  各スイッチを1回ずつ押してください。Ctrl+Cで中断")
    try:
        while len(seen) < 8:
            for idx in mcp.get_switch_events():
                if idx not in seen:
                    seen.add(idx)
                    print("  OK SW{}  ({}/8)".format(idx + 1, len(seen)))
                else:
                    print("     SW{} (確認済)".format(idx + 1))
            time.sleep_ms(10)
        print("  ✓ 全スイッチOK")
    except KeyboardInterrupt:
        miss = [i + 1 for i in range(8) if i not in seen]
        print("\n  中断。未確認 SW: {}".format(miss if miss else "なし"))
        if miss:
            print("     → 該当SWのGPAxハンダ、10kΩプルアップ、SW実装を確認")


# ============================================================
# [4] エンコーダ押し込み ENC1-4 (MCP GPB0-3)
# ============================================================
def push_test():
    print("\n===== [4] エンコーダ Push (MCP GPB0-3) =====")
    try:
        mcp = _get_mcp()
    except Exception as e:
        print("  MCP初期化失敗 {} → [1] I2Cスキャンを確認".format(e))
        return
    seen = set()
    print("  各エンコーダを押し込んでください（4個）。Ctrl+Cで中断")
    try:
        while len(seen) < 4:
            for idx in mcp.get_push_events():
                if idx not in seen:
                    seen.add(idx)
                    print("  OK ENC{} push  ({}/4)".format(idx + 1, len(seen)))
            time.sleep_ms(10)
        print("  ✓ 全Push OK")
    except KeyboardInterrupt:
        miss = [i + 1 for i in range(4) if i not in seen]
        print("\n  中断。未確認 Push: {}".format(miss if miss else "なし"))
        if miss:
            print("     → GPBxハンダ、10kΩプルアップ、エンコーダSW端子を確認")


# ============================================================
# [5] エンコーダ回転 ENC1-4 (GP8-15 A/B相)
# ============================================================
def encoder_test():
    print("\n===== [5] エンコーダ回転 (GP8-15) =====")
    enc = _get_enc()
    counts = [[0, 0] for _ in range(4)]   # [CW, CCW]
    done = set()
    print("  各エンコーダを CW/CCW 両方向に数クリック回してください。Ctrl+Cで中断")
    try:
        while len(done) < 4:
            for i, rot in enumerate(enc.update_all()):
                if rot == 0:
                    continue
                if rot > 0:
                    counts[i][0] += 1
                else:
                    counts[i][1] += 1
                cw, ccw = counts[i]
                print("  ENC{}: CW={} CCW={}".format(i + 1, cw, ccw))
                if cw > 0 and ccw > 0 and i not in done:
                    done.add(i)
                    print("  ✓ ENC{} 両方向OK  ({}/4)".format(i + 1, len(done)))
            time.sleep_ms(2)
        print("  ✓ 全エンコーダOK")
    except KeyboardInterrupt:
        miss = [i + 1 for i in range(4) if i not in done]
        print("\n  中断。両方向未確認 ENC: {}".format(miss if miss else "なし"))
        if miss:
            print("     → A/B相(GPx)のハンダ、逆回転しかしない場合はA/B入れ替わり")


# ============================================================
# [6] LCD ×2 (SPI/CS/DC/RST/BL)
# ============================================================
def lcd_test():
    print("\n===== [6] LCD ×2 表示・バックライト =====")
    try:
        disp = _get_disp()
    except Exception as e:
        print("  LCD初期化失敗 {}".format(e))
        print("     → SPI(SCK18/MOSI19)/DC20/RST21/各CS(16,17)/電源 を確認")
        return

    colors = ((0xF800, "赤"), (0x07E0, "緑"), (0x001F, "青"), (0xFFFF, "白"))
    for lcd, tag, hdr in ((disp.lcd0, "LCD0(左)", 0x07FF), (disp.lcd1, "LCD1(右)", 0xF800)):
        print("  {} カラーバー表示...".format(tag))
        for col, _cn in colors:
            lcd.fill(col); lcd.show(); time.sleep_ms(350)
        lcd.fill(0x0000)
        lcd.rect(0, 0, 320, 20, hdr, fill=True)
        lcd.text("{} OK".format(tag), 10, 50, 0xFFFF)
        lcd.small_text("bring-up test", 10, 90, 0x7BEF)
        lcd.show()

    print("  バックライト個別テスト（各画面が独立して暗→明すればBL配線OK）")
    for lcd, tag in ((disp.lcd0, "LCD0"), (disp.lcd1, "LCD1")):
        print("   {} 消灯→点灯".format(tag))
        lcd.set_brightness(0);   time.sleep_ms(500)
        lcd.set_brightness(80);  time.sleep_ms(300)
    print("  ✓ 両画面に色/文字が出て各BLが効けばOK")
    print("     色化けする → バイトスワップ/CS取り違え、片方だけ映らない → 該当CS/BL")


# ============================================================
# [7] タッチ ×2 (CST816 / I2C0・I2C1)
# ============================================================
def touch_test():
    print("\n===== [7] タッチパネル ×2 =====")
    try:
        from touch import TouchManager, GESTURE_NONE
    except Exception as e:
        print("  touch読込失敗 {}".format(e)); return
    tm = TouchManager(_get_i2c0(), _get_i2c1())
    seen = set()
    print("  各画面をタップ/スワイプしてください。Ctrl+Cで中断")
    try:
        while len(seen) < 2:
            g0, g1 = tm.update_all()
            if g0 != GESTURE_NONE:
                print("  LCD0 タッチ: {}".format(g0)); seen.add(0)
            if g1 != GESTURE_NONE:
                print("  LCD1 タッチ: {}".format(g1)); seen.add(1)
            time.sleep_ms(10)
        print("  ✓ 両画面タッチOK")
    except KeyboardInterrupt:
        miss = [i for i in (0, 1) if i not in seen]
        print("\n  中断。未確認 タッチ: {}".format(
            ["LCD{}".format(i) for i in miss] if miss else "なし"))
        if miss:
            print("     → 該当画面の TP_SDA/TP_SCL(I2C)、FPC接触を確認")


# ============================================================
# [w] タッチ連続スキャン（差し替え/リシート中にリアルタイム監視）
# ============================================================
def watch_touch():
    print("\n===== [w] タッチIC 連続スキャン監視 =====")
    print("  I2C0/I2C1 を連続スキャン。モジュール差し替え・FPCリシート・画面タッチ")
    print("  をしながら 0x15 が出るか監視します。Ctrl+Cで終了")
    # RST(GP21)を一度解除
    try:
        rst = Pin(21, Pin.OUT)
        rst.value(0); time.sleep_ms(120); rst.value(1); time.sleep_ms(200)
    except Exception:
        pass
    i2c0, i2c1 = _get_i2c0(), _get_i2c1()
    prev = None
    try:
        while True:
            try:
                f0 = i2c0.scan()
            except Exception:
                f0 = []
            try:
                f1 = i2c1.scan()
            except Exception:
                f1 = []
            state = (0x15 in f0, 0x15 in f1)
            if state != prev:
                print("  I2C0 touch:{}  I2C1 touch:{}   (I2C0={} I2C1={})".format(
                    "●OK" if state[0] else "―",
                    "●OK" if state[1] else "―",
                    [hex(a) for a in f0], [hex(a) for a in f1]))
                prev = state
            time.sleep_ms(300)
    except KeyboardInterrupt:
        print("\n  終了")


# ============================================================
# [L] I2Cライン電気チェック（GPIO直読みで断線/固着/ショートを判定）
# ============================================================
def line_check():
    print("\n===== [L] I2C ライン電気チェック =====")
    print("  SDA/SCL を入力(内部プルアップ)で読む。idle は 1(HIGH) が正常。")
    print("  0(LOW)固着なら GND ショート/ハンダブリッジ/バス占有を疑う。\n")
    for name, sda_p, scl_p in (("I2C0(GP4/5)", 4, 5), ("I2C1(GP6/7)", 6, 7)):
        sda = Pin(sda_p, Pin.IN, Pin.PULL_UP)
        scl = Pin(scl_p, Pin.IN, Pin.PULL_UP)
        time.sleep_ms(3)
        s, c = sda.value(), scl.value()
        tag = "OK (idle high)" if (s and c) else "← LOW固着あり！"
        print("  {}: SDA(GP{})={}  SCL(GP{})={}   {}".format(
            name, sda_p, s, scl_p, c, tag))

    # I2C1 の SDA-SCL 間ショート簡易判定：GP6をLOW駆動してGP7を読む
    try:
        drv = Pin(6, Pin.OUT); drv.value(0)
        rd = Pin(7, Pin.IN, Pin.PULL_UP)
        time.sleep_ms(3)
        shorted = (rd.value() == 0)
        Pin(6, Pin.IN, Pin.PULL_UP)   # 入力に戻す
        print("  I2C1 SDA-SCL間ショート: {}".format(
            "あり！ GP6↔GP7 がブリッジ" if shorted else "なし"))
    except Exception as e:
        print("  ショート判定スキップ: {}".format(e))

    print("\n  【読み方】")
    print("   - I2C0 は 1/1、I2C1 が 0/0 等 → GP6/GP7 が GND へ固着（ブリッジ/短絡）")
    print("   - I2C1 も 1/1 なのにスキャンで 0x15 が出ない → 線は生きているが")
    print("     LCD2 の TP_SDA/TP_SCL が未達（モジュール側コネクタ/イモハンダ/断線）")
    print("   - GP4/5(動作OK)と GP6/7 の値・導通を比較するのが早い")


# ============================================================
# [b] バックライト個別診断（GP26=LCD0 / GP27=LCD1 を静的に固定）
# ============================================================
def bl_test():
    print("\n===== [b] バックライト BL 診断 =====")
    print("  BLは負論理（LOW=点灯 / HIGH=消灯）。テスターで各点を測る用に静的固定します。")
    print("  測定点: ① Pico の GP26/GP27 パッド  ② 各LCDモジュールの BL 端子")
    bl0 = Pin(26, Pin.OUT)   # LCD0 BL
    bl1 = Pin(27, Pin.OUT)   # LCD1 BL
    steps = (
        ("両方 LOW  → 負論理なら両画面『点灯（最も明るい）』", 0, 0),
        ("両方 HIGH → 負論理なら両画面『消灯』",             1, 1),
        ("GP26=HIGH / GP27=LOW (LCD0消灯 / LCD1点灯)",       1, 0),
        ("GP26=LOW  / GP27=HIGH (LCD0点灯 / LCD1消灯)",       0, 1),
    )
    try:
        for label, v0, v1 in steps:
            bl0.value(v0); bl1.value(v1)
            print("\n  {}".format(label))
            print("    GP26={}  GP27={}".format(v0, v1))
            print("    → GP26パッドとLCD0-BL端子の電圧を測定（HIGH≈3.3V / LOW≈0V）。Enterで次へ")
            input()
    except KeyboardInterrupt:
        pass
    # 終了時は両方点灯（LOW）に戻す
    bl0.value(0); bl1.value(0)
    print("\n  完了（BLは点灯状態に戻しました）")
    print("  判定の目安:")
    print("   - GP26パッドが HIGH/LOW で 3.3/0V に振れ、LCD0-BL も追従 → GP26系は正常")
    print("     （それでも暗い→モジュール側BL LED/抵抗、または輝度設定を確認）")
    print("   - GP26パッドは振れるが LCD0-BL が 0V のまま → GP26↔LCD0BL 間が断線")
    print("     （BLピンのイモハンダ/未接続/コネクタ、延長ケーブルのBL線を確認）")
    print("   - GP26パッド自体が振れない(常時0V) → GP26 が GND へショート/ピン損傷")
    print("   - GP26パッドが常時3.3V → GP26 が 3V3 へショート")


# ============================================================
# [8] 総合ライブモニタ（本番と同じ入力を一括監視）
# ============================================================
def live_monitor():
    print("\n===== [8] 総合ライブモニタ =====")
    mcp = _get_mcp()
    enc = _get_enc()
    led = Pin(LED_PIN, Pin.OUT)
    print("  スイッチ/エンコーダ回転/押込を自由に操作。押すとLED点灯。Ctrl+Cで終了")
    try:
        while True:
            for idx in mcp.get_switch_events():
                print("  SW{}".format(idx + 1)); led.value(1)
            for idx in mcp.get_push_events():
                print("  ENC{} push".format(idx + 1)); led.value(1)
            for i, rot in enumerate(enc.update_all()):
                if rot != 0:
                    print("  ENC{} {}".format(i + 1, "CW" if rot > 0 else "CCW"))
            led.value(0)
            time.sleep_ms(5)
    except KeyboardInterrupt:
        print("\n  終了")


# ============================================================
# メニュー
# ============================================================
_MENU = (
    ("1", "I2Cスキャン（まず最初に）", i2c_scan),
    ("2", "デバッグLED (GP28)",        led_test),
    ("3", "スイッチ SW1-8",            switches_test),
    ("4", "エンコーダ 押し込み",       push_test),
    ("5", "エンコーダ 回転",           encoder_test),
    ("6", "LCD ×2 表示/BL",            lcd_test),
    ("7", "タッチ ×2",                 touch_test),
    ("8", "総合ライブモニタ",          live_monitor),
    ("b", "バックライト BL 個別診断",  bl_test),
    ("l", "I2Cライン電気チェック",     line_check),
    ("w", "タッチ連続スキャン監視",    watch_touch),
)


def run():
    while True:
        print("\n========= PCB 実装確認メニュー =========")
        for key, label, _fn in _MENU:
            print("  [{}] {}".format(key, label))
        print("  [a] 自動チェック（I2C+LED）")
        print("  [q] 終了")
        try:
            c = input("選択> ").strip().lower()
        except KeyboardInterrupt:
            print("\n終了"); return
        if c == "q":
            print("終了"); return
        if c == "a":
            i2c_scan(); led_test(); continue
        for key, _label, fn in _MENU:
            if c == key:
                try:
                    fn()
                except Exception as e:
                    print("  テスト中に例外: {}".format(e))
                break
        else:
            print("  不明な選択: {}".format(c))


print("PCB診断ツール読込。 test_pcb.run() でメニュー、または個別関数を実行")
run()
