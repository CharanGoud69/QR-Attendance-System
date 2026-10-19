@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (set "PYTHON=python") else (set "PYTHON=py -3")
if not exist ".venv\Scripts\python.exe" (
  %PYTHON% -m venv .venv
  if errorlevel 1 goto fail
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto fail
.venv\Scripts\python.exe setup_admin.py --ensure
if errorlevel 1 goto fail
.venv\Scripts\python.exe launch.py
if errorlevel 1 goto fail
pause
exit /b 0
:fail
echo.
echo Setup failed. Install Python 3.12 or later from python.org with PATH enabled, then retry.
echo If Python is installed, read the error above. Internet is needed to install packages.
pause
exit /b 1
