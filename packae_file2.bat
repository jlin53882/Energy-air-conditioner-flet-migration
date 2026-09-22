@echo off
chcp 65001 >nul
title 🚀 一鍵打包 ERAP 程式（Flet + Tkinter + Telegram 最終穩定版）

echo ===============================================
echo  🚀 開始一鍵打包 ERAP 程式（Flet + Tkinter + Telegram）
echo ===============================================

REM 1️⃣ 檢查 uv 是否存在
uv --version >nul 2>nul
if %errorlevel% neq 0 (
    cls
    echo.
    echo  ❌ 錯誤：找不到 'uv' 命令。
    echo  請在 PowerShell 中執行以下官方指令來安裝 uv：
    echo.
    echo  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    echo.
    pause
    exit /b
)

echo.
echo 🧩 檢查 / 建立 Python 虛擬環境...
uv venv >nul 2>nul

echo.
echo 🔄 同步打包環境套件 (含 extras)...
uv sync --all-extras

echo.
echo ⚡ 安裝 Nuitka 打包加速快取 sccache...
uv add sccache

echo.
echo 🔧 開始使用 Nuitka 打包 (自動偵測 sccache 加速)...

set PYTHON_EXE=.venv\Scripts\python.exe
set OUTPUT_DIR=AutoPunch_Output

REM 暫時將 venv\Scripts 加入 PATH，以便 Nuitka 找到 sccache.exe
set "ORIGINAL_PATH=%PATH%"
set "PATH=%~dp0.venv\Scripts;%PATH%"

REM 若有 icon.ico，使用它
if exist icon.ico (
    set ICON_OPT=--windows-icon-from-ico=icon.ico
) else (
    set ICON_OPT=
)

%PYTHON_EXE% -m nuitka ^
  --standalone ^
  --jobs=16 ^
  --windows-console-mode=force ^
  --show-progress ^
  --enable-plugin=tk-inter ^
  --enable-plugin=pylint-warnings ^
  --enable-plugin=anti-bloat ^
  --include-package=matplotlib.backends ^
  --include-package=matplotlib.pyplot ^
  --include-package=mpl_toolkits ^
  --include-package=flet ^
  --include-package=telegram ^
  --include-package=telegram.ext ^
  --nofollow-import-to=tkinter.test ^
  --nofollow-import-to=tkinter.tix ^
  --remove-output ^
  --output-dir=%OUTPUT_DIR% ^
  %ICON_OPT% ^
  run.py

REM 還原原始的 PATH
set "PATH=%ORIGINAL_PATH%"
set "ORIGINAL_PATH="

echo.
echo ===============================================
echo  🎉 打包完成！
echo  📂 輸出位置：%~dp0%OUTPUT_DIR%
echo ===============================================
pause