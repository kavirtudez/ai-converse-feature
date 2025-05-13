from flask import Flask, request, jsonify, render_template, make_response
from flask_cors import CORS
import tensorflow as tf
import numpy as np
import cv2
import mediapipe as mp
import base64
import json
import logging
import os
from collections import deque
import threading
import queue
import time
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Suppress MediaPipe warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'  # Suppress TensorFlow logging
import absl.logging
absl.logging.set_verbosity(absl.logging.ERROR)

# Configure TensorFlow for better performance
tf.config.threading.set_inter_op_parallelism_threads(2)
tf.config.threading.set_intra_op_parallelism_threads(2)

# Create the Flask app with CORS options
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True, allow_headers="*", expose_headers="*")

# Add OPTIONS method handler to all routes for CORS preflight requests
@app.route('/', methods=['OPTIONS'])
@app.route('/<path:path>', methods=['OPTIONS'])
def options_handler(path=None):
    response = make_response()
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,X-Requested-With')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# Initialize MediaPipe with optimized settings
mp_holistic = mp.solutions.holistic
holistic = mp_holistic.Holistic(
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
    model_complexity=0,  # Reduced complexity for better performance
    enable_segmentation=False,
    refine_face_landmarks=False,
    static_image_mode=False
)

# Load the model
try:
    model = tf.keras.models.load_model('action.h5')
    # Optimize model for inference
    model.compile(optimizer='adam', loss='categorical_crossentropy', metrics=['accuracy'])
    logger.info("Model loaded successfully")
except Exception as e:
    logger.error(f"Error loading model: {e}")
    raise

# Define actions and colors for visualization
actions = ['hello', 'thanks', 'iloveyou']
colors = [(245,117,16), (117,245,16), (16,117,245)]

# Define Tagalog translations
tagalog_labels = {
    'hello': 'kamusta',
    'thanks': 'salamat',
    'iloveyou': 'mahal kita'
}

# For converting back from Tagalog to English (for model processing)
english_labels = {
    'kamusta': 'hello',
    'salamat': 'thanks',
    'mahal kita': 'iloveyou'
}

# Create a sequence buffer for each client
sequence_buffer = {}
prediction_queue = queue.Queue()

# Initialize client buffer safely with explicit types
def init_client_buffer():
    """Create a new buffer for a client with proper data types"""
    return {
        'frames': deque(maxlen=30),
        'predictions': deque(maxlen=10),
        'sentence': deque(maxlen=5),
        'last_prediction': ('Waiting for hands...', 0.0, None, False),
        'current_action': None,
        'current_action_start_time': None,
        'consecutive_predictions': 0,
        'last_action': None,
        'empty_frame_counter': 0,
        'previous_results': None,
        'motion_history': deque(maxlen=10),
        'last_iloveyou_time': 0,  # Track when we last detected "iloveyou"
        'iloveyou_cooldown': 2.0  # Seconds to wait before allowing another "iloveyou" detection
    }

# Constants for prediction stability
CONFIDENCE_THRESHOLD = 0.65  # Lowered threshold to detect more quickly
HIGH_CONFIDENCE_THRESHOLD = 0.90  # Lowered to detect 'iloveyou' better
MIN_PREDICTION_TIME = 0.5  # Reduced time to make predictions faster
MIN_CONSECUTIVE_PREDICTIONS = 3  # Reduced number of consecutive predictions needed
MAX_EMPTY_FRAMES = 5  # Maximum number of frames without hands before resetting
VALID_HAND_VISIBILITY_THRESHOLD = 0.2  # Reduced from 0.8 - much more lenient visibility requirement
MOTION_THRESHOLD = 0.025  # Increased from 0.02 - requiring more motion for dynamic signs

# Sign-specific settings
SIGN_TYPES = {
    'hello': 'dynamic',  # Dynamic sign that needs motion
    'thanks': 'dynamic', # Dynamic sign that needs motion
    'iloveyou': 'static' # Static sign that needs proper hand configuration
}

# More balanced weights - reduce iloveyou weight even more
SIGN_WEIGHTS = {
    'hello': 1.1,    # Boost to hello
    'thanks': 1.1,   # Boost to thanks
    'iloveyou': 0.85  # Further reduction for iloveyou to prevent over-detection
}

