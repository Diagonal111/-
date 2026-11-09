@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 goto :error
)
if not exist ".venv\Scripts\uvicorn.exe" (
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto :error
)
if not exist "dist\index.html" (
  if not exist "node_modules" (
    call npm install
    if errorlevel 1 goto :error
  )
  call npm run build
  if errorlevel 1 goto :error
)
.venv\Scripts\python.exe run.py
if errorlevel 1 goto :error
exit /b 0
:error
echo.
echo Startup failed. Check Python / Node.js and the messages above.
pause
exit /b 1
