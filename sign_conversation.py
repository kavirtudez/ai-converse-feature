import subprocess
import time
import threading
import requests
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import logging
import os
import json
import sys

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the Flask app for orchestration
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)  # More permissive CORS
socketio = SocketIO(app, 
                   cors_allowed_origins="*", 
                   async_mode='threading', 
                   logger=True, 
                   engineio_logger=True,
                   ping_timeout=60,
                   ping_interval=25)

# Add a response decorator to ensure CORS headers
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization,X-Requested-With'
    response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
    return response

# Global variables to track subprocess status
sign_recognition_process = None
angular_process = None

# Ollama settings
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "tinyllama"  # Changed from llama3 to use a smaller model

# Flask app and Angular app URLs
SIGN_APP_URL = "http://localhost:5000"
ANGULAR_APP_URL = "http://localhost:4200"

# Variable to store the current sentence
current_sentence = []
last_update_time = time.time()

# Thread for polling current sentence
sentence_polling_thread = None
stop_polling = False

# Add a direct sentence update endpoint
@app.route('/api/sentence_update', methods=['POST'])
def api_sentence_update():
    """Endpoint for app.py to directly push sentence updates"""
    global current_sentence, last_update_time
    
    try:
        data = request.json
        new_sentence = data.get('sentence', [])
        client_id = data.get('clientId', 'default')
        
        logger.info(f"Received direct sentence update from app.py: {new_sentence}")
        
        # Update our stored sentence
        current_sentence = new_sentence
        last_update_time = time.time()
        
        # Emit to any connected WebSocket clients
        try:
            socketio.emit('sentence_update', {'sentence': current_sentence})
            socketio.sleep(0)  # Allow emit to process
            logger.info(f"Emitted sentence update to WebSocket clients: {current_sentence}")
        except Exception as e:
            logger.error(f"Error emitting sentence update via WebSocket: {str(e)}")
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error processing direct sentence update: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

def poll_sign_app_for_sentence():
    """Background thread function to poll the sign app for the current sentence"""
    global current_sentence, stop_polling, last_update_time
    
    while not stop_polling:
        try:
            # Only poll if we haven't received a direct update recently
            if time.time() - last_update_time > 5:  # Only poll if no updates for 5 seconds
                response = requests.get(f"{SIGN_APP_URL}/get_sentence?clientId=default", timeout=3)
                logger.info(f"Received response from sign app: Status {response.status_code}")
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        logger.info(f"Parsed response data: {data}")
                        
                        if data.get('success', False):
                            new_sentence = data.get('sentence', [])
                            # Only emit if there's a change
                            if new_sentence != current_sentence:
                                current_sentence = new_sentence
                                last_update_time = time.time()
                                logger.info(f"Sentence updated: {current_sentence}")
                                try:
                                    # Force emit via socket
                                    socketio.emit('sentence_update', {'sentence': current_sentence})
                                    # Also immediately try to send a REST API update for clients using direct API
                                    socketio.sleep(0)  # Allow emit to process
                                except Exception as e:
                                    logger.error(f"Error emitting sentence update: {str(e)}")
                    except ValueError as e:
                        logger.error(f"Error parsing JSON response: {str(e)}, Response: {response.text}")
                else:
                    logger.warning(f"Failed to get sentence, status code: {response.status_code}, Response: {response.text}")
            
            # Force periodic updates even if no change detected
            # This ensures clients have the latest sentence
            if time.time() - last_update_time > 10:  # Every 10 seconds
                try:
                    socketio.emit('sentence_update', {'sentence': current_sentence})
                    last_update_time = time.time()
                    socketio.sleep(0)  # Allow emit to process
                    logger.info(f"Sent periodic update with current sentence: {current_sentence}")
                except Exception as e:
                    logger.error(f"Error emitting periodic update: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error polling for sentence: {str(e)}")
        
        # Reduced polling frequency since we now have direct updates
        time.sleep(1.0)  # Poll once a second instead of twice