def extract_keypoints(results):
    try:
        pose = np.array([[res.x, res.y, res.z, res.visibility] for res in results.pose_landmarks.landmark]).flatten() if results.pose_landmarks else np.zeros(33*4)
        face = np.array([[res.x, res.y, res.z] for res in results.face_landmarks.landmark]).flatten() if results.face_landmarks else np.zeros(468*3)
        lh = np.array([[res.x, res.y, res.z] for res in results.left_hand_landmarks.landmark]).flatten() if results.left_hand_landmarks else np.zeros(21*3)
        rh = np.array([[res.x, res.y, res.z] for res in results.right_hand_landmarks.landmark]).flatten() if results.right_hand_landmarks else np.zeros(21*3)
        return np.concatenate([pose, face, lh, rh])
    except Exception as e:
        logger.error(f"Error extracting keypoints: {e}")
        return None

def calculate_hand_motion(current_hand, previous_hand):
    """Calculate the amount of motion between two hand landmark frames"""
    if current_hand is None or previous_hand is None:
        return 0
    
    # Calculate Euclidean distance for each landmark point
    total_motion = 0
    for i in range(len(current_hand.landmark)):
        curr = current_hand.landmark[i]
        prev = previous_hand.landmark[i]
        
        # Distance in 3D space
        dist = np.sqrt((curr.x - prev.x)**2 + (curr.y - prev.y)**2 + (curr.z - prev.z)**2)
        total_motion += dist
    
    # Return average motion
    return total_motion / len(current_hand.landmark)

def has_hands(results):
    """Check if hands are present in the frame with simpler, more lenient detection"""
    # Most basic check - are any hand landmarks detected?
    if results.left_hand_landmarks is None and results.right_hand_landmarks is None:
        return False
    
    # If we have hands, do some basic validation but be very lenient
    if results.left_hand_landmarks:
        # Just check that some fingers are visible (not just wrist)
        return True
    
    if results.right_hand_landmarks:
        # Just check that some fingers are visible (not just wrist)
        return True
    
    return False

