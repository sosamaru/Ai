@echo off
setlocal
cd /d "%~dp0"

py -3.13 -c "import sys" >nul 2>nul
if not errorlevel 1 goto py313
py -3.12 -c "import sys" >nul 2>nul
if not errorlevel 1 goto py312
py -3.11 -c "import sys" >nul 2>nul
if not errorlevel 1 goto py311
python -c "import sys" >nul 2>nul
if not errorlevel 1 goto python

echo [FAIL] Python 3.11, 3.12, or 3.13 was not found.
echo Install a supported Python version and enable the Python launcher or PATH option.
exit /b 1

:py313
py -3.13 -m aipro %*
exit /b %errorlevel%

:py312
py -3.12 -m aipro %*
exit /b %errorlevel%

:py311
py -3.11 -m aipro %*
exit /b %errorlevel%

:python
python -m aipro %*
exit /b %errorlevel%
