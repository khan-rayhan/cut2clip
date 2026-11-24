@echo off
setlocal
cd /d "%~dp0\.."
echo ========================================
echo       Cut2Clip Windows Setup
echo ========================================
where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher not found. Install Python 3.12 from python.org and enable PATH.
  pause
  exit /b 1
)
py -3.12 --version >nul 2>nul
if errorlevel 1 (
  echo Python 3.12 is required for the tested dependency set.
  echo Install Python 3.12, then run this file again.
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  py -3.12 -m venv .venv
  if errorlevel 1 goto :fail
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 goto :fail
python -m pip install -r requirements.txt
if errorlevel 1 goto :fail
python -m pip install -e ".[dev]"
if errorlevel 1 goto :fail
echo.
echo Running system diagnostics...
python -m src.doctor
if errorlevel 1 (
  echo Some dependencies or system tools are missing. Review the report above.
  pause
  exit /b 2
)
echo.
echo Setup completed. Launch with: .venv\Scripts\python.exe -m src.gui_main
pause
exit /b 0
:fail
echo Setup failed. Check the error above and your internet connection.
pause
exit /b 1
