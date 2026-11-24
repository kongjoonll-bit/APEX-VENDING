@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=C:\Users\USER\Downloads\python-3.12\python.exe"

if not exist "%PY%" (
  echo [ERROR] Python not found: %PY%
  pause
  exit /b 1
)

rem ---------- 1) 토큰 확인 ----------
findstr /b /c:"CHECKER_TOKEN=MT" ".env" >nul 2>&1
if not errorlevel 1 goto token_ok

echo ============================================================
echo  봇 토큰이 설정되지 않았습니다.
echo  Discord Developer Portal ^> Bots ^> Reset Token 후
echo  MT... 로 시작하는 값을 붙여넣고 Enter 하세요.
echo ============================================================
set /p "TOK=CHECKER_TOKEN="
if "%TOK%"=="" (
  echo 토큰이 비어 있어 종료합니다.
  pause
  exit /b 1
)
powershell -NoProfile -Command "$p='.env'; $l=Get-Content $p; $l=$l -replace '^CHECKER_TOKEN=.*$','CHECKER_TOKEN=%TOK%'; Set-Content -Path $p -Value $l -Encoding UTF8"
echo 토큰을 .env 에 저장했습니다.

:token_ok

rem ---------- 2) 서버(길드) ID 확인 : 즉시 명령 등록 ----------
findstr /b /c:"GUILD_ID=" ".env" >nul 2>&1
powershell -NoProfile -Command "$v=(Select-String -Path '.env' -Pattern '^GUILD_ID=(.*)$').Matches.Groups[1].Value; if($v.Trim() -eq ''){exit 1}else{exit 0}"
if not errorlevel 1 goto guild_ok

echo.
echo  서버(길드) ID를 입력하면 /패널 이 즉시 등록됩니다. 모르면 그냥 Enter.
set /p "GID=GUILD_ID="
if not "%GID%"=="" powershell -NoProfile -Command "$p='.env'; $l=Get-Content $p; $l=$l -replace '^GUILD_ID=.*$','GUILD_ID=%GID%'; Set-Content -Path $p -Value $l -Encoding UTF8"

:guild_ok

rem ---------- 3) 웹 + 봇 실행 ----------
echo.
echo [1/2] 웹 리포트 서버 시작: http://localhost:5001
start "Apex Checker WEB" "%PY%" web.py
timeout /t 2 >nul

echo [2/2] 디스코드 봇 시작...
echo.
"%PY%" checker_bot.py

echo.
echo 봇이 종료되었습니다. 위 로그를 확인하세요.
pause >nul

