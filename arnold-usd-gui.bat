@echo off
setlocal EnableExtensions
title arnold-usd-gui
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "PYTHONPATH=%ROOT%\src;%PYTHONPATH%"

set "PY="
set "PYW="

if exist "%ROOT%\.venv\Scripts\python.exe" set "PY=%ROOT%\.venv\Scripts\python.exe"
if exist "%ROOT%\.venv\Scripts\pythonw.exe" set "PYW=%ROOT%\.venv\Scripts\pythonw.exe"
if exist "%ROOT%\venv\Scripts\python.exe" if not defined PY set "PY=%ROOT%\venv\Scripts\python.exe"
if exist "%ROOT%\venv\Scripts\pythonw.exe" if not defined PYW set "PYW=%ROOT%\venv\Scripts\pythonw.exe"

if not defined PYW for /f "delims=" %%I in ('where pyw 2^>nul') do (
    set "PYW=%%I"
    goto :have_pyw
)
:have_pyw
if not defined PYW for /f "delims=" %%I in ('where pythonw 2^>nul') do (
    set "PYW=%%I"
    goto :have_pyw2
)
:have_pyw2
if not defined PY for /f "delims=" %%I in ('where py 2^>nul') do (
    set "PY=%%I"
    goto :have_py
)
:have_py
if not defined PY for /f "delims=" %%I in ('where python 2^>nul') do (
    set "PY=%%I"
    goto :have_py2
)
:have_py2

if not defined PY if not defined PYW (
    call :fail "Python 3.10+ was not found. Install Python and enable Add python.exe to PATH."
    exit /b 1
)

rem Explorer double-click: cmd.exe /c "...arnold-usd-gui.bat" — hide the console.
echo(%CMDCMDLINE%| findstr /I /C:"%~nx0" >nul
if %ERRORLEVEL%==0 if defined PYW (
    start "arnold-usd-gui" /D "%ROOT%" "%PYW%" -m arnold_usd_gui %*
    exit /b 0
)

if defined PY (
    "%PY%" -m arnold_usd_gui %*
    exit /b %ERRORLEVEL%
)
"%PYW%" -m arnold_usd_gui %*
exit /b %ERRORLEVEL%

:fail
powershell -NoProfile -Command ^
  "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('%~1','arnold-usd-gui')" 2>nul
if errorlevel 1 (
    echo arnold-usd-gui: %~1
    pause
)
exit /b 1
