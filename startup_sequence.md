# Sign Language Recognition System - Startup Sequence

This document outlines the correct sequence for starting all components of the Sign Language Recognition system.

## Prerequisites

- Python environment with all dependencies installed (use `pip install -r requirements.txt`)
- Angular CLI installed (for the frontend component)

## Startup Sequence

Always follow this specific order to ensure all components work correctly together:

1. **Activate the Python virtual environment**:
   ```
   # On Windows
   signenv\Scripts\activate
   
   # On macOS/Linux
   source signenv/bin/activate
   ```

2. **Start the Sign Recognition Service** (app.py):
   ```
   python app.py
   ```
   This service will run on port 5000 and handles the webcam feed and sign detection.

3. **Start the Gemini Integration Service** (integrate_gemini.py):
   ```
   python integrate_gemini.py
   ```
   This service handles the Gemini AI integration for processing sign language sentences.

4. **Start the Angular Frontend** (if not already running):
   ```
   cd asl&fslmodel/frontend
   ng serve
   ```
   The Angular app provides the frontend UI for the application.

5. **Start the Orchestration Service** (sign_conversation.py):
   ```
   python sign_conversation.py
   ```
   This service coordinates communication between all components.

## Accessing the Application

- Main sign recognition interface: http://127.0.0.1:5000
- Conversation interface: http://127.0.0.1:5001
- Angular frontend: http://127.0.0.1:4200

## Troubleshooting

If you encounter connection issues:
- Ensure all services are running on their expected ports
- Check that no firewall is blocking the communication
- Verify that the Python environment has all required dependencies
- Try using 127.0.0.1 instead of localhost for more reliable connections

## Core Files

The essential files needed to run the application are:
- app.py - Main sign recognition service
- sign_conversation.py - Orchestration service
- integrate_gemini.py - Gemini AI integration
- templates/ - Directory containing HTML templates
- Angular frontend (in asl&fslmodel/frontend/) 