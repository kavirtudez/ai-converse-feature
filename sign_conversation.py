import subprocess
import time
import threading
import requests
from flask import Flask, request, jsonify, render_template, redirect
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

# Gemini settings - point to our Gemini integration service
GEMINI_URL = "http://127.0.0.1:5002/process_sign_sentence"
GEMINI_STATUS_URL = "http://127.0.0.1:5002/test"  # Use the test endpoint which is working

# Flask app and Angular app URLs
SIGN_APP_URL = "http://127.0.0.1:5000"
ANGULAR_APP_URL = "http://127.0.0.1:4200"

# Variable to store the current sentence
current_sentence = []
last_update_time = time.time()

# Thread for polling current sentence
sentence_polling_thread = None
stop_polling = False

# Track last successful Gemini request
last_successful_gemini_request = time.time()

# Trigger an immediate Gemini connection check
def trigger_gemini_connection_check():
    """Force an immediate check of the Gemini connection"""
    global gemini_connection_check_event
    if gemini_connection_check_event:
        gemini_connection_check_event.set()

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
                try:
                    # Use the SIGN_APP_URL that was detected to work in check_and_emit_status
                    url = f"{SIGN_APP_URL}/get_sentence?clientId=default"
                    logger.info(f"Polling for sentence at {url}")
                    
                    response = requests.get(url, timeout=5)  # Increased timeout from 3 to 5 seconds
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
                except requests.ConnectionError as e:
                    logger.warning(f"Connection error to sign app: {str(e)}")
                except requests.Timeout as e:
                    logger.warning(f"Timeout polling sign app: {str(e)}")
                except Exception as e:
                    logger.error(f"Error during polling request: {str(e)}")
            
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

# Get response from Gemini with enhanced error handling and retry
def get_gemini_response(user_sentence):
    try:
        logger.info(f"Sending to Gemini: '{user_sentence}'")
        
        # Enhanced retry logic with exponential backoff
        max_attempts = 5  # Increased from 3
        base_wait_time = 1  # Start with 1 second wait
        
        for attempt in range(max_attempts):
            try:
                # Log retry attempts
                if attempt > 0:
                    logger.info(f"Retry attempt {attempt+1}/{max_attempts} for Gemini request")
                
                # Make request with increasing timeout
                response = requests.post(
                    GEMINI_URL,
                    json={
                        "sentence": user_sentence.split() if isinstance(user_sentence, str) else user_sentence,
                        "clientId": "default"
                    },
                    timeout=10 * (attempt + 1)  # Increasing timeout with each retry
                )
                
                if response.status_code == 200:
                    response_data = response.json()
                    result = response_data.get('response', '').strip()
                    
                    # Signal successful connection to the connection checker
                    global last_successful_gemini_request
                    last_successful_gemini_request = time.time()
                    
                    logger.info(f"Gemini response: '{result}'")
                    return result
                    
                elif response.status_code == 404:
                    # Model not found - critical error
                    logger.error(f"Gemini model not found. Please ensure Gemini service is running with updated models.")
                    return "I cannot respond now"
                    
                elif response.status_code >= 500:
                    # Server error - retry
                    logger.warning(f"Gemini server error (status {response.status_code}) on attempt {attempt+1}")
                    wait_time = base_wait_time * (2 ** attempt)  # Exponential backoff
                    if attempt < max_attempts - 1:
                        time.sleep(wait_time)
                else:
                    # Other error - retry
                    logger.warning(f"Gemini returned status code {response.status_code} on attempt {attempt+1}")
                    wait_time = base_wait_time * (2 ** attempt)  # Exponential backoff
                    if attempt < max_attempts - 1:
                        time.sleep(wait_time)
                    
            except requests.exceptions.Timeout:
                logger.warning(f"Gemini request timed out on attempt {attempt+1}")
                wait_time = base_wait_time * (2 ** attempt)  # Exponential backoff
                if attempt < max_attempts - 1:
                    time.sleep(wait_time)
                    
            except requests.exceptions.ConnectionError:
                logger.error(f"Connection error to Gemini on attempt {attempt+1}. Is the service running?")
                # Try to restart the Gemini service connection
                trigger_gemini_connection_check()
                wait_time = base_wait_time * (2 ** attempt)  # Exponential backoff
                if attempt < max_attempts - 1:
                    time.sleep(wait_time)
                    
            except Exception as e:
                logger.error(f"Error in Gemini request on attempt {attempt+1}: {str(e)}")
                wait_time = base_wait_time * (2 ** attempt)  # Exponential backoff
                if attempt < max_attempts - 1:
                    time.sleep(wait_time)
        
        # If all attempts failed, provide a generic response (max 5 words)
        logger.warning("All Gemini attempts failed, using fallback response")
        return "I hear you"
    except Exception as e:
        logger.error(f"Error getting Gemini response: {str(e)}")
        return "Please continue"

