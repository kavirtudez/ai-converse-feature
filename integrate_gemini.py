import logging
import sys
import time
import requests
from flask import Flask, jsonify, request
from gemini_handler import GeminiHandler

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app for the integration
app = Flask(__name__)

# Create an instance of GeminiHandler with API key
gemini = GeminiHandler(model="gemini-pro", api_key="AIzaSyC1NYbUuZLEbVuAfJRQ4-wYtP2a4FgV9_U", max_words=5)

# Default port for sign_conversation.py
SIGN_CONVERSATION_PORT = 5001

# Add a response decorator to ensure CORS headers
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization,X-Requested-With'
    response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
    return response

@app.route('/api/gemini_status', methods=['GET'])
def check_gemini_status():
    """Check if Gemini API is accessible"""
    status = gemini.check_status()
    return jsonify({
        'status': 'running' if status else 'not_running',
        'model': gemini.model,
        'timestamp': time.time()
    })

@app.route('/api/gemini_response', methods=['POST'])
def get_gemini_response():
    """
    Get a response from Gemini
    
    Expected JSON body: {"input": "user input text"}
    Returns: {"response": "gemini response", "success": true}
    """
    try:
        # Get input from request
        data = request.json
        user_input = data.get('input', '')
        
        if not user_input:
            return jsonify({
                'success': False,
                'error': 'No input provided',
                'response': 'Please provide input'
            })
        
        # Get response from Gemini
        response = gemini.get_response(user_input)
        
        # Return formatted response
        return jsonify({
            'success': True,
            'response': response,
            'input': user_input
        })
        
    except Exception as e:
        logger.error(f"Error getting Gemini response: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'response': 'Error processing request'
        }), 500

@app.route('/api/trigger_check', methods=['POST'])
def trigger_connection_check():
    """Force an immediate connection check for Gemini"""
    gemini.trigger_immediate_check()
    return jsonify({
        'success': True,
        'message': 'Connection check triggered'
    })

@app.route('/test', methods=['GET'])
def test_endpoint():
    """Simple test endpoint to verify service is running"""
    return jsonify({
        'status': 'Gemini integration service is running',
        'success': True,
        'timestamp': time.time()
    })

@app.route('/forward_to_sign_conversation', methods=['POST'])
def forward_to_sign_conversation():
    """
    Forward sentence from app.py to sign_conversation.py
    This is a utility method to avoid direct dependencies
    """
    try:
        # Get data from request
        data = request.json
        
        # Forward to sign_conversation.py
        response = requests.post(
            f"http://localhost:{SIGN_CONVERSATION_PORT}/api/sentence_update",
            json=data,
            timeout=3
        )
        
        if response.status_code == 200:
            return jsonify({
                'success': True,
                'message': 'Successfully forwarded to sign_conversation'
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Failed to forward, status code: {response.status_code}'
            }), 502
            
    except Exception as e:
        logger.error(f"Error forwarding to sign_conversation: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/process_sign_sentence', methods=['POST'])
def process_sign_sentence():
    """
    Process a sign language sentence and get a Gemini response
    
    This is a more direct endpoint for app.py to use without going 
    through sign_conversation.py
    """
    try:
        # Get data from request
        data = request.json
        sentence = data.get('sentence', [])
        client_id = data.get('clientId', 'default')
        
        if not sentence:
            return jsonify({
                'success': False,
                'error': 'Empty sentence'
            })
        
        # Join the sentence into a string
        sentence_str = " ".join(sentence)
        logger.info(f"Processing sign sentence: '{sentence_str}'")
        
        # Get response from Gemini
        gemini_response = gemini.get_response(sentence_str)
        logger.info(f"Gemini response: '{gemini_response}'")
        
        # Return the response
        return jsonify({
            'success': True,
            'input': sentence_str,
            'response': gemini_response,
            'clientId': client_id
        })
        
    except Exception as e:
        logger.error(f"Error processing sign sentence: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def main():
    """Main entry point for the Gemini integration service"""
    logger.info("Starting Gemini integration service")
    
    # Check if Gemini API is accessible
    status = gemini.check_status()
    if status:
        logger.info(f"Gemini API is accessible with model {gemini.model}")
        
        # List available models
        try:
            models = genai.list_models()
            model_names = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
            logger.info(f"Available Gemini models: {model_names}")
        except Exception as e:
            logger.warning(f"Could not list models: {e}")
        
        # Test response quality
        test_inputs = ["hello", "thanks", "iloveyou"]
        logger.info("Testing response quality:")
        for test in test_inputs:
            response = gemini.get_response(test)
            logger.info(f"  Input: '{test}' → Response: '{response}'")
            
        logger.info("Response testing complete - all systems operational")
    else:
        logger.warning(f"Gemini API is not accessible or model {gemini.model} is not available")
        logger.warning("Please check your API key and internet connection")
    
    # Run the Flask app
    try:
        logger.info("Gemini integration service running on port 5002")
        logger.info("Use this service to get responses from Gemini with improved stability")
        logger.info("This service works alongside sign_conversation.py without modifying it")
        app.run(host='0.0.0.0', port=5002, debug=True)
    except KeyboardInterrupt:
        logger.info("Shutting down Gemini integration service")
    finally:
        # Clean shutdown
        gemini.shutdown()

if __name__ == "__main__":
    main() 