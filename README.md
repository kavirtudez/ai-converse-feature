# Sign Language Recognition Web Interface

A web application that uses a machine learning model to recognize three sign language gestures in real-time:
- 'hello'
- 'thanks'
- 'iloveyou'

## Prerequisites

- Windows 10/11
- Python 3.8 or higher
- A webcam
- Administrator rights (for setup)

## Setup Instructions

### 1. Set up the Python Environment

The easiest way to set up your environment is using the provided setup script:

```bash
# Run this command with administrator privileges (right-click Command Prompt/PowerShell and select "Run as administrator")
python setup_env.py
```

This script will:
- Create a virtual environment called `venv`
- Install all required packages with compatible versions
- Avoid dependency conflicts

### 2. Activate the Virtual Environment

After the setup script completes, activate the virtual environment:

```bash
# On Windows
venv\Scripts\activate

# On macOS/Linux
source venv/bin/activate
```

### 3. Convert the Model

Once the environment is set up, convert the Keras model to TensorFlow.js format:

```bash
python convert_model.py
```

This will create a `tfjs_model` directory containing the converted model files.

### 4. Run the Flask Server

Start the Flask server to handle the sign recognition:

```bash
python app.py
```

The server will start at `http://127.0.0.1:5000`

### 5. Open the Web Interface

Open your web browser and navigate to:
```
http://127.0.0.1:5000
```

## Usage

1. Allow camera access when prompted by your browser
2. Position yourself in front of the camera
3. Perform one of the three signs:
   - 'hello' - Wave with your hand near your head
   - 'thanks' - Move your flat hand downward from your chin
   - 'iloveyou' - Extend your thumb, index finger and pinky finger while keeping other fingers closed

4. The interface will display the predicted sign and confidence level

## Troubleshooting

If you encounter issues:

1. **Dependency Problems**: Try running the setup script again with administrator privileges
2. **Camera Not Working**: Make sure your browser has permission to access the camera
3. **Model Conversion Fails**: Check that you have the correct versions of tensorflow (2.12.0) and tensorflowjs (3.18.0)
4. **Low Recognition Accuracy**: 
   - Ensure good lighting
   - Keep your hands within the camera frame
   - Make clear, deliberate movements

## Project Structure

- `app.py`: Flask server that processes video frames and makes predictions
- `convert_model.py`: Script to convert the Keras model to TensorFlow.js format
- `setup_env.py`: Script to set up the Python environment
- `action.h5`: Pre-trained Keras model
- `index.html` & `app.js`: Web interface for capturing and displaying video
- `templates/`: Contains Flask HTML templates
- `tfjs_model/`: Contains the converted TensorFlow.js model (after conversion)

## Technologies Used

- TensorFlow/Keras
- TensorFlow.js
- MediaPipe
- Flask
- HTML/CSS/JavaScript 