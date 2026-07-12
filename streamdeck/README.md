# 自作StreamDeck

Raspberry Pi Pico 2（RP2350）ベースの自作マクロパッド。
2画面タッチLCD、8個の物理スイッチ、4個のロータリーエンコーダを備え、
PC側の常駐アプリと連携して音量・マイク・天気・起動アプリを表示し、
キー送信やアプリ起動を行う。Elgato Stream Deck + にインスパイアされた形状。

## 特徴

- **2画面カラーLCD**（横向き・5ページ・独立タッチスワイプ）
- **物理スイッチ×8**（プロファイル別のキー割り当て）
- **ロータリーエンコーダ×4**（回転・プッシュ）
- **4プロファイル**（汎用・SolidWorks・音声・開発）
- **PC連携**（音量・マイク・天気・起動アプリ表示、キー送信）
- **PC側統合UI**（トレイ常駐・Windows自動起動対応）

## リポジトリ構成

```
streamdeck/               … Pico側 MicroPythonコード
├── main.py               … メインループ
├── display.py            … LCD制御（ST7789V2）
├── display_pages.py      … LCD表示内容（5ページ）
├── touch.py              … タッチジェスチャー
├── encoder.py            … エンコーダ読み取り
├── mcp23017.py           … IOエキスパンダ
├── debug_led.py          … デバッグLED
├── hid.py                … HIDスタブ
├── config.py             … 設定
├── test_*.py             … 各機能の単体テスト
├── CLAUDE.md             … Claude Code用 文脈ファイル
└── README.md             … このファイル

streamdeck_configurator/  … PC側 Pythonアプリ
├── streamdeck_app.py     … 統合UIメインアプリ（推奨）
├── agent.py              … 常駐エージェント
├── configurator.py       … 設定GUI
├── autostart.py          … Windows自動起動
└── requirements.txt

streamdeck_pcb/           … KiCad PCB設計
├── streamdeck_symbols.kicad_sym
├── 01_netlist_connection.md
├── 02_BOM.md
└── 03_schematic_diagram.svg

streamdeck_case/          … Fusion 360 筐体設計
└── 筐体設計仕様.md
```

## ハードウェア

| 部品 | 型番 |
|------|------|
| マイコン | Raspberry Pi Pico 2（RP2350） |
| ディスプレイ | Waveshare 1.9inch Touch LCD ×2（ST7789V2 + CST816） |
| IOエキスパンダ | MCP23017 |
| スイッチ | タクトスイッチ ×8 |
| エンコーダ | EC11 プッシュ付き ×4 |
| USB-C | 秋月 AE-USB2.0-TYPE-C-5077CR |

詳細なピンアサインは `CLAUDE.md` または `streamdeck_pcb/01_netlist_connection.md` を参照。

## セットアップ

### Pico側

1. MicroPython v1.28.0 を Pico 2 に書き込む
2. `streamdeck/` 内の .py ファイルを Pico にコピー
3. `main.py` が自動起動する

### PC側

```bash
cd streamdeck_configurator
pip install -r requirements.txt
python streamdeck_app.py
```

- **Windows専用**（pycaw, pyautogui使用）
- **Python 3.12推奨**
- Thonnyは閉じておくこと（COMポート競合）

## 使い方

1. PicoをUSBでPCに接続
2. `python streamdeck_app.py` を起動
3. 自動でPicoに接続、音量・天気などがLCDに表示される
4. スイッチ・エンコーダでキー送信、タッチでページ切り替え
5. ×ボタンでトレイに最小化（常駐継続）

## 開発の経緯

このプロジェクトは以下の段階を経て完成した:

1. ブレッドボードで全機能の実機デバッグ（特にディスプレイ制御を長時間攻略）
2. 統合テスト（PC連携含む全機能動作確認）
3. KiCadでPCB設計（基板3枚構成）
4. Fusion 360で筐体設計（Stream Deck +風）
5. JLCPCBでPCB・3Dプリント発注
6. PC側UIの統合・トレイ常駐・自動起動実装

技術的なハマりどころ（ST7789V2のソフト回転、バイトスワップ、
2画面RST共有など）は `CLAUDE.md` に詳しく記録されている。

## ライセンス

個人プロジェクト。