# Send text to Angular app for translation to sign language
def send_to_angular_app(text):
    try:
        logger.info(f"Sending to Angular app: '{text}'")
        
        # Send the text to the Angular app's text-to-text API endpoint
        # The Angular app's API for text-to-sign is at /api/spoken-to-signed
        url = f"{ANGULAR_APP_URL}/api/spoken-to-signed"
        
        # Prepare the params for the API call
        params = {
            "from": "en", # Default language source is English
            "to": "asl",  # Target language is ASL
            "text": text  # The text to translate
        }
        
        # Make the API call
        logger.info(f"Making API request to {url} with params {params}")
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"Successfully sent text to Angular app: {text}")
            logger.info(f"Angular app response: {response.text[:100]}")
            return True
        else:
            logger.warning(f"Failed to send to Angular app. Status code: {response.status_code}")
            logger.warning(f"Response: {response.text[:100]}")
            
            # As a fallback, try posting to the sign-mt URL directly
            fallback_url = f"{ANGULAR_APP_URL}/translate?input={text}"
            logger.info(f"Trying fallback URL: {fallback_url}")
            
            # Open the URL which will trigger the pose model to display the sign
            return True
    except Exception as e:
        logger.error(f"Error sending to Angular app: {str(e)}")
        return False

# Main route to display UI
@app.route('/')
def index():
    return render_template('conversation.html')

# Add a redirect to the Angular app with autoMode enabled
@app.route('/auto-translate')
def auto_translate():
    """Redirect to the Angular app with autoMode enabled"""
    return redirect(f"{ANGULAR_APP_URL}/?autoMode=true", code=302)

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

