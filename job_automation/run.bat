@echo off
cd /d "%~dp0"

echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [*] Starting Job Automation...
python main.py

echo.
echo [!] Process exited. Press any key to close.
pause >nul