def check_sign_validity(predicted_sign, current_results, previous_results, motion_history):
    """Check if the predicted sign meets the criteria for its type (dynamic vs static)"""
    sign_type = SIGN_TYPES.get(predicted_sign, 'dynamic')
    
    # Convert any NumPy values in motion_history to Python float
    motion_history = [float(m) if hasattr(m, 'dtype') else m for m in motion_history]
    
    # Special handling for specific signs
    if predicted_sign == 'hello':
        # For "hello" we expect hand near forehead 
        if current_results and current_results.right_hand_landmarks:
            landmarks = current_results.right_hand_landmarks.landmark
            # Check if hand is near the forehead height (y position)
            if len(landmarks) >= 21:
                wrist = landmarks[0]
                # Get nose position as reference for face/head
                nose_y = None
                if current_results.pose_landmarks:
                    nose = current_results.pose_landmarks.landmark[0]  # Nose landmark
                    nose_y = nose.y
                
                # Check if hand is near forehead height (above nose)
                hand_near_forehead = False
                if nose_y:
                    # Hand should be near or above nose height
                    hand_near_forehead = wrist.y <= nose_y + 0.05
                
                # Check for some motion but not too much
                if len(motion_history) >= 3:
                    avg_motion = sum(motion_history[-3:]) / 3
                    good_motion = MOTION_THRESHOLD * 0.5 < avg_motion < MOTION_THRESHOLD * 2.0
                    
                    return bool(hand_near_forehead and good_motion)
        
        # Fallback to motion-only check
        if len(motion_history) >= 3:
            avg_motion = sum(motion_history[-3:]) / 3
            return bool(avg_motion > MOTION_THRESHOLD * 0.8)
    
    elif predicted_sign == 'thanks':
        # For "thanks" we expect fingers tapping on chin, potentially with both hands
        
        # Check if hands are near chin height
        hands_near_chin = False
        if current_results:
            # Check for chin/mouth position in face landmarks
            chin_y = None
            if current_results.face_landmarks:
                # Use bottom lip as reference for chin
                lips = [current_results.face_landmarks.landmark[i] for i in range(0, 17)]  # Lower face contour
                if lips:
                    chin_y = max(lip.y for lip in lips)  # Bottom of face
            
            # Check if either or both hands are near chin
            left_hand_near_chin = False
            right_hand_near_chin = False
            
            if current_results.left_hand_landmarks and chin_y:
                left_fingers = [current_results.left_hand_landmarks.landmark[i] for i in range(8, 21, 4)]  # Fingertips
                left_hand_near_chin = any(abs(finger.y - chin_y) < 0.1 for finger in left_fingers)
                
            if current_results.right_hand_landmarks and chin_y:
                right_fingers = [current_results.right_hand_landmarks.landmark[i] for i in range(8, 21, 4)]  # Fingertips
                right_hand_near_chin = any(abs(finger.y - chin_y) < 0.1 for finger in right_fingers)
                
            hands_near_chin = left_hand_near_chin or right_hand_near_chin
            
            # Check for appropriate motion (tapping)
            if len(motion_history) >= 3:
                avg_motion = sum(motion_history[-3:]) / 3
                good_motion = MOTION_THRESHOLD * 0.6 < avg_motion < MOTION_THRESHOLD * 1.5
                
                return bool(hands_near_chin and good_motion)
        
        # Fallback to motion-only check
        if len(motion_history) >= 3:
            avg_motion = sum(motion_history[-3:]) / 3
            return bool(MOTION_THRESHOLD * 0.5 < avg_motion < MOTION_THRESHOLD * 1.5)
    
    elif predicted_sign == 'iloveyou':
        # For "iloveyou" we expect extended thumb, index, and pinky - static pose
        if len(motion_history) >= 3:
            avg_motion = sum(motion_history[-3:]) / 3
            
            # Low motion threshold for this static sign
            low_motion = avg_motion < MOTION_THRESHOLD * 0.5
            
            # Check for proper hand configuration - specific to "iloveyou" sign
            proper_hand_config = False
            
            # Check if we have hand landmarks to verify
            if current_results and (current_results.left_hand_landmarks or current_results.right_hand_landmarks):
                # Preferably check right hand first, then left
                hand_landmarks = current_results.right_hand_landmarks or current_results.left_hand_landmarks
                
                # Check for "I love you" sign configuration
                if hand_landmarks:
                    landmarks = hand_landmarks.landmark
                    if len(landmarks) >= 21:
                        # Check specific finger extensions for the ILY sign
                        thumb_tip = landmarks[4]   # Thumb tip
                        index_tip = landmarks[8]   # Index finger tip
                        middle_tip = landmarks[12] # Middle finger tip
                        ring_tip = landmarks[16]   # Ring finger tip
                        pinky_tip = landmarks[20]  # Pinky tip
                        wrist = landmarks[0]       # Wrist reference
                        
                        # Critical finger positions for ILY sign
                        thumb_extended = thumb_tip.y < wrist.y - 0.05  # Thumb must be clearly extended upward
                        index_extended = index_tip.y < wrist.y - 0.1   # Index must be clearly extended upward
                        middle_curled = middle_tip.y > index_tip.y + 0.05  # Middle must be clearly curled
                        ring_curled = ring_tip.y > index_tip.y + 0.05      # Ring must be clearly curled
                        pinky_extended = pinky_tip.y < ring_tip.y - 0.08  # Pinky must be clearly extended
                        
                        # All conditions must be met for a proper hand configuration
                        proper_hand_config = (thumb_extended and 
                                             index_extended and 
                                             middle_curled and 
                                             ring_curled and 
                                             pinky_extended)
                            
            # Need BOTH low motion AND proper hand configuration for "iloveyou"
            return bool(low_motion and proper_hand_config)
    
    # Default handling for sign types
    if sign_type == 'static':
        # For generic static signs, we want hands to be stable with minimal motion
        if len(motion_history) >= 2:
            avg_motion = sum(motion_history[-2:]) / 2
            return bool(avg_motion < MOTION_THRESHOLD * 1.5)
        return True
    
    elif sign_type == 'dynamic':
        # For generic dynamic signs, we expect some motion
        if len(motion_history) >= 2:
            avg_motion = sum(motion_history[-2:]) / 2
            return bool(avg_motion > MOTION_THRESHOLD * 0.5)
        return True
    
    return True

