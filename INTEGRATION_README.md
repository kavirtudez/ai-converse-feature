# Sign Language Conversation Integration

This project integrates the Dynamic Sign Language Recognition system with the Angular Sign Language Translation app, using Ollama for AI-powered responses.

## Overview

The system consists of three main components:

1. **Dynamic Sign Recognition** (app.py) - Recognizes sign language gestures in real-time using your webcam
2. **Ollama** - An AI model that generates short text responses to sign language input
3. **Angular Sign Animation** - Translates text responses back into animated sign language

## Prerequisites

- Python 3.7+
- Node.js and npm (for Angular)
- Angular CLI (`npm install -g @angular/cli`)
- Ollama installed and running (https://ollama.ai/)

## Setup

### 1. Install the required Python packages

```bash
pip install -r requirements.txt
pip install -r integration_requirements.txt
```

### 2. Make sure Ollama is installed and running

Download and install Ollama from https://ollama.ai/

Start Ollama and pull the Llama3 model:

```bash
ollama pull llama3
```

### 3. Configure the Angular app

Navigate to the Angular app directory and install dependencies:

```bash
cd asl&fslmodel/frontend
npm install
```

## Running the Integration

Start the integrated system by running:

```bash
python sign_conversation.py
```

This will:
1. Start the dynamic sign recognition app (app.py)
2. Start the Angular app
3. Start the integration server

Then open a web browser and navigate to:

```
http://localhost:5001
```

## How to Use

1. The interface shows two frames:
   - Left: Sign Recognition (captures your signs)
   - Right: Sign Animation (shows animated responses)

2. Make sign language gestures to create a sentence
   - Current supported signs: 'hello', 'thanks', 'iloveyou'
   - Your recognized signs will appear at the top of the left frame

3. Click "Send Sign Sentence" to submit the collected sentence to Ollama

4. Ollama will generate a short response (5 words or less)

5. The response will be sent to the Angular app for sign language animation

6. You can click "Clear Sentence" to clear the current collected signs

## Troubleshooting

If you encounter any issues:

1. Check that all services are running (green indicators at the top of the page)
2. Make sure Ollama is running and the llama3 model is installed
3. Verify that the cameras are properly connected and allowed
4. Try restarting the integration with `python sign_conversation.py`

## Technical Details

- **Sign Recognition**: Runs on port 5000
- **Angular App**: Runs on port 4200
- **Integration Server**: Runs on port 5001

The integration server acts as a bridge between the sign recognition app and the Angular app, using Ollama to generate responses.

## Customization

You can modify `sign_conversation.py` to:
- Change the Ollama model (change `OLLAMA_MODEL` variable)
- Adjust the maximum response length
- Change server ports if needed

## Notes

- The system is designed for short, simple conversations
- Ollama responses are limited to 5 words for better sign language animation
- The Angular app's text input is leveraged to receive text from Ollama 