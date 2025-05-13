@echo off
echo Starting Sign Language Recognition System...
echo.
echo This script will start all required services in the correct order.
echo.

REM Activate the Python virtual environment
echo Activating virtual environment...
call signenv\Scripts\activate
if %ERRORLEVEL% NEQ 0 (
    echo Failed to activate virtual environment. Please make sure it exists.
    pause
    exit /b
)
echo Virtual environment activated successfully.
echo.

REM Start the main recognition app
echo Starting Sign Recognition Service (app.py)...
start "Sign Recognition Service" cmd /k "python app.py"
echo Waiting for the service to initialize...
timeout /t 5 /nobreak > nul
echo.

REM Start the Gemini integration
echo Starting Gemini Integration Service...
start "Gemini Integration" cmd /k "python integrate_gemini.py"
echo Waiting for the service to initialize...
timeout /t 3 /nobreak > nul
echo.

REM Notify about Angular
echo.
echo You need to ensure the Angular app is running.
echo If it's not already running, open a new terminal and run:
echo cd asl^&fslmodel/frontend ^&^& ng serve
echo.
echo Press any key when the Angular app is running...
pause > nul

REM Start the orchestration service
echo Starting Orchestration Service...
start "Orchestration Service" cmd /k "python sign_conversation.py"
echo.

echo All services have been started.
echo.
echo Access the application at:
echo - Main recognition interface: http://127.0.0.1:5000
echo - Conversation interface: http://127.0.0.1:5001
echo - Angular frontend: http://127.0.0.1:4200
echo.
echo Press any key to exit this window...
pause > nul 