def prediction_worker():
    while True:
        try:
            client_id, sequence, current_results, previous_results, motion_history = prediction_queue.get()
            if sequence is None:
                break
            
            # Make prediction
            prediction = model.predict(sequence, verbose=0)
            scores = prediction[0]
            
            # Get the raw prediction first - before applying any weights
            raw_max_score = float(np.max(scores))
            raw_predicted_idx = int(np.argmax(scores))
            raw_predicted_action = actions[raw_predicted_idx]
            
            # Add stricter validation for the iloveyou sign
            # Only apply weight adjustments if the confidence isn't extremely high already
            if raw_predicted_action == 'iloveyou' and raw_max_score < 0.95:
                # Check if there's enough finger visibility for iloveyou sign
                has_sufficient_fingers = False
                
                if current_results.right_hand_landmarks:
                    # For "iloveyou" sign, typically the pinky, index and thumb should be extended
                    # Check visibility and position of these key landmarks
                    landmarks = current_results.right_hand_landmarks.landmark
                    
                    # More strict verification of finger positions
                    if len(landmarks) >= 21:  # Make sure we have enough landmarks
                        # Check positions of thumb tip, index tip, and pinky tip relative to palm
                        thumb_tip = landmarks[4]    # Thumb tip
                        index_tip = landmarks[8]    # Index finger tip
                        middle_tip = landmarks[12]  # Middle finger tip
                        ring_tip = landmarks[16]    # Ring finger tip
                        pinky_tip = landmarks[20]   # Pinky tip
                        wrist = landmarks[0]        # Wrist/palm center
                        
                        # Much stricter check for proper finger configuration
                        if (index_tip.y < wrist.y - 0.1 and      # Index clearly extended up
                            pinky_tip.y < wrist.y - 0.08 and     # Pinky clearly extended up
                            abs(thumb_tip.x - wrist.x) > 0.08 and # Thumb clearly extended to side
                            middle_tip.y > index_tip.y + 0.05 and # Middle clearly curled
                            ring_tip.y > index_tip.y + 0.05):     # Ring clearly curled
                            has_sufficient_fingers = True
                
                # If we don't have proper finger configuration, reduce the weight further
                if not has_sufficient_fingers:
                    SIGN_WEIGHTS['iloveyou'] = 0.7  # Much lower weight if fingers don't match
                else:
                    SIGN_WEIGHTS['iloveyou'] = 0.85  # Regular reduced weight with good finger config
            
            # Apply weights to balance sign detection
            weighted_scores = scores.copy()
            for i, action in enumerate(actions):
                weighted_scores[i] *= SIGN_WEIGHTS.get(action, 1.0)
            
            # Get top prediction
            max_score = float(np.max(weighted_scores))
            predicted_idx = int(np.argmax(weighted_scores))
            predicted_action = actions[predicted_idx]
            
            # Add extra validation for "iloveyou" sign to prevent over-detection
            if predicted_action == 'iloveyou':
                # If the raw score for "iloveyou" is very close to other signs, be more skeptical
                if raw_predicted_action != 'iloveyou' and raw_max_score > 0.65:  # Lower threshold to reject more easily
                    # Use raw prediction instead
                    predicted_action = raw_predicted_action
                    predicted_idx = raw_predicted_idx
                    max_score = raw_max_score
                
                # Require higher confidence threshold for iloveyou
                if max_score < CONFIDENCE_THRESHOLD * 1.25:  # Even higher confidence needed (25% more)
                    # Reduce confidence even more
                    max_score *= 0.8  # Further reduce confidence for borderline cases
            
            # Add protection against invalid predictions
            if predicted_idx >= len(actions):
                logger.error(f"Invalid prediction index: {predicted_idx}, max allowed: {len(actions)-1}")
                # Fall back to highest unweighted score
                predicted_idx = int(np.argmax(scores))
                predicted_action = actions[predicted_idx]
                max_score = float(scores[predicted_idx])
            
            # Check if the predicted sign is valid based on its type (static vs dynamic)
            is_valid_sign = check_sign_validity(predicted_action, current_results, previous_results, motion_history)
            
            # Add extra validation for "iloveyou" - require near stillness
            if predicted_action == 'iloveyou' and is_valid_sign:
                # If there's too much movement, it's probably not a static sign
                recent_motion = sum(motion_history[-3:]) / 3 if len(motion_history) >= 3 else 0
                if recent_motion > MOTION_THRESHOLD * 0.5:  # Even stricter motion threshold (reduced from 0.8)
                    is_valid_sign = False
            
            # Adjust confidence for invalid signs
            if not is_valid_sign:
                max_score *= 0.65  # Further reduce confidence for invalid signs (from 0.7)
            
            # Convert NumPy types to Python types to avoid serialization issues
            max_score = float(max_score)
            is_valid_sign = bool(is_valid_sign)
            
            # Store the original scores for confidence display
            display_max_score = float(np.max(scores))
            
            # Copy scores to a regular Python list to avoid NumPy serialization issues
            scores_list = [float(s) for s in scores]
            
            # Store the prediction with Python native types (not NumPy types)
            sequence_buffer[client_id]['last_prediction'] = (predicted_action, display_max_score, scores_list, is_valid_sign)
            
        except Exception as e:
            logger.error(f"Error in prediction worker: {str(e)}")
            import traceback
            logger.error(f"Detailed error: {traceback.format_exc()}")
        finally:
            prediction_queue.task_done()

