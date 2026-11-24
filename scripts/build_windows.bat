@echo off
setlocal
cd /d "%~dp0\.."
if not exist .venv\Scripts\python.exe (
  echo Virtual environment not found. Run scripts\setup_windows.bat first.
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m src.doctor
if errorlevel 1 (
  echo Required dependencies or FFmpeg are missing. Build stopped.
  exit /b 1
)
echo Running deterministic offline test suite...
set QT_QPA_PLATFORM=offscreen
python -m pytest -q -m "not integration and not model_integration and not slow"
if errorlevel 1 (
  echo Tests failed. Build stopped.
  exit /b 1
)
if "%CUT2CLIP_RUN_ONLINE_TESTS%"=="1" (
  echo Running real YouTube and AI model integration tests...
  python -m pytest -q -m "integration or model_integration"
  if errorlevel 1 exit /b 1
) else (
  echo Skipping network/AI-model integration tests. Set CUT2CLIP_RUN_ONLINE_TESTS=1 to enable them.
)
echo Building portable executable...
python -m PyInstaller --clean --noconfirm cut2clip.spec
if errorlevel 1 exit /b 1
if not exist dist\cut2clip.exe (
  echo Build did not produce dist\cut2clip.exe
  exit /b 1
)
echo Running packaged GUI smoke test...
start "" /wait dist\cut2clip.exe --smoke-test
if errorlevel 1 (
  echo Packaged GUI smoke test failed.
  exit /b 1
)
where iscc >nul 2>nul
if not errorlevel 1 (
  echo Building installer...
  iscc packaging\installer.iss
  if errorlevel 1 exit /b 1
) else (
  echo Inno Setup not found. Portable EXE is ready; installer skipped.
)
echo.
echo Build completed. See dist\cut2clip.exe and installer\ (if Inno Setup is installed).
exit /b 0
