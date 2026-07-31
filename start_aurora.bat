@echo off
echo Starting AURORA AI Backend...
start cmd /k "cd backend && uvicorn main:app --reload --port 8000"
timeout /t 3
echo Opening AURORA AI Dashboard...
start "" "frontend\index.html"
echo System Ready.
