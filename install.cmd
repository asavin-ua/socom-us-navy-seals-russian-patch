@echo off
setlocal
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.11 or newer is required.
  pause
  exit /b 1
)
if "%~1"=="" (
  echo Drag a clean SOCOM USA v3.00 ISO onto install.cmd
  echo Or run: install.cmd "original.iso" "translated.iso"
  pause
  exit /b 1
)
if "%~2"=="" (
  python -B "%~dp0tools\project.py" build --input "%~1" --output "%~dpn1.ru.iso"
) else (
  python -B "%~dp0tools\project.py" build --input "%~1" --output "%~2"
)
set "patch_result=%errorlevel%"
if not "%patch_result%"=="0" echo Installation failed. See the error above.
pause
exit /b %patch_result%
