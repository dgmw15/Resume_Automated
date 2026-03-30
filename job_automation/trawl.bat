@echo off
title Job Trawler

:: Lock the working directory to the folder this .bat lives in
cd /d "%~dp0"

echo.
echo [*] Working directory: %CD%
echo.

:: ── Activate venv ────────────────────────────────────────────────────────────
if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found.
    echo         Expected: %CD%\.venv\Scripts\activate.bat
    echo.
    echo         Fix: open a terminal here and run:
    echo           python -m venv .venv
    echo           .venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Could not activate the virtual environment.
    pause
    exit /b 1
)
echo [*] Virtual environment active.

:: ── Browser check ────────────────────────────────────────────────────────────
if not exist "%LOCALAPPDATA%\ms-playwright\chromium-1117\chrome-win\chrome.exe" (
    echo [!] Browser not found. Installing Chromium now (one-time download, ~150MB)...
    playwright install chromium
    if errorlevel 1 (
        echo [ERROR] Browser install failed.
        echo         Try running manually: .venv\Scripts\playwright.exe install chromium
        pause
        exit /b 1
    )
    echo [*] Browser installed.
) else (
    echo [*] Browser already installed.
)

:: ── Options ──────────────────────────────────────────────────────────────────
echo.
echo =====================================================
echo  Job Trawler — scrapes listings to trawl_results.xlsx
echo =====================================================
echo.
echo  Press Enter on any option to use the default.
echo.
set /p PAGES="  How many pages per role? [default: 2]: "
set /p PORTAL="  Which portal? (careersfuture / leave blank for all): "
set /p NODESC="  Skip full job descriptions for speed? (y / n) [default: n]: "

set ARGS=
if not "%PAGES%"==""  set ARGS=%ARGS% --pages %PAGES%
if not "%PORTAL%"=="" set ARGS=%ARGS% --portal %PORTAL%
if /i "%NODESC%"=="y" set ARGS=%ARGS% --no-descriptions

echo.
echo [*] Running: python trawl.py%ARGS%
echo.

:: ── Run ──────────────────────────────────────────────────────────────────────
python trawl.py%ARGS%

echo.
echo =====================================================
echo  Done. Results saved to trawl_results.xlsx
echo  Logs saved to trawl.log
echo =====================================================
echo.
pause
