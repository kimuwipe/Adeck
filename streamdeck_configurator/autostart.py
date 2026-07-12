# autostart.py
# Windows スタートアップへの自動起動 登録/解除
#
# 方式: スタートアップフォルダに .bat を置く（レジストリを触らない安全な方法）
#   %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\
#
# .bat は pythonw.exe で streamdeck_app.py を起動する（コンソール非表示）

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "StreamDeckController"
BAT_NAME = f"{APP_NAME}.bat"


def _startup_dir() -> Path:
    """Windowsスタートアップフォルダのパスを返す"""
    appdata = os.environ.get("APPDATA", "")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" \
        / "Programs" / "Startup"


def _bat_path() -> Path:
    return _startup_dir() / BAT_NAME


def is_enabled() -> bool:
    """自動起動が登録済みか"""
    return _bat_path().exists()


def enable() -> bool:
    """自動起動を登録する。成功でTrue"""
    try:
        startup = _startup_dir()
        startup.mkdir(parents=True, exist_ok=True)

        if getattr(sys, "frozen", False):
            # PyInstaller等でexe化されている場合：exe自身を直接起動
            exe = Path(sys.executable).resolve()
            work_dir = exe.parent
            bat = (
                f'@echo off\r\n'
                f'cd /d "{work_dir}"\r\n'
                f'start "" "{exe}"\r\n'
            )
        else:
            # スクリプト実行時：pythonw.exe（コンソール非表示）で起動
            app_script = Path(__file__).resolve().parent / "streamdeck_app.py"
            work_dir = app_script.parent
            py = sys.executable
            pyw = py.replace("python.exe", "pythonw.exe")
            launcher = pyw if Path(pyw).exists() else py
            bat = (
                f'@echo off\r\n'
                f'cd /d "{work_dir}"\r\n'
                f'start "" "{launcher}" "{app_script}"\r\n'
            )
        _bat_path().write_text(bat, encoding="utf-8")
        return True
    except Exception as e:
        print(f"[AUTOSTART] 登録失敗: {e}")
        return False


def disable() -> bool:
    """自動起動を解除する。成功でTrue"""
    try:
        p = _bat_path()
        if p.exists():
            p.unlink()
        return True
    except Exception as e:
        print(f"[AUTOSTART] 解除失敗: {e}")
        return False


def toggle(enabled: bool) -> bool:
    return enable() if enabled else disable()


if __name__ == "__main__":
    # テスト実行
    print("スタートアップフォルダ:", _startup_dir())
    print("現在の状態:", "登録済み" if is_enabled() else "未登録")
