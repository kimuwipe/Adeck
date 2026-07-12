# CLAUDE.md — 自作StreamDeck プロジェクト

このファイルは Claude Code がプロジェクトの文脈を理解するための資料です。
過去の開発で得た知見・設計判断・ハマりどころを集約しています。

## プロジェクト概要

Raspberry Pi Pico 2（RP2350）ベースの自作StreamDeck。
Elgato Stream Deck + 風の、2画面タッチLCD＋物理スイッチ＋ロータリーエンコーダを持つ
マクロパッド。PC側の常駐アプリと連携し、音量・マイク・天気・起動アプリを表示し、
キー送信やアプリ起動を行う。

**現在の状態**: 実機で全機能動作確認済み。PCB化・3Dプリント筐体を発注済み。
PC側UIを統合＋トレイ常駐＋自動起動まで実装済み。

## ハードウェア構成

- **マイコン**: Raspberry Pi Pico 2（RP2350、MicroPython v1.28.0）
- **ディスプレイ**: Waveshare 1.9inch Touch LCD ×2
  - ドライバIC: ST7789V2、タッチIC: CST816
  - パネル: 170×320（横向き320×170で使用）
- **入力**: タクトスイッチ×8、EC11プッシュ付きエンコーダ×4
- **IOエキスパンダ**: MCP23017（I2C 0x20）
- **USB-C**: 秋月 AE-USB2.0-TYPE-C-5077CR

### ピンアサイン（確定・実機検証済み）

| GP | 機能 |
|----|------|
| GP4/5 | I2C0 SDA/SCL（MCP23017 + LCD①タッチ） |
| GP6/7 | I2C1 SDA/SCL（LCD②タッチ） |
| GP8-15 | エンコーダ1-4 の A/B相 |
| GP16 | LCD② CS |
| GP17 | LCD① CS |
| GP18 | SPI SCK（共通） |
| GP19 | SPI MOSI（共通） |
| GP20 | LCD DC（共通） |
| GP21 | LCD RST（共通・2画面共有） |
| GP26 | LCD① バックライト（負論理） |
| GP27 | LCD② バックライト（負論理） |
| GP28 | デバッグLED（330Ω経由） |

MCP23017: GPA0-7=スイッチ8個、GPB0-3=エンコーダPush4個、A0/A1/A2→GND

## Pico側ファイル構成

- `main.py` — メインループ。プロファイル管理、入力処理、描画、シリアル通信
- `config.py` — キー割り当て等の設定
- `display.py` — LCD制御（ST7789V2、ソフト回転、バイトスワップ）
- `display_pages.py` — 5ページのLCD表示内容
- `touch.py` — タッチパネル（CST816）ジェスチャー検出
- `encoder.py` — ロータリーエンコーダ読み取り
- `mcp23017.py` — IOエキスパンダ制御
- `debug_led.py` — デバッグLED
- `hid.py` — HIDスタブ（MicroPython v1.28に usb.device 無いため）
- `test_*.py` — 各機能の単体テスト

## ★ディスプレイの勝ちパターン（最重要・再発防止）

ST7789V2の制御は情報が少なく、長時間デバッグして確定した方式。**変更時は要注意**。

- **物理**: 縦向き170×320、MADCTL=0x00、INVON（色反転）、列オフセット35（(240-170)/2）
- **論理**: 横向き320×170をソフト回転（px=ly, py=W-1-lx）で実現
- **色**: framebufとST7789V2のエンディアン差でバイトスワップ必須
  - **転送専用バッファ(_txbuf)へviperでスワップコピー**する方式
  - 元バッファを往復スワップすると色がずれる（往復NG）
- **バックライト**: 負論理（duty反転、LOWで点灯）
- **バッファ**: 物理縦170×320を1枚＋転送用1枚、2画面共有（計212KB）
- **2画面RST共有問題**: lcd0でハードリセット1回、lcd1はdo_reset=Falseで
  レジスタ設定のみ。両画面初期化後にlcd0._init_regs()で確定
  （lcd1初期化がlcd0に干渉するため）

## その他の重要な設計判断

- **HID方式**: MicroPython v1.28に usb.device 無し→hid.pyスタブ化。
  キー送信はPC側agent.pyのpyautoguiに移譲。
- **serial_recv**: `sys.stdin.readline()` はブロッキングするため、
  `select.poll()` でノンブロッキング化（これをしないとPC未接続時に停止）。
- **共有バッファ描画**: 2画面が同じバッファを共有するため、
  「draw_page(lcd0)→show()→draw_page(lcd1)→show()」と1画面ずつ処理する。
- **タッチ操作**: 画面タップ＝次プロファイル(プリセット)へ切替、スワイプ左右＝ページ送り。
  各ページ右上に現在プロファイルのバッジを表示（display_pages._profile_badge、draw_pageで全ページ共通描画）。
  タップ領域を座標で限定しないのは、タッチ座標のスケール/縦軸向きが実機依存で未確定なため
  （全画面タップにして座標マッピング非依存で確実動作にした）。8x8フォントはASCIIのみ→
  日本語プロファイル名は 'P{n}' にフォールバック表示。

## PC側ファイル構成（streamdeck_configurator/）

