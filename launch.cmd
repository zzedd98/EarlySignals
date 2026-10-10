@echo off
REM Usage: launch.cmd scraper 30
REM        launch.cmd scraper 30 cache
REM        launch.cmd worker 10

if "%~1"=="" (
  echo Usage: launch.cmd ^<scraper^|worker^> [count] [cache]
  exit /b 1
)

set COUNT=%~2
if "%COUNT%"=="" set COUNT=10

set EXTRA=
if /I "%~3"=="cache" set EXTRA=--cache
if /I "%~3"=="--cache" set EXTRA=--cache

node "%~dp0scripts\launch.mjs" %1 %COUNT% %EXTRA%
exit /b %ERRORLEVEL%
