# Dynamic Sign Language Recognition System

This system integrates three components to create a complete sign language recognition and communication pipeline:
1. **Sign Recognition App**: Python app that recognizes sign language gestures using AI
2. **Sign Animation**: Angular-based frontend for displaying sign language animations
3. **AI Response**: Ollama AI for generating responses to sign language input

## System Requirements

- Python 3.8+ with pip
- Node.js 16+ and npm
- Angular CLI
- Ollama (for AI text generation)
- Webcam/Camera for sign language input
- Windows/macOS/Linux

## Quick Setup

### 1. Python Environment Setup

```bash
# Clone the repository
git clone [repository-url]
cd dynamic-sign-recognizer

# Create and activate a virtual environment
python -m venv signenv
# On Windows:
signenv\Scripts\activate
# On macOS/Linux:
source signenv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Ollama Setup

1. Download and install Ollama from [ollama.ai](https://ollama.ai)
2. Pull the TinyLlama model:
```bash
ollama pull tinyllama
```
3. Start the Ollama server (it should run on port 11434)

### 3. Angular Frontend Setup

```bash
cd asl&fslmodel/frontend
npm install
```

## Running the System

You need to run these components in the following order:

### 1. Start the Sign Recognition App

```bash
# In the main project directory
python app.py
```
This runs the sign recognition service on http://localhost:5000

### 2. Start the Angular Frontend

```bash
cd asl&fslmodel/frontend
ng serve
```
This runs the Angular app on http://localhost:4200

### 3. Start the Orchestration Service

```bash
# In the main project directory
python sign_conversation.py
```
This runs the orchestration service on http://localhost:5001

### 4. Use the System

Open your browser and navigate to:
- **http://localhost:5000** - For the sign recognition interface
- **http://localhost:5001** - For the conversation interface
- **http://localhost:4200** - For the sign animation interface

## How to Use

1. Allow camera access when prompted
2. Make sign gestures (supported signs: hello, thanks, iloveyou)
3. The system will recognize and display your signs as text
4. Click "Send to AI" to send the recognized signs to Ollama
5. View the AI response
6. Clear the sentence to start over

## Troubleshooting

- **Camera not working**: Check browser permissions and ensure no other app is using the camera
- **Signs not recognized**: Ensure good lighting and clear hand visibility
- **Ollama not responding**: Check that Ollama is running with `ps aux | grep ollama` or Task Manager
- **Angular app not loading**: Verify Node.js version (16+) and that all Angular dependencies are installed

## System Architecture

- **app.py**: Core sign language recognition service using MediaPipe and TensorFlow
- **sign_conversation.py**: Orchestration service connecting sign recognition with Ollama
- **Angular frontend**: Provides sign language animation based on text input

## License

[Your License Information]

## Contributors

[List of contributors] 