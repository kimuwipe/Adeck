# 自作StreamDeck

Raspberry Pi Pico 2（RP2350）ベースの自作マクロパッド。
2画面タッチLCD、8個の物理スイッチ、4個のロータリーエンコーダを備え、
PC側の常駐アプリと連携して音量・マイク・天気・起動アプリを表示し、
キー送信やアプリ起動を行う。Elgato Stream Deck + にインスパイアされた形状。

## 特徴

- **2画面カラーLCD**（横向き・5ページ・独立タッチスワイプ）
- **日本語表示対応**（プロファイル名・プリセット名・天気・曜日を日本語で表示。使用文字だけの
  16×16ビットマップフォントを書き込み時に自動生成するため、任意の日本語名も文字化けしない）
- **日付/時刻をLCDに表示**（1ページ目・曜日は漢字）
- **物理スイッチ×8 / ロータリーエンコーダ×4**（プロファイル別の割り当て、回転・プッシュ）
- **プロファイル**（汎用・SolidWorks・音声・開発・AI … 最大8・追加/削除/リネーム/インポート可）
- **プリセット**（よく使うアクションを名前付きで保存・最大32。割り当てるとボタン/LCDに
  プリセット名を表示）
- **多彩なアクション**（キー送信・ホットキー記録・アプリ/ショートカット起動・URL・
  コマンド実行・テキスト入力）
- **PC連携**（音量・マイク・天気・起動アプリ・日付/時刻の表示、キー送信）
- **PC側統合UI**（トレイ常駐・Windows自動起動・前面アプリ連動の自動プロファイル切替・
  書き込み不要のライブ反映）

## リポジトリ構成

```
streamdeck/               … Pico側 MicroPythonコード
├── main.py               … メインループ
├── display.py            … LCD制御（ST7789V2・日本語描画 text_jp）
├── display_pages.py      … LCD表示内容（5ページ・日付/時刻・日本語ラベル）
├── jpfont.py             … 日本語ビットマップフォント（16×16・PC書込時に自動生成）
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
├── agent.py              … 常駐エージェント（音量/マイク/天気/日時取得・キー送信）
├── configurator.py       … 設定GUI（プロファイル・プリセット・ライブ反映・Pico書込）
├── fontgen.py            … 使用文字だけの日本語フォントを自動生成
├── autostart.py          … Windows自動起動
└── requirements.txt

streamdeck_pcb/           … KiCad PCB設計
├── 00_README_KiCad手順.md … KiCad運用手順
├── streamdeck_symbols.kicad_sym
├── 01_netlist_connection.md
├── 02_BOM.md
└── 03_schematic_diagram.svg

streamdeck_case/          … Fusion 360 筐体設計
└── 筐体設計仕様.md
```

> ビルド成果物（`StreamDeckController.exe` / `dist/` / `*.spec` 等）と端末別の
> `streamdeck_config.json` は `.gitignore` 済み。配布は GitHub Releases。

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

## 設定（プロファイル・プリセット・反映）

- 設定アプリのグリッドでスイッチ/エンコーダを選び、右パレットからアクションを割り当てる。
  ホットキーは「⌨ 記録」で実際のキーを押して登録できる。
- よく使うアクションは「＋プリセット保存」で名前付き保存（最大32）。プリセットを
  スイッチへ割り当てると、設定アプリのボタンとLCDにその名前（例「戻る」）が表示される。
  手動でアクションを変えると名前ラベルは自動でクリアされる。
- **ライブ反映**：書き込み不要でアクション設定を即時反映（デバッグ向け）。
- **Picoに書き込む**：`config.py` と、その設定で実際に使う文字だけの日本語フォント
  `jpfont.py` を生成して Pico に書き込む（再起動で確定）。これにより任意の日本語名も
  文字化けせず表示できる。※フォントは書き込み時に確定するため、新しい日本語名を
  追加したら再度「Picoに書き込む」＋再起動が必要（ライブ反映はフォント非対象）。

## 開発の経緯

このプロジェクトは以下の段階を経て完成した:

1. ブレッドボードで全機能の実機デバッグ（特にディスプレイ制御を長時間攻略）
2. 統合テスト（PC連携含む全機能動作確認）
3. KiCadでPCB設計（基板3枚構成）
4. Fusion 360で筐体設計（Stream Deck +風）
5. JLCPCBでPCB・3Dプリント発注
6. PC側UIの統合・トレイ常駐・自動起動実装
7. 設定UIのElgato風グリッド化、プリセット、日本語表示・日付/時刻、フォント自動生成の追加

技術的なハマりどころ（ST7789V2のソフト回転、バイトスワップ、2画面RST共有、
日本語グリフのblit（透明キーの扱い）、COMのMTA初期化など）は `CLAUDE.md` に詳しく
記録されている。

## ライセンス

個人プロジェクト。
