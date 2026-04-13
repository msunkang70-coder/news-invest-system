@echo off
title NIAS v2.0 — Auto Scheduler
cd /d "C:\Users\MS\OneDrive\AI Study\뉴스정보\뉴스요약자동화"

:: 이미 실행 중이면 중복 실행 방지
tasklist /FI "WINDOWTITLE eq NIAS*" | find "python" >nul 2>&1
if %errorlevel%==0 (
    echo [NIAS] 이미 실행 중 — 스킵
    exit /b
)

echo ============================================
echo  NIAS v2.0 스케줄러 자동 시작
echo  시간: %date% %time%
echo ============================================

:: 스케줄러 시작 (백그라운드)
start /min "NIAS Scheduler" python -X utf8 src/main.py --schedule

:: 5초 대기 후 대시보드 시작
timeout /t 5 /nobreak >nul
start /min "NIAS Dashboard" streamlit run src/app.py --server.port 8501 --server.headless true

echo [NIAS] 스케줄러 + 대시보드 시작 완료
echo [NIAS] 대시보드: http://localhost:8501
echo.
echo 이 창을 닫아도 됩니다.
timeout /t 5