# Start prediction worker thread
prediction_thread = threading.Thread(target=prediction_worker, daemon=True)
prediction_thread.start()

# Define a function to notify sign_conversation.py of sentence updates
def notify_conversation_service(client_id, sentence):
    """Send sentence updates to the conversation service"""
    try:
        # Only send if the sentence has content
        if sentence:
            logger.info(f"Notifying conversation service of sentence update: {sentence}")
            requests.post("http://localhost:5001/api/sentence_update", 
                         json={"clientId": client_id, "sentence": sentence},
                         timeout=0.5)  # Short timeout to avoid blocking
    except Exception as e:
        # Don't let notification failures affect the main app
        logger.warning(f"Failed to notify conversation service: {str(e)}")

# Add function to send sentence to Gemini instead of Ollama
def send_to_gemini(client_id, sentence):
    """Send the current sentence to Gemini"""
    try:
        if not sentence:
            logger.warning("Cannot send empty sentence to Gemini")
            return {"success": False, "error": "Empty sentence"}
            
        logger.info(f"Sending sentence to Gemini: {sentence}")
        
        # Call the Gemini integration service directly
        response = requests.post(
            "http://localhost:5002/process_sign_sentence",
            json={"clientId": client_id, "sentence": sentence},
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success", False):
                logger.info(f"Successfully sent to Gemini, response: {data.get('response')}")
                return {"success": True, "response": data.get("response")}
            else:
                error = data.get("error", "Unknown error")
                logger.warning(f"Failed to send to Gemini: {error}")
                return {"success": False, "error": error}
        else:
            logger.warning(f"Failed to send to Gemini, status code: {response.status_code}")
            return {"success": False, "error": f"Status code: {response.status_code}"}
            
    except Exception as e:
        logger.error(f"Error sending to Gemini: {str(e)}")
        return {"success": False, "error": str(e)}

# Add new route for sending to Gemini
@app.route('/send_to_gemini', methods=['POST'])
def api_send_to_gemini():
    """API endpoint to send the current sentence to Gemini"""
    client_id = request.json.get('clientId', 'default')
    
    if client_id in sequence_buffer:
        sentence = list(sequence_buffer[client_id]['sentence'])
        result = send_to_gemini(client_id, sentence)
        
        if result["success"]:
            return jsonify({
                "success": True,
                "sentence": sentence,
                "response": result["response"]
            })
        else:
            return jsonify({
                "success": False,
                "error": result["error"]
            }), 500
    
    return jsonify({
        "success": False,
        "error": "Client ID not found"
    }), 404

# Keep the old function for compatibility, but forward to the new implementation
@app.route('/send_to_ollama', methods=['POST'])
def api_send_to_ollama():
    """Legacy API endpoint to send the current sentence to Ollama (now forwards to Gemini)"""
    logger.info("Received request to old Ollama endpoint, forwarding to Gemini")
    return api_send_to_gemini()

@app.route('/')
def home():
    return render_template('index.html', language='english')

@app.route('/tagalog')
def tagalog():
    return render_template('index.html', language='tagalog')

@app.route('/predict', methods=['POST'])
def predict():
    try:
        # Get the image data from the request
        data = request.json
        image_data = data['image'].split(',')[1]
        image_bytes = base64.b64decode(image_data)
        client_id = data.get('clientId', 'default')
        language = data.get('language', 'english')
        
        # Initialize sequence buffer for new clients
        if client_id not in sequence_buffer:
            sequence_buffer[client_id] = init_client_buffer()
        
        # Convert to numpy array
        nparr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Convert to RGB for MediaPipe
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Make detection
        results = holistic.process(frame_rgb)
        
        # Get previous results for motion calculation
        previous_results = sequence_buffer[client_id].get('previous_results')
        
        # Calculate hand motion if both current and previous frames have hands
        motion_value = 0
        if previous_results and results:
            left_motion = calculate_hand_motion(results.left_hand_landmarks, previous_results.left_hand_landmarks) if results.left_hand_landmarks and previous_results.left_hand_landmarks else 0
            right_motion = calculate_hand_motion(results.right_hand_landmarks, previous_results.right_hand_landmarks) if results.right_hand_landmarks and previous_results.right_hand_landmarks else 0
            motion_value = max(left_motion, right_motion)
            
        # Store motion value in history
        sequence_buffer[client_id]['motion_history'].append(motion_value)
        
        # Store current results for next frame
        sequence_buffer[client_id]['previous_results'] = results
        
        # Check if hands are present - use a much more lenient check
        hands_present = has_hands(results)
        
        # Extract keypoints
        keypoints = extract_keypoints(results)
        if keypoints is None:
            return jsonify({
                'error': 'Failed to extract keypoints',
                'success': False
            }), 400
        
        # Add keypoints to sequence buffer
        sequence_buffer[client_id]['frames'].append(keypoints)
        
        # Get current prediction
        predicted_action, max_score, scores, is_valid_sign = sequence_buffer[client_id]['last_prediction']
        
        # Track empty frames (no hands) - but be more lenient
        if not hands_present:
            sequence_buffer[client_id]['empty_frame_counter'] += 1
        else:
            sequence_buffer[client_id]['empty_frame_counter'] = 0
            
        # Reset if too many empty frames - increased from 5 to be more lenient
        if sequence_buffer[client_id]['empty_frame_counter'] > MAX_EMPTY_FRAMES * 2:
            sequence_buffer[client_id]['predictions'].clear()
            sequence_buffer[client_id]['current_action'] = None
            sequence_buffer[client_id]['current_action_start_time'] = None
            sequence_buffer[client_id]['consecutive_predictions'] = 0
            
        # If we have enough frames, queue a new prediction
        if len(sequence_buffer[client_id]['frames']) == 30:
            sequence = np.array(list(sequence_buffer[client_id]['frames']))
            sequence = np.expand_dims(sequence, axis=0)
            
            # Always make predictions, even if hands might not be perfectly detected
            prediction_queue.put((
                client_id, 
                sequence, 
                results, 
                previous_results, 
                list(sequence_buffer[client_id]['motion_history'])
            ))
            
            # Add prediction to buffer
            if scores is not None:
                # Still consider all predictions, even if sign validation is uncertain
                sequence_buffer[client_id]['predictions'].append(np.argmax(scores))
                
                # Check for high confidence predictions
                if max_score >= HIGH_CONFIDENCE_THRESHOLD:
                    current_action = predicted_action
                    
                    # Check cooldown for "iloveyou" sign to prevent rapid repeated detection
                    current_time = time.time()
                    if current_action == 'iloveyou':
                        last_iloveyou_time = sequence_buffer[client_id]['last_iloveyou_time']
                        cooldown_period = sequence_buffer[client_id]['iloveyou_cooldown']
                        
                        # If we're still in cooldown, don't allow another "iloveyou" detection
                        if current_time - last_iloveyou_time < cooldown_period:
                            # Skip this detection
                            current_action = None
                        else:
                            # Update the last detection time
                            sequence_buffer[client_id]['last_iloveyou_time'] = current_time
                    
                    # Only add to sentence if it's valid and not in cooldown
                    if current_action and (len(sequence_buffer[client_id]['sentence']) == 0 or 
                        current_action != sequence_buffer[client_id]['sentence'][-1]):
                        sequence_buffer[client_id]['sentence'].append(current_action)
                        sequence_buffer[client_id]['last_action'] = current_action
                        # Reset tracking for next prediction
                        sequence_buffer[client_id]['current_action'] = None
                        sequence_buffer[client_id]['consecutive_predictions'] = 0
                        
                        # Notify conversation service of updated sentence
                        notify_conversation_service(client_id, list(sequence_buffer[client_id]['sentence']))
                        
                # Check if we have consistent predictions
                elif len(sequence_buffer[client_id]['predictions']) >= 3:  # Reduced from 5 for even faster detection
                    # Use a majority vote from recent predictions
                    recent_preds = list(sequence_buffer[client_id]['predictions'])[-3:]
                    unique_preds, counts = np.unique(recent_preds, return_counts=True)
                    majority_idx = np.argmax(counts)
                    majority_prediction = unique_preds[majority_idx]
                    majority_count = counts[majority_idx]
                    
                    # If we have a majority and confidence is high enough - be more lenient
                    if majority_count >= 2 and max_score > CONFIDENCE_THRESHOLD * 0.9:  # Reduced threshold
                        current_action = actions[majority_prediction]
                        current_time = time.time()
                        
                        # Check cooldown for "iloveyou" sign
                        if current_action == 'iloveyou':
                            last_iloveyou_time = sequence_buffer[client_id]['last_iloveyou_time']
                            cooldown_period = sequence_buffer[client_id]['iloveyou_cooldown']
                            
                            # If we're still in cooldown, don't allow another "iloveyou" detection
                            if current_time - last_iloveyou_time < cooldown_period:
                                # Skip this detection
                                current_action = None
                        
                        # Only proceed if we have a valid action after cooldown check
                        if current_action:
                            # Initialize or update prediction tracking
                            if sequence_buffer[client_id]['current_action'] != current_action:
                                sequence_buffer[client_id]['consecutive_predictions'] = 1
                                sequence_buffer[client_id]['current_action'] = current_action
                                sequence_buffer[client_id]['current_action_start_time'] = current_time
                            else:
                                sequence_buffer[client_id]['consecutive_predictions'] += 1
                                
                                # Only update the sentence if we have enough consecutive predictions
                                # and enough time has passed (less strict now)
                                if (sequence_buffer[client_id]['consecutive_predictions'] >= MIN_CONSECUTIVE_PREDICTIONS - 1 and
                                    current_time - sequence_buffer[client_id]['current_action_start_time'] >= MIN_PREDICTION_TIME * 0.8):
                                    
                                    # Add to sentence if it's a new sign or different from the last one
                                    if (len(sequence_buffer[client_id]['sentence']) == 0 or 
                                        current_action != sequence_buffer[client_id]['sentence'][-1]):
                                        
                                        # For "iloveyou", update the last detection time
                                        if current_action == 'iloveyou':
                                            sequence_buffer[client_id]['last_iloveyou_time'] = current_time
                                            
                                        sequence_buffer[client_id]['sentence'].append(current_action)
                                        sequence_buffer[client_id]['last_action'] = current_action
                                        # Reset for next prediction
                                        sequence_buffer[client_id]['current_action'] = None
                                        sequence_buffer[client_id]['consecutive_predictions'] = 0
                                        
                                        # Notify conversation service of updated sentence
                                        notify_conversation_service(client_id, list(sequence_buffer[client_id]['sentence']))
            
            # Handle case when hands might not be perfectly detected but we're still getting predictions
            elif not hands_present and sequence_buffer[client_id]['empty_frame_counter'] > MAX_EMPTY_FRAMES * 2:
                # Only reset completely after a longer period with no hands
                predicted_action = 'Waiting for hands...'
                max_score = 0.0
                is_valid_sign = False
                sequence_buffer[client_id]['last_prediction'] = (predicted_action, max_score, None, is_valid_sign)
        
        # Add prediction text and background for better visibility
        cv2.rectangle(frame, (0,0), (frame.shape[1], 40), (245, 117, 16), -1)
        sentence_text = ' '.join(sequence_buffer[client_id]['sentence'])
        cv2.putText(frame, sentence_text, (3,30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2, cv2.LINE_AA)
        
        # Add prediction and confidence
        prediction_text = f"{predicted_action} ({max_score:.2f})"
        color = (0, 255, 0) if is_valid_sign else (0, 165, 255)  # Green if valid, orange if not
        cv2.putText(frame, prediction_text, (frame.shape[1] - 250, 70), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        
        # Add motion indicator (for debugging)
        motion_value = 0 if not sequence_buffer[client_id]['motion_history'] else sequence_buffer[client_id]['motion_history'][-1]
        motion_text = f"Motion: {motion_value:.4f}"
        cv2.putText(frame, motion_text, (10, frame.shape[0] - 10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # Convert frame back to base64 with reduced quality
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        frame_base64 = base64.b64encode(buffer).decode('utf-8')
        
        # Format response depending on language
        display_prediction = predicted_action
        display_sentence = list(sequence_buffer[client_id]['sentence'])
        
        if language == 'tagalog' and predicted_action in tagalog_labels:
            display_prediction = tagalog_labels[predicted_action]
            display_sentence = [tagalog_labels[sign] for sign in sequence_buffer[client_id]['sentence'] if sign in tagalog_labels]
            
        # Special case for waiting message
        if predicted_action == 'Waiting for hands...':
            display_prediction = 'Naghihintay ng kamay...' if language == 'tagalog' else predicted_action
        
        # Fix the NumPy bool_ serialization issue - convert to Python bool
        is_valid_sign_python = bool(is_valid_sign)
        
        # Return response with converted Python values instead of NumPy types
        return jsonify({
            'prediction': display_prediction,
            'confidence': float(max_score),
            'frame': f'data:image/jpeg;base64,{frame_base64}',
            'frames_collected': int(len(sequence_buffer[client_id]['frames'])),
            'sentence': display_sentence,
            'is_valid_sign': is_valid_sign_python,
            'success': True
        })
        
    except Exception as e:
        logger.error(f"Error in predict endpoint: {str(e)}")
        # Give more detailed error information
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Detailed error: {error_details}")
        
        return jsonify({
            'error': str(e),
            'details': error_details if app.debug else 'Enable debug mode for details',
            'success': False
        }), 500

@app.route('/get_sentence', methods=['GET'])
def get_sentence():
    client_id = request.args.get('clientId', 'default')
    if client_id in sequence_buffer:
        sentence = list(sequence_buffer[client_id]['sentence'])
        return jsonify({
            'sentence': sentence,
            'success': True
        })
    return jsonify({
        'sentence': [],
        'success': False
    })

@app.route('/clear_sentence', methods=['POST'])
def clear_sentence():
    client_id = request.json.get('clientId', 'default')
    if client_id in sequence_buffer:
        sequence_buffer[client_id]['sentence'].clear()
        # Notify conversation service of cleared sentence
        notify_conversation_service(client_id, [])
        return jsonify({
            'success': True
        })
    return jsonify({
        'success': False
    })

@app.route('/test', methods=['GET'])
def test():
    return jsonify({
        'status': 'Sign recognition service is running',
        'success': True
    })

@app.route('/test_sign', methods=['POST'])
def test_sign():
    """Test endpoint to simulate sign recognition for debugging"""
    client_id = request.json.get('clientId', 'default')
    sign = request.json.get('sign')
    
    if sign not in actions:
        return jsonify({
            'error': f'Invalid sign: {sign}. Valid signs are: {actions}',
            'success': False
        }), 400
    
    # Initialize sequence buffer for new clients
    if client_id not in sequence_buffer:
        sequence_buffer[client_id] = init_client_buffer()
    
    # Add sign to sentence if not already there
    if sign not in sequence_buffer[client_id]['sentence']:
        sequence_buffer[client_id]['sentence'].append(sign)
        
    return jsonify({
        'sentence': list(sequence_buffer[client_id]['sentence']),
        'success': True
    })

if __name__ == '__main__':
    # Display clear message about which port we're using
    port = 5000
    print(f"\n{'='*50}")
    print(f"STARTING SIGN RECOGNITION APP ON PORT {port}")
    print(f"Access the app at: http://127.0.0.1:{port}")
    print(f"{'='*50}\n")
    
    # Run the app on the specified port - explicitly set host to 0.0.0.0
    app.run(debug=True, port=port, host='0.0.0.0', threaded=True) 