- `streamdeck_app.py` — **統合UIメインアプリ**（推奨エントリポイント・CustomTkinter）
  - agent（常駐通信）とconfigurator（設定）を1ウィンドウに統合
  - 上部に接続状態・音量/マイク/天気/プロファイルを常時表示
  - タブUI: 設定（configurator.EditorFrame を埋め込み）/オプション（自動起動・
    前面アプリ自動切替＋ルール編集ダイアログ）/ログ
  - cfg は load_config() で1つ用意し editor/agent で共有参照
  - システムトレイ常駐（pystray）、Windows自動起動対応
- `agent.py` — 常駐エージェント機能（音量/マイク/天気/アプリ取得、キー送信）
- `configurator.py` — 設定GUI（CustomTkinter・Elgato風グリッドUI）。
  スイッチ2×4／エンコーダ4個をボタングリッド表示、クリックで選択→下パネルで設定、
  右パレットからアクション割り当て。統合UIからは別プロセスで起動（CTk/tk root二重化回避）。
  キー記録（⌨ボタンで任意コンビを捕捉→"KEY:ctrl c"）、プリセット保存/管理（最大32・
  右パレットに表示）、アプリは.lnk/.url ショートカットも登録可（agentはos.startfile起動）。
  プロファイルは可変数（追加/削除/リネーム、最大MAX_PROFILES=8）。profiles/switches/encoders
  を同時に増減し、config_to_py/expand_maps は len(cfg["profiles"]) で動的生成。
  display側 PROFILE_COLORS[pi] は % len でmodulo化（4色を循環）。
  グリッドUIは EditorFrame(ctk.CTkFrame) として切り出し済み（統合UIのタブに埋め込み／
  単体は App(ctk.CTk) ラッパーで起動）。cfg入出力は load_config/save_config/normalize_config
- `autostart.py` — Windows自動起動の登録/解除
- `requirements.txt` — 依存: pyserial, pycaw, psutil, comtypes, pyautogui,
  pystray, Pillow, customtkinter（グリッドUI）, pyperclip（任意・日本語TEXT入力）

### PC側の重要な知見

- **Python 3.12必須**（3.7では型注釈エラー）。各ファイル冒頭に
  `from __future__ import annotations` を付けている。
- **pycaw API**: スピーカーは `device.EndpointVolume`（新API）、
  マイクは `device.Activate`（旧API）で混在が正解。
- **Picoポート検出**: VID=0x2E8A優先＋"USB シリアル"名対応。
- **cp932エラー対策**: requirements.txtは英語コメントのみ。
- **Thonnyとの競合**: agent実行中はThonnyでCOMポートを開けない（排他）。

## PCB（streamdeck_pcb/）

- KiCad 7.x で設計。基板3枚構成（メイン100×100、スイッチ基板、エンコーダ基板）。
- `streamdeck_symbols.kicad_sym` — 自作シンボル5種（KiCad 7形式、各propertyに(id N)必須）
- 電源: Pico 2オンボード3V3レギュレータで足りる（総負荷約160-220mA）。
  C5(100μF)を3V3バルクとして追加。
- I2Cプルアップ: Waveshare LCDが内部10kΩ内蔵。メイン4.7kΩと合成3.2kで許容範囲。
- **GNDベタ必須**: ブレッドボードのGND接触抵抗20Ωが表示ちらつきの原因だった。
  PCBのGNDベタで解決する前提。
- 発注: JLCPCB（PCB + 3Dプリント筐体を1社でまとめる）。

## 筐体（streamdeck_case/）

- Fusion 360で設計。Stream Deck +風の2段角度くさび形。
- 傾斜面65°（SW→LCD）、手前緩い面20°（ENC）。
- 外形: 幅約110mm（LCD部120mm）、奥行き161mm、高さ145mm。
- メイン基板は底に水平配置（土台）、LCDだけ延長ケーブルで傾斜面へ。
- 開口: SW穴20×20角×8、LCD窓55×30×2、ENC穴φ17×4。
- 素材: レジン（SLA）でJLC3DP発注。
- 底面開口＋底板ネジ止めで基板を入れる構造。

## 既知の課題 / 今後のTODO

- [ ] PCB実装後、GNDベタでちらつきが解消するか確認
- [ ] LCD実物の外形・表示エリアを実測して筐体窓を微調整
- [x] PC側: ボタンにアクション追加（URL開く/コマンド実行/テキスト入力）
      → プレフィックス方式 URL:/CMD:/TEXT: で実装。agent.send_key が分岐処理、
        configurator で入力欄から設定（Pico側は無改造で action 文字列を透過転送）
- [x] PC側: アプリ連動の自動プロファイル切替（前面アプリで自動切替）
      → streamdeck_app の AgentThread が前面アプリを1秒毎に監視(ctypes+psutil)、
        auto_profile.rules で一致したら set_profile メッセージをPicoへ送信。
        状態タブのチェックボックスでON/OFF、ルールはJSON編集。
- [x] PC側: 設定のライブ反映（書き込みなしで即反映）
      → configurator.expand_maps でランタイム形式に展開し {type:config} を送信。
        Pico は apply_live_config で main globals と config モジュール属性の両方を
        差し替え（display_pagesがconfig直参照のため）。config_ack を返す。
- [ ] +3.3VA/+3.3Vのメイン基板との合流確認

## 開発環境メモ

- ユーザーは豊田市在住の半導体CVDエンジニア（SolidWorks使用、材料工学）
- 実機デバッグを厭わない実践派
- KiCad 7.x、Fusion 360、Anaconda(Python 3.12)、Thonny使用
- 天気APIは Open-Meteo（豊田市 lat=35.0826, lon=137.1564）