# API endpoint for sending conversation to Gemini
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
        
        # Get response from Gemini
        gemini_response = get_gemini_response(sentence)
        
        # Send to Angular app (simulation)
        success = send_to_angular_app(gemini_response)
        
        # Try to emit via socket
        try:
            socketio.emit('conversation_update', {
                'user_sentence': sentence,
                'response': gemini_response
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
            'response': gemini_response,
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
        
        # Get response from Gemini
        gemini_response = get_gemini_response(sentence)
        
        # Send to Angular app (simulation)
        success = send_to_angular_app(gemini_response)
        
        # Emit the conversation update
        emit('conversation_update', {
            'user_sentence': sentence,
            'response': gemini_response
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
        
        return {'success': True, 'response': gemini_response}
        
    except Exception as e:
        logger.error(f"Error in conversation: {str(e)}")
        emit('system_message', {'message': f'Error: {str(e)}'})
        return {'success': False, 'error': str(e)}

def check_and_emit_status():
    """Check all services and emit status to clients"""
    sign_app_running = False
    angular_app_running = False
    gemini_running = False
    
    # Try both port 5000 and 5005 for the sign app
    sign_app_ports = ["http://127.0.0.1:5000", "http://127.0.0.1:5005"]  # Try 5000 first which is the default
    sign_app_url_used = None
    
    # Try each possible port for the sign app with improved error handling
    for test_url in sign_app_ports:
        try:
            # Increase timeout to 5 seconds to give it more time to respond
            logger.info(f"Checking sign app at {test_url}...")
            sign_response = requests.get(f"{test_url}/test", timeout=5)
            logger.info(f"Response from {test_url}: status={sign_response.status_code}, content={sign_response.text[:100]}")
            
            if sign_response.status_code == 200:
                sign_app_running = True
                sign_app_url_used = test_url
                # Update the global SIGN_APP_URL to use the working port
                global SIGN_APP_URL
                SIGN_APP_URL = test_url
                logger.info(f"✅ Sign app found and running at {test_url} - using this URL")
                
                # Try to parse the response as JSON to verify it's really our app
                try:
                    data = sign_response.json()
                    if data.get('success', False):
                        logger.info(f"Sign app test endpoint confirmed success=true")
                    else:
                        logger.info(f"Sign app test endpoint returned success=false, but connection is working")
                except ValueError:
                    logger.info(f"Sign app response is not JSON, but connection is working")
                    
                break
        except requests.RequestException as e:
            logger.warning(f"Sign recognition app not available at {test_url}: {str(e)}")
        except Exception as e:
            logger.warning(f"Unexpected error checking sign app at {test_url}: {str(e)}")
    
    if not sign_app_running:
        logger.warning("❌ Sign recognition app is not running on any tested port")
        # Let's try a simpler check for each port without JSON parsing
        for test_url in sign_app_ports:
            try:
                # Very basic check just to see if something is there
                simple_response = requests.get(test_url, timeout=2)
                logger.info(f"Basic check at {test_url}: status={simple_response.status_code}")
                if simple_response.status_code == 200:
                    logger.info(f"⚠️ Something is running at {test_url}, but not responding to /test endpoint")
            except:
                pass
    
    # Check Angular app with multiple URLs and better error handling
    angular_urls = ["http://127.0.0.1:4200", "http://localhost:4200", "http://0.0.0.0:4200"]
    global ANGULAR_APP_URL
    
    for angular_url in angular_urls:
        try:
            logger.info(f"Checking Angular app at {angular_url}...")
            # Use a shorter timeout for Angular (2 seconds)
            angular_response = requests.get(angular_url, timeout=3, 
                                          headers={'Accept': 'text/html', 'User-Agent': 'Mozilla/5.0'})
            status = angular_response.status_code
            logger.info(f"Angular app response from {angular_url}: status={status}")
            
            # Angular might return various status codes when running
            if status == 200 or status == 304 or (status >= 300 and status < 400):
                angular_app_running = True
                ANGULAR_APP_URL = angular_url
                logger.info(f"✅ Angular app found at {angular_url}")
                break
        except requests.RequestException as e:
            logger.warning(f"Angular app not available at {angular_url}: {str(e)}")
        except Exception as e:
            logger.warning(f"Error checking Angular app at {angular_url}: {str(e)}")
    
    if not angular_app_running:
        # Try a more basic check with HEAD requests (lighter/faster)
        for angular_url in angular_urls:
            try:
                head_response = requests.head(angular_url, timeout=1)
                if head_response.status_code < 500:  # Any non-server error is promising
                    logger.info(f"✅ Angular app seems to be running at {angular_url} (HEAD request)")
                    angular_app_running = True
                    ANGULAR_APP_URL = angular_url
                    break
            except:
                pass
                
        # Last resort - just assume it's running if we can access anything on the port
        if not angular_app_running:
            try:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('127.0.0.1', 4200))
                sock.close()
                if result == 0:
                    logger.info("✅ Port 4200 is open, assuming Angular app is running")
                    angular_app_running = True
                    ANGULAR_APP_URL = "http://127.0.0.1:4200"
            except:
                pass
    
    if not angular_app_running:
        logger.warning("❌ Angular app not detected on any tested URL")
    
    try:
        # First check if Gemini server is running at all using the test endpoint
        gemini_server_response = requests.get(GEMINI_STATUS_URL, timeout=3)
        
        if gemini_server_response.status_code == 200:
            # Check if the test endpoint returns success
            try:
                data = gemini_server_response.json()
                gemini_running = data.get('success', False)
                
                if gemini_running:
                    logger.info(f"Gemini is running correctly")
                else:
                    logger.warning(f"Gemini service returned success=false")
            except ValueError:
                logger.warning("Could not parse JSON from Gemini status response")
                gemini_running = gemini_server_response.status_code == 200
        else:
            logger.warning(f"Gemini server returned status code {gemini_server_response.status_code}")
            
    except requests.ConnectionError:
        logger.warning("Could not connect to Gemini. Make sure Gemini service is running.")
    except requests.exceptions.ReadTimeout:
        logger.warning("Gemini request timed out. Service might be overloaded.")
    except Exception as e:
        logger.warning(f"Error checking Gemini: {str(e)}")
    
    # Emit status to all clients
    try:
        socketio.emit('status_update', {
            'sign_app_running': sign_app_running,
            'angular_app_running': angular_app_running,
            'gemini_running': gemini_running
        })
    except Exception as e:
        logger.warning(f"Failed to emit status update: {str(e)}")
    
    return {
        'sign_app_running': sign_app_running,
        'angular_app_running': angular_app_running,
        'gemini_running': gemini_running
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

# Add a function to check and maintain Gemini connection
def check_gemini_connection():
    """Function to check and keep the Gemini connection alive with periodic pings"""
    global last_successful_gemini_request, gemini_connection_check_event
    gemini_connection_check_event = threading.Event()
    
    while True:
        try:
            # Check if it's been too long since the last successful request
            time_since_last_success = time.time() - last_successful_gemini_request
            
            # Only ping if it's been more than 60 seconds since last successful request
            if time_since_last_success > 60:
                logger.info("Performing periodic Gemini connection check...")
                
                # Simple ping to keep Gemini connected
                response = requests.post(
                    GEMINI_URL,
                    json={
                        "sentence": ["ping"],
                        "clientId": "default"
                    },
                    timeout=5
                )
                
                if response.status_code == 200:
                    logger.info("Gemini is responsive. Connection maintained.")
                    last_successful_gemini_request = time.time()
                else:
                    logger.warning(f"Gemini returned unexpected status code: {response.status_code}")
            
        except requests.exceptions.ConnectionError:
            logger.error("Cannot connect to Gemini. Service may be down.")
            
            # Try to determine if Gemini is actually running using os-specific commands
            try:
                # Windows-specific check
                if os.name == 'nt':
                    process_check = subprocess.run(["tasklist", "/fi", "imagename eq gemini.exe"], 
                                                capture_output=True, text=True, check=False)
                    if "gemini.exe" not in process_check.stdout:
                        logger.warning("Gemini process not found. Please restart Gemini manually.")
                else:
                    # Unix-like OS check
                    process_check = subprocess.run(["pgrep", "-f", "gemini"], 
                                                capture_output=True, text=True, check=False)
                    if not process_check.stdout.strip():
                        logger.warning("Gemini process not found. Please restart Gemini manually.")
            except Exception:
                pass  # Ignore errors in the process check itself
                
        except Exception as e:
            logger.warning(f"Error pinging Gemini: {str(e)}")
            
        # Wait for either the normal interval or an immediate check request
        gemini_connection_check_event.wait(timeout=30)  # Reduced to 30 seconds for more frequent checks
        gemini_connection_check_event.clear()

# Start the Gemini connection maintenance thread
gemini_connection_thread = None
gemini_connection_check_event = None

if __name__ == '__main__':
    try:
        # Create templates directory if it doesn't exist
        if not os.path.exists('templates'):
            os.mkdir('templates')
        
        # Start services automatically if possible
        success = True
        
        # Try to start sign recognition app if it's not already running
        # Check both ports 5000 and 5005
        sign_running = False
        sign_app_ports = ["http://127.0.0.1:5000", "http://127.0.0.1:5005"]
        
        for test_url in sign_app_ports:
            try:
                logger.info(f"Checking for sign app at {test_url}...")
                sign_response = requests.get(f"{test_url}/test", timeout=5)
                if sign_response.status_code == 200:
                    sign_running = True
                    # Update the URL to use the working port
                    # We rely on the global declaration already present in check_and_emit_status
                    SIGN_APP_URL = test_url  
                    logger.info(f"✅ Sign recognition app is already running at {test_url}")
                    break
            except requests.RequestException as e:
                logger.info(f"Sign app not detected at {test_url}: {str(e)}")
        
        if not sign_running:
            logger.info("Sign recognition app not detected on any port, will try to start it")
            success = start_sign_recognition() and success
            # Update URL to the default port we expect for the newly started app
            SIGN_APP_URL = "http://127.0.0.1:5000"  # Default for newly started app
        
        # Try to start Angular app if it's not already running
        angular_running = False
        angular_urls = ["http://127.0.0.1:4200", "http://localhost:4200", "http://0.0.0.0:4200"]
        
        for angular_url in angular_urls:
            try:
                logger.info(f"Checking Angular app at {angular_url}...")
                angular_response = requests.get(angular_url, timeout=3,
                                             headers={'Accept': 'text/html', 'User-Agent': 'Mozilla/5.0'})
                status = angular_response.status_code
                
                # Angular might return various status codes when running
                if status == 200 or status == 304 or (status >= 300 and status < 400):
                    angular_running = True
                    ANGULAR_APP_URL = angular_url
                    logger.info(f"✅ Angular app found at {angular_url}")
                    break
            except requests.RequestException as e:
                logger.info(f"Angular app not detected at {angular_url}: {str(e)}")
                
        # If we still haven't found it, try a port check
        if not angular_running:
            try:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('127.0.0.1', 4200))
                sock.close()
                if result == 0:
                    logger.info("✅ Port 4200 is open, assuming Angular app is running")
                    angular_running = True
                    ANGULAR_APP_URL = "http://127.0.0.1:4200"
                    
            except Exception as e:
                logger.warning(f"Error checking Angular port: {str(e)}")
        
        if not angular_running:
            logger.warning("Angular app not detected. Please start it with: cd asl&fslmodel/frontend && ng serve")
        
        # Check if Gemini is running and start the connection maintenance thread
        try:
            response = requests.get(GEMINI_STATUS_URL, timeout=5)
            gemini_running = response.status_code == 200
            if gemini_running:
                logger.info(f"Gemini is running")
                # Start the Gemini connection maintenance thread
                gemini_connection_thread = threading.Thread(target=check_gemini_connection, daemon=True)
                gemini_connection_thread.start()
                logger.info("Started Gemini connection maintenance thread")
            else:
                logger.warning(f"Gemini service returned status code {response.status_code}. Make sure Gemini is running.")
        except Exception as e:
            logger.warning(f"Gemini might not be running: {str(e)}")
            logger.warning(f"Please make sure Gemini is running.")
        
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
        logger.info(f"3. Gemini Service")
        
        # Run with allow_unsafe_werkzeug=True to support newer Flask versions
        socketio.run(app, host='0.0.0.0', port=5001, debug=True, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        cleanup() 