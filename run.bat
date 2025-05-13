@echo off
echo Starting Dynamic Sign Language Recognition System...
echo.

echo 1. Creating Python virtual environment (if it doesn't exist)...
if not exist signenv\ (
    python -m venv signenv
    call signenv\Scripts\activate
    pip install -r requirements.txt
) else (
    call signenv\Scripts\activate
)
echo.

echo 2. Checking if Ollama is installed...
where ollama >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo WARNING: Ollama doesn't appear to be installed.
    echo Please install Ollama from https://ollama.ai
    echo and pull the tinyllama model with 'ollama pull tinyllama'
) else (
    echo Checking if tinyllama model is available...
    ollama list | findstr "tinyllama" >nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo WARNING: tinyllama model not found. Attempting to pull...
        start "" ollama pull tinyllama
    ) else (
        echo tinyllama model is ready.
    )
)
echo.

echo 3. Starting services...
echo.
echo Starting sign recognition app (app.py)...
start "Sign Recognition" cmd /c "signenv\Scripts\activate && python app.py"
echo.

echo Starting orchestration service (sign_conversation.py)...
start "Orchestration Service" cmd /c "signenv\Scripts\activate && python sign_conversation.py"
echo.

echo Checking Angular frontend...
if exist "asl&fslmodel\frontend" (
    cd "asl&fslmodel\frontend"
    echo Starting Angular frontend...
    start "Angular Frontend" cmd /c "npm start"
    cd ..\..
) else (
    echo WARNING: Angular frontend directory not found.
    echo Please ensure the Angular app is properly set up.
)
echo.

echo All services started! Please open your browser to the following URLs:
echo - http://localhost:5000 - Sign Recognition Interface
echo - http://localhost:5001 - Conversation Interface
echo - http://localhost:4200 - Angular Frontend (if running)
echo.
echo Press any key to open the sign recognition app in your default browser...
pause >nul
start http://localhost:5000
echo.
echo System is running! Close this window when done to stop all services.
pause 