# Start the sign recognition app
def start_sign_recognition():
    global sign_recognition_process
    logger.info("Starting sign recognition app (app.py)...")
    
    # Check if app.py exists
    if not os.path.exists("app.py"):
        logger.error("app.py not found in current directory. Please ensure it exists.")
        return False
    
    try:
        # Use subprocess.Popen to start the app.py process
        sign_recognition_process = subprocess.Popen(
            [sys.executable, "app.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        logger.info("Sign recognition app started successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to start sign recognition app: {str(e)}")
        return False

# Start the Angular app
def start_angular_app():
    global angular_process
    logger.info("Starting Angular app...")
    
    # Check if the Angular app directory exists
    angular_dir = "asl&fslmodel/frontend"
    if not os.path.exists(angular_dir):
        logger.error(f"Angular directory '{angular_dir}' not found. Please ensure it exists.")
        return False
    
    try:
        # Use subprocess.Popen to start the Angular app
        os.chdir(angular_dir)
        # Use shell=True for Windows to handle the & character properly
        angular_process = subprocess.Popen(
            ["ng", "serve"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=True  # Use shell=True on Windows for paths with special characters
        )
        # Change back to original directory
        os.chdir("../..")
        logger.info("Angular app started successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to start Angular app: {str(e)}")
        os.chdir("../..")  # Make sure to return to original directory even if failed
        return False

# Check if a service is running on a specific port
def check_service(url, max_attempts=10):
    for attempt in range(max_attempts):
        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                logger.info(f"Service at {url} is running")
                return True
        except requests.RequestException:
            pass
        
        logger.info(f"Waiting for service at {url} to start (attempt {attempt+1}/{max_attempts})...")
        time.sleep(3)
    
    logger.error(f"Service at {url} failed to start after {max_attempts} attempts")
    return False

# Get response from Ollama
def get_ollama_response(user_sentence):
    try:
        logger.info(f"Sending to Ollama: '{user_sentence}'")
        
        # Create a more conversational and helpful prompt
        prompt = f"""You are a friendly AI assistant communicating with someone using sign language.
        
The person has signed: "{user_sentence}"

Respond in a natural, conversational way. Keep your response short and simple (5-10 words maximum) 
since it will be translated back to sign language. Be positive, helpful, and engaging.

If the message is a greeting (like "hello"), respond with a greeting.
If the message shows appreciation, acknowledge it warmly.
If the message expresses feelings, respond empathetically.
For any other message, provide a friendly, relevant response.

Your response (5-10 words maximum):"""
        
        # Try multiple times with backoff
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = requests.post(
                    OLLAMA_URL,
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": False,
                        "max_tokens": 25,  # Allow slightly more tokens for better responses
                        "temperature": 0.7  # Add some creativity but keep it focused
                    },
                    timeout=10 if attempt == 0 else 15  # Longer timeout on retry
                )
                
                if response.status_code == 200:
                    response_data = response.json()
                    result = response_data.get('response', '').strip()
                    
                    # Basic filtering to ensure reasonable response
                    if not result or len(result) < 2:
                        result = "Hello, nice to meet you!"
                    
                    logger.info(f"Ollama response: '{result}'")
                    return result
                else:
                    logger.warning(f"Ollama returned status code {response.status_code} on attempt {attempt+1}")
                    if attempt < max_attempts - 1:
                        time.sleep(1)  # Wait before retry
                    
            except requests.exceptions.Timeout:
                logger.warning(f"Ollama request timed out on attempt {attempt+1}")
                if attempt < max_attempts - 1:
                    time.sleep(1)  # Wait before retry
            except Exception as e:
                logger.error(f"Error in Ollama request on attempt {attempt+1}: {str(e)}")
                if attempt < max_attempts - 1:
                    time.sleep(1)  # Wait before retry
        
        # If all attempts failed, provide a generic response
        logger.warning("All Ollama attempts failed, using fallback response")
        return "Nice to talk with you!"
    except Exception as e:
        logger.error(f"Error getting Ollama response: {str(e)}")
        return "I'm listening. Please continue."

# Send text to Angular app for translation to sign language
def send_to_angular_app(text):
    try:
        logger.info(f"Sending to Angular app: '{text}'")
        
        # For demonstration purposes, we'll simulate a successful response
        # In a production environment, we would need to:
        # 1. Either use Selenium to automate the browser interaction
        # 2. Or implement a custom API in the Angular app
        # 3. Or use JavaScript postMessage API to communicate with the iframe
        
        # For now, we'll inform the user to manually enter the text in the Angular app
        logger.info(f"Please enter '{text}' in the Angular app's text input field")
        
        # Return success to continue the flow
        return True
    except Exception as e:
        logger.error(f"Error sending to Angular app: {str(e)}")
        return False

# Main route to display UI
@app.route('/')
def index():
    return render_template('conversation.html')

# API endpoint to check status
@app.route('/api/status', methods=['GET'])
def api_status():
    status = check_and_emit_status()
    return jsonify(status)

# Direct API endpoint for getting the current sentence
@app.route('/api/sentence', methods=['GET'])
def api_sentence():
    global current_sentence
    # Try to fetch latest sentence from sign app directly
    try:
        response = requests.get(f"{SIGN_APP_URL}/get_sentence?clientId=default", timeout=3)
        if response.status_code == 200:
            try:
                data = response.json()
                logger.info(f"API endpoint received data from sign app: {data}")
                if data.get('success', False):
                    current_sentence = data.get('sentence', [])
            except ValueError as e:
                logger.warning(f"Could not parse JSON response from sign app: {str(e)}, Response: {response.text}")
        else:
            logger.warning(f"Sign app returned non-200 status: {response.status_code}")
    except Exception as e:
        logger.warning(f"Could not fetch latest sentence from sign app: {str(e)}")
    
    # Fetch the latest app.py test endpoint status too
    try:
        test_response = requests.get(f"{SIGN_APP_URL}/test", timeout=2)
        sign_app_status = "Running" if test_response.status_code == 200 else "Not responding correctly"
    except Exception:
        sign_app_status = "Not running"
    
    return jsonify({
        'sentence': current_sentence,
        'timestamp': time.time(),
        'sign_app_status': sign_app_status
    })

# API endpoint for clearing the sentence
@app.route('/api/clear_sentence', methods=['POST'])
def api_clear_sentence():
    try:
        response = requests.post(
            f"{SIGN_APP_URL}/clear_sentence", 
            json={'clientId': 'default'},
            timeout=5
        )
        
        success = response.status_code == 200
        if success:
            global current_sentence
            current_sentence = []
            # Try to emit via socket too
            try:
                socketio.emit('sentence_update', {'sentence': []})
                socketio.emit('system_message', {'message': 'Sentence cleared'})
            except Exception as e:
                logger.warning(f"Socket emit failed: {str(e)}")
                
            logger.info("Sentence cleared successfully")
            return jsonify({'success': True})
        else:
            logger.error(f"Failed to clear sentence: {response.status_code}")
            return jsonify({'success': False, 'error': f"Failed with status code {response.status_code}"})
    except Exception as e:
        logger.error(f"Error clearing sentence: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

# API endpoint for sending conversation to Ollama
@app.route('/api/send_conversation', methods=['POST'])
def api_send_conversation():
    try:
        global current_sentence
        
        if not current_sentence:
            return jsonify({
                'success': False, 
                'error': 'No sentence available'
            })
        
        # Get the sentence
        sentence = " ".join(current_sentence)
        logger.info(f"Processing sentence: {sentence}")
        
        # Get response from Ollama
        ollama_response = get_ollama_response(sentence)
        
        # Send to Angular app (simulation)
        success = send_to_angular_app(ollama_response)
        
        # Try to emit via socket
        try:
            socketio.emit('conversation_update', {
                'user_sentence': sentence,
                'response': ollama_response
            })
        except Exception as e:
            logger.warning(f"Socket emit failed: {str(e)}")
        
        # Clear the sentence after sending
        try:
            requests.post(
                f"{SIGN_APP_URL}/clear_sentence", 
                json={'clientId': 'default'},
                timeout=5
            )
            # Reset our local copy too
            current_sentence = []
            try:
                socketio.emit('sentence_update', {'sentence': []})
            except Exception as e:
                logger.warning(f"Socket emit failed: {str(e)}")
        except Exception as e:
            logger.warning(f"Failed to clear sentence after conversation: {str(e)}")
        
        return jsonify({
            'success': True, 
            'response': ollama_response,
            'user_sentence': sentence
        })
        
    except Exception as e:
        logger.error(f"Error in conversation: {str(e)}")
        return jsonify({
            'success': False, 
            'error': str(e)
        })

# SocketIO event handlers
@socketio.on('connect')
def handle_connect():
    logger.info('Client connected')
    # Send current status and sentence immediately upon connection
    check_and_emit_status()
    emit('sentence_update', {'sentence': current_sentence})

@socketio.on('disconnect')
def handle_disconnect():
    logger.info('Client disconnected')

@socketio.on('check_status')
def handle_check_status():
    check_and_emit_status()

@socketio.on('clear_sentence')
def handle_clear_sentence():
    try:
        response = requests.post(
            f"{SIGN_APP_URL}/clear_sentence", 
            json={'clientId': 'default'},
            timeout=5
        )
        
        success = response.status_code == 200
        if success:
            global current_sentence
            current_sentence = []
            emit('sentence_update', {'sentence': []})
            emit('system_message', {'message': 'Sentence cleared'})
            logger.info("Sentence cleared successfully")
        else:
            emit('system_message', {'message': 'Error clearing sentence'})
            logger.error(f"Failed to clear sentence: {response.status_code}")
            
        return {'success': success}
    except Exception as e:
        logger.error(f"Error clearing sentence: {str(e)}")
        emit('system_message', {'message': f'Error: {str(e)}'})
        return {'success': False, 'error': str(e)}

@socketio.on('send_conversation')
def handle_send_conversation():
    try:
        # Use the current sentence we've been tracking
        global current_sentence
        
        if not current_sentence:
            emit('system_message', {'message': 'No sentence available'})
            return {'success': False, 'error': 'No sentence available'}
        
        # Get the sentence
        sentence = " ".join(current_sentence)
        logger.info(f"Processing sentence: {sentence}")
        
        # Get response from Ollama
        ollama_response = get_ollama_response(sentence)
        
        # Send to Angular app (simulation)
        success = send_to_angular_app(ollama_response)
        
        # Emit the conversation update
        emit('conversation_update', {
            'user_sentence': sentence,
            'response': ollama_response
        })
        
        # Clear the sentence after sending
        try:
            requests.post(
                f"{SIGN_APP_URL}/clear_sentence", 
                json={'clientId': 'default'},
                timeout=5
            )
            # Reset our local copy too
            current_sentence = []
            emit('sentence_update', {'sentence': []})
        except Exception as e:
            logger.warning(f"Failed to clear sentence after conversation: {str(e)}")
        
        return {'success': True, 'response': ollama_response}
        
    except Exception as e:
        logger.error(f"Error in conversation: {str(e)}")
        emit('system_message', {'message': f'Error: {str(e)}'})
        return {'success': False, 'error': str(e)}

def check_and_emit_status():
    """Check all services and emit status to clients"""
    sign_app_running = False
    angular_app_running = False
    ollama_running = False
    
    try:
        # Check sign recognition app with more flexible parsing
        sign_response = requests.get(f"{SIGN_APP_URL}/test", timeout=3)
        sign_app_running = sign_response.status_code == 200
        logger.info(f"Sign app test endpoint returned: {sign_response.text}")
    except requests.RequestException as e:
        logger.warning(f"Sign recognition app is not running: {str(e)}")
    
    try:
        # Check Angular app
        angular_response = requests.get(f"{ANGULAR_APP_URL}", timeout=2)
        angular_app_running = angular_response.status_code == 200
    except requests.RequestException:
        logger.warning("Angular app is not running")
    
    try:
        # First check if Ollama server is running at all
        ollama_server_response = requests.get("http://localhost:11434/api/tags", timeout=3)
        
        if ollama_server_response.status_code == 200:
            # Check if our model is available
            models = ollama_server_response.json().get('models', [])
            model_available = any(model['name'].startswith(OLLAMA_MODEL) for model in models)
            
            if model_available:
                # If model is available, test with a simple query
                test_response = requests.post(
                    OLLAMA_URL,
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": "hello",
                        "max_tokens": 1
                    },
                    timeout=5
                )
                ollama_running = test_response.status_code == 200
                if ollama_running:
                    logger.info(f"Ollama is running correctly with model {OLLAMA_MODEL}")
                else:
                    logger.warning(f"Ollama API returned status code {test_response.status_code}")
            else:
                logger.warning(f"Model {OLLAMA_MODEL} not found. Please run 'ollama pull {OLLAMA_MODEL}'")
        else:
            logger.warning(f"Ollama server returned status code {ollama_server_response.status_code}")
            
    except requests.ConnectionError:
        logger.warning("Could not connect to Ollama. Make sure Ollama service is running.")
    except requests.exceptions.ReadTimeout:
        logger.warning("Ollama request timed out. Service might be overloaded.")
    except Exception as e:
        logger.warning(f"Error checking Ollama: {str(e)}")
    
    # Emit status to all clients
    try:
        socketio.emit('status_update', {
            'sign_app_running': sign_app_running,
            'angular_app_running': angular_app_running,
            'ollama_running': ollama_running
        })
    except Exception as e:
        logger.warning(f"Failed to emit status update: {str(e)}")
    
    return {
        'sign_app_running': sign_app_running,
        'angular_app_running': angular_app_running,
        'ollama_running': ollama_running
    }

# Function to clean up processes on shutdown
def cleanup():
    logger.info("Cleaning up processes...")
    
    global stop_polling
    stop_polling = True
    
    if sign_recognition_process:
        logger.info("Terminating sign recognition app...")
        sign_recognition_process.terminate()
        
    if angular_process:
        logger.info("Terminating Angular app...")
        angular_process.terminate()

if __name__ == '__main__':
    try:
        # Create templates directory if it doesn't exist
        if not os.path.exists('templates'):
            os.mkdir('templates')
        
        # Start services automatically if possible
        success = True
        
        # Try to start sign recognition app if it's not already running
        try:
            sign_response = requests.get(f"{SIGN_APP_URL}/test", timeout=2)
            sign_running = sign_response.status_code == 200
            if sign_running:
                logger.info("Sign recognition app is already running")
            else:
                logger.warning("Sign recognition app response unexpected, will try to start it")
                success = start_sign_recognition() and success
        except requests.RequestException:
            logger.info("Sign recognition app not detected, will try to start it")
            success = start_sign_recognition() and success
        
        # Try to start Angular app if it's not already running
        try:
            angular_response = requests.get(ANGULAR_APP_URL, timeout=2)
            angular_running = angular_response.status_code == 200
            if angular_running:
                logger.info("Angular app is already running")
            else:
                logger.warning("Angular app response unexpected, cannot start automatically")
        except requests.RequestException:
            logger.warning("Angular app not detected. Please start it with: cd asl&fslmodel/frontend && ng serve")
        
        # Check if Ollama is running
        try:
            response = requests.post(
                OLLAMA_URL,
                json={"model": OLLAMA_MODEL, "prompt": "hello", "max_tokens": 1},
                timeout=5
            )
            ollama_running = response.status_code == 200
            if not ollama_running:
                logger.warning(f"Ollama service returned status code {response.status_code}. Make sure Ollama is running.")
        except Exception as e:
            logger.warning(f"Ollama might not be running: {str(e)}")
            logger.warning(f"Please make sure Ollama is running and the {OLLAMA_MODEL} model is pulled.")
        
        # If services started successfully, start the sentence polling thread
        if success:
            stop_polling = False
            sentence_polling_thread = threading.Thread(target=poll_sign_app_for_sentence, daemon=True)
            sentence_polling_thread.start()
            logger.info("Started sentence polling thread")
        
        # Start the orchestration app
        logger.info("Starting conversation orchestration app on port 5001")
        logger.info("NOTE: Please make sure the following services are running separately:")
        logger.info("1. Sign Recognition App: python app.py (on port 5000)")
        logger.info("2. Angular App: cd asl&fslmodel/frontend && ng serve (on port 4200)")
        logger.info(f"3. Ollama Service with {OLLAMA_MODEL} model pulled")
        
        # Run with allow_unsafe_werkzeug=True to support newer Flask versions
        socketio.run(app, host='0.0.0.0', port=5001, debug=True, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        cleanup() 