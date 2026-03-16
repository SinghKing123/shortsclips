@echo off
title ShortsClips
cd /d F:\shortsclips

echo.
echo   Starting ShortsClips server...
echo.

start /b py server.py

timeout /t 4 /nobreak >nul

echo   Starting Cloudflare tunnel...
echo   ============================================
echo   Your public URL will appear below.
echo   Open it on your phone from ANYWHERE.
echo   ============================================
echo.

cloudflared.exe tunnel --url http://localhost:5555
