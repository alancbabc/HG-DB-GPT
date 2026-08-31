@echo off
setlocal
rem %~dp0 ends in a backslash. Keep a trailing dot so the closing quote is not
rem parsed into the PowerShell argument (for example, E:\media\ becomes E:\media").
set "DBGPT_RELEASE_ROOT=%~dp0."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%DBGPT_RELEASE_ROOT%\scripts\Invoke-DBGPTOfflineSetup.ps1" -ReleaseRoot "%DBGPT_RELEASE_ROOT%"
set "DBGPT_SETUP_EXIT=%ERRORLEVEL%"
if not "%DBGPT_SETUP_EXIT%"=="0" (
  echo.
  echo DB-GPT offline setup did not complete. Review the error and log path above.
  pause
)
exit /b %DBGPT_SETUP_EXIT%
