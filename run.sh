#!/bin/bash

echo "Starting Dynamic Sign Language Recognition System..."
echo

echo "1. Creating Python virtual environment (if it doesn't exist)..."
if [ ! -d "signenv" ]; then
    python3 -m venv signenv
    source signenv/bin/activate
    pip install -r requirements.txt
else
    source signenv/bin/activate
fi
echo

echo "2. Checking if Ollama is installed..."
if ! command -v ollama &> /dev/null; then
    echo "WARNING: Ollama doesn't appear to be installed."
    echo "Please install Ollama from https://ollama.ai"
    echo "and pull the tinyllama model with 'ollama pull tinyllama'"
else
    echo "Checking if tinyllama model is available..."
    if ! ollama list | grep -q "tinyllama"; then
        echo "WARNING: tinyllama model not found. Attempting to pull..."
        ollama pull tinyllama &
    else
        echo "tinyllama model is ready."
    fi
fi
echo

echo "3. Starting services..."
echo
echo "Starting sign recognition app (app.py)..."
python app.py > app_log.txt 2>&1 &
APP_PID=$!
echo "Sign recognition app started with PID: $APP_PID"
echo

echo "Starting orchestration service (sign_conversation.py)..."
python sign_conversation.py > conversation_log.txt 2>&1 &
CONVERSATION_PID=$!
echo "Orchestration service started with PID: $CONVERSATION_PID"
echo

echo "Checking Angular frontend..."
if [ -d "asl&fslmodel/frontend" ]; then
    cd "asl&fslmodel/frontend"
    echo "Starting Angular frontend..."
    npm start > ../../angular_log.txt 2>&1 &
    ANGULAR_PID=$!
    echo "Angular frontend started with PID: $ANGULAR_PID"
    cd ../..
else
    echo "WARNING: Angular frontend directory not found."
    echo "Please ensure the Angular app is properly set up."
fi
echo

echo "All services started! Please open your browser to the following URLs:"
echo "- http://localhost:5000 - Sign Recognition Interface"
echo "- http://localhost:5001 - Conversation Interface" 
echo "- http://localhost:4200 - Angular Frontend (if running)"
echo

echo "Opening sign recognition app in default browser..."
if command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:5000 &> /dev/null
elif command -v open &> /dev/null; then
    open http://localhost:5000
else
    echo "Could not open browser automatically. Please navigate to http://localhost:5000"
fi

echo "System is running! Press Ctrl+C to stop all services."
echo
echo "PIDs for reference (in case manual termination is needed):"
echo "Sign Recognition (app.py): $APP_PID"
echo "Orchestration (sign_conversation.py): $CONVERSATION_PID"
if [ -n "${ANGULAR_PID}" ]; then
    echo "Angular Frontend: $ANGULAR_PID"
fi

# Cleanup function
cleanup() {
    echo "Stopping all services..."
    kill $APP_PID 2>/dev/null
    kill $CONVERSATION_PID 2>/dev/null
    if [ -n "${ANGULAR_PID}" ]; then
        kill $ANGULAR_PID 2>/dev/null
    fi
    echo "All services stopped."
    exit 0
}

# Register the cleanup function to be called on SIGINT (Ctrl+C)
trap cleanup SIGINT

# Wait for user to press Ctrl+C
while true; do
    sleep 1
done 