import logging
import time
import threading
import re
import os
import random
import google.generativeai as genai

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GeminiHandler:
    """
    Handler for Gemini API interactions with improved stability,
    connection maintenance, and strict response formatting.
    """
    
    def __init__(self, model="models/gemini-1.5-flash-8b", api_key="AIzaSyC1NYbUuZLEbVuAfJRQ4-wYtP2a4FgV9_U", max_words=5):
        # Set API key directly or from environment variable
        self.api_key = api_key
        os.environ["GEMINI_API_KEY"] = self.api_key
        
        # Initialize the Gemini client
        genai.configure(api_key=self.api_key)
        
        # Default to models/gemini-1.5-flash-8b which was confirmed working
        self.model = model
        logger.info(f"Using Gemini model: {self.model}")
        self.max_words = max_words
        self.last_successful_request = time.time()
        self.connection_check_event = threading.Event()
        self.connection_thread = None
        self.is_running = True
        self.quota_exceeded = False
        self.retry_after_timestamp = 0
        
        # Start connection maintenance thread
        self.start_connection_maintenance()
    
    def start_connection_maintenance(self):
        """Start the connection maintenance thread if not already running"""
        if not self.connection_thread or not self.connection_thread.is_alive():
            self.connection_thread = threading.Thread(target=self._maintain_connection, daemon=True)
            self.connection_thread.start()
            logger.info(f"Started Gemini connection maintenance thread for model {self.model}")
    
    def _maintain_connection(self):
        """Background thread to maintain a stable connection to Gemini API"""
        check_interval = 30  # Check every 30 seconds
        
        while self.is_running:
            try:
                # Check if it's been too long since the last successful request
                time_since_last = time.time() - self.last_successful_request
                
                # Only ping if it's been more than 60 seconds since last success
                if time_since_last > 60 and not self.quota_exceeded:
                    logger.info("Performing periodic Gemini connection check...")
                    
                    # Simple heartbeat request to check Gemini API connectivity
                    try:
                        # Use generate_content for heartbeat
                        model = genai.GenerativeModel(self.model)
                        response = model.generate_content("ping", generation_config={"max_output_tokens": 10})
                        logger.info("Gemini connection successfully maintained")
                        self.last_successful_request = time.time()
                        self.quota_exceeded = False
                    except Exception as e:
                        error_str = str(e)
                        if "429" in error_str and "quota" in error_str:
                            logger.warning("Quota exceeded during connection check")
                            self.quota_exceeded = True
                            # Try to extract retry delay
                            if "retry_delay" in error_str:
                                try:
                                    retry_seconds = int(re.search(r'retry_delay\s*{\s*seconds:\s*(\d+)', error_str).group(1))
                                    self.retry_after_timestamp = time.time() + retry_seconds
                                    logger.warning(f"Will retry after {retry_seconds} seconds")
                                except (AttributeError, ValueError):
                                    self.retry_after_timestamp = time.time() + 60  # Default 60 seconds
                        elif "404" in error_str and "not found" in error_str.lower():
                            # Model not found error - try to list models and switch to a valid one
                            logger.warning(f"Model {self.model} not found during connection check, attempting to find valid model")
                            try:
                                models = genai.list_models()
                                model_names = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
                                if model_names:
                                    new_model = model_names[0]
                                    logger.info(f"Switching from {self.model} to {new_model}")
                                    self.model = new_model
                            except Exception as list_error:
                                logger.warning(f"Failed to list models: {str(list_error)}")
                        else:
                            logger.warning(f"Gemini connection check failed: {error_str}")
                        
            except Exception as e:
                logger.warning(f"Error in Gemini connection check: {str(e)}")
            
            # Wait for either the normal interval or an immediate check request
            self.connection_check_event.wait(timeout=check_interval)
            self.connection_check_event.clear()
    
    def trigger_immediate_check(self):
        """Force an immediate connection check"""
        if self.connection_check_event:
            self.connection_check_event.set()
    
    def get_response(self, user_input):
        """
        Get a short, concise response from Gemini with strict word limits
        and formatting requirements.
        
        Args:
            user_input: The user's input text
            
        Returns:
            A short response string (max 5 words by default)
        """
        if not user_input:
            return "Please sign something"
        
        # Check if we're currently rate-limited
        if self.quota_exceeded:
            current_time = time.time()
            if current_time < self.retry_after_timestamp:
                wait_time = int(self.retry_after_timestamp - current_time)
                logger.warning(f"Quota still exceeded, need to wait {wait_time} more seconds")
                return self._get_fallback_response()
            else:
                logger.info("Retry period expired, attempting Gemini request")
                self.quota_exceeded = False
        
        try:
            logger.info(f"Sending to Gemini: '{user_input}'")
            
            # Enhanced retry logic with exponential backoff
            max_attempts = 3
            base_wait_time = 1  # Start with 1 second wait
            
            for attempt in range(max_attempts):
                try:
                    # Log retry attempts
                    if attempt > 0:
                        logger.info(f"Retry attempt {attempt+1}/{max_attempts} for Gemini request")
                    
                    # Create system instruction for desired response format
                    system_instruction = "Always respond in less than 5 words. Be simple, friendly, and kind. Do not use emojis, hashtags, or periods. Your responses will be to greetings and expressions of gratitude or affection."
                    
                    # Create a generative model
                    model = genai.GenerativeModel(
                        model_name=self.model,  # Using the corrected model name
                        generation_config={
                            "temperature": 0.7,
                            "max_output_tokens": 30,
                        },
                        system_instruction=system_instruction
                    )
                    
                    # Send the request to Gemini
                    response = model.generate_content(user_input)
                    
                    # Update successful connection timestamp
                    self.last_successful_request = time.time()
                    self.quota_exceeded = False
                    
                    # Extract and post-process response
                    raw_result = response.text.strip()
                    post_processed = self._post_process_response(raw_result)
                    
                    logger.info(f"Gemini raw response: '{raw_result}'")
                    logger.info(f"Post-processed response: '{post_processed}'")
                    return post_processed
                    
                except Exception as e:
                    error_str = str(e)
                    if "429" in error_str and "quota" in error_str:
                        logger.warning(f"Quota exceeded on attempt {attempt+1}")
                        self.quota_exceeded = True
                        
                        # Try to extract retry delay
                        if "retry_delay" in error_str:
                            try:
                                retry_seconds = int(re.search(r'retry_delay\s*{\s*seconds:\s*(\d+)', error_str).group(1))
                                self.retry_after_timestamp = time.time() + retry_seconds
                                logger.warning(f"Will retry after {retry_seconds} seconds")
                                
                                # If this is the last attempt, return fallback response
                                if attempt == max_attempts - 1:
                                    logger.warning("All attempts failed due to quota limits, using fallback")
                                    return self._get_fallback_response()
                                    
                                # Otherwise, wait before retrying
                                time.sleep(min(retry_seconds, 10))  # Wait at most 10 seconds before retrying
                                
                            except (AttributeError, ValueError):
                                # Couldn't parse retry delay, use default backoff
                                if attempt < max_attempts - 1:
                                    wait_time = base_wait_time * (2 ** attempt)
                                    time.sleep(wait_time)
                        
                    else:
                        logger.warning(f"Gemini request error on attempt {attempt+1}: {error_str}")
                        if attempt < max_attempts - 1:
                            wait_time = base_wait_time * (2 ** attempt)  # Exponential backoff
                            time.sleep(wait_time)
            
            # If all attempts failed, provide a fallback response
            logger.warning("All Gemini attempts failed, using fallback response")
            return self._get_fallback_response()
            
        except Exception as e:
            logger.error(f"Error getting Gemini response: {str(e)}")
            return "Please continue"
    
    def _post_process_response(self, raw_response):
        """
        Post-process Gemini's response to limit words and remove unwanted elements.
        """
        if not raw_response:
            return self._get_fallback_response()
        
        # Remove emojis (Unicode ranges for common emoji)
        clean_text = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F700-\U0001F77F\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002702-\U000027B0\U000024C2-\U0001F251]+', '', raw_response)
        
        # Remove hashtags
        clean_text = re.sub(r'#\w+', '', clean_text)
        
        # Remove any remaining special characters except basic punctuation
        clean_text = re.sub(r'[^\w\s.,!?]', '', clean_text)
        
        # Replace multiple spaces with a single space
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        # Remove commas as requested
        clean_text = clean_text.replace(',', '')
        
        # Limit to max_words by taking only the first max_words words
        words = clean_text.split()
        if len(words) > self.max_words:
            words = words[:self.max_words]
        
        result = ' '.join(words)
        
        # If we've stripped everything away or it's too short, use a fallback
        if not result or len(result) < 2:
            return self._get_fallback_response()
        
        # Capitalize first letter for natural-looking response
        result = result[0].upper() + result[1:] if result else result
        
        return result
    
    def _get_fallback_response(self):
        """Return a fallback response when processing fails"""
        fallbacks = [
            "That is great",
            "Good",
            "That's great!",
            "Hello Friend",
            "Let me help you",
            "Hello there",
            "Thank you",
            "I love you too",
            "Nice to meet you"
        ]
        return random.choice(fallbacks)
    
    def check_status(self):
        """
        Check if Gemini API is available
        
        Returns:
            bool: True if Gemini API is accessible, False otherwise
        """
        try:
            # Check if we're currently rate-limited
            if self.quota_exceeded:
                current_time = time.time()
                if current_time < self.retry_after_timestamp:
                    wait_time = int(self.retry_after_timestamp - current_time)
                    logger.warning(f"Quota still exceeded, need to wait {wait_time} more seconds")
                    return False
                else:
                    logger.info("Retry period expired, attempting Gemini request")
                    self.quota_exceeded = False
            
            # Test with a simple query - list available models first
            try:
                # First try to list models to avoid model-specific errors
                models = genai.list_models()
                model_names = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
                logger.info(f"Available Gemini models: {model_names}")
                
                # If our model isn't in the list, use the first available one
                if self.model not in model_names and model_names:
                    logger.warning(f"Model {self.model} not found, using {model_names[0]} instead")
                    self.model = model_names[0]
                
                # Now test with the model
                model = genai.GenerativeModel(self.model)
                # Use generate_content instead of count_tokens
                response = model.generate_content("test")
                
                self.last_successful_request = time.time()
                logger.info(f"Gemini API is accessible with model {self.model}")
                return True
            except Exception as e:
                logger.warning(f"Error with specified model, trying fallback: {str(e)}")
                # Try with a fallback model
                fallback_models = ["models/gemini-1.5-flash-8b", "models/gemini-1.5-flash-8b-latest", 
                                  "models/gemini-1.5-flash-latest", "models/gemini-1.5-pro-latest", 
                                  "models/gemini-1.5-pro-002", "models/gemini-pro", "models/gemini-1.0-pro-latest"]
                for fallback in fallback_models:
                    try:
                        if fallback != self.model and fallback in model_names:  # Only try valid models
                            logger.info(f"Trying fallback model: {fallback}")
                            model = genai.GenerativeModel(fallback)
                            response = model.generate_content("test")
                            
                            # If successful, update our model to use this one
                            logger.info(f"Fallback successful with {fallback}, updating model preference")
                            self.model = fallback
                            self.last_successful_request = time.time()
                            return True
                    except Exception:
                        continue
                        
                # If we get here, all fallbacks failed
                raise Exception("All model attempts failed")
                
        except Exception as e:
            error_str = str(e)
            if "429" in error_str and "quota" in error_str:
                logger.warning("Quota exceeded during status check")
                self.quota_exceeded = True
                # Try to extract retry delay
                if "retry_delay" in error_str:
                    try:
                        retry_seconds = int(re.search(r'retry_delay\s*{\s*seconds:\s*(\d+)', error_str).group(1))
                        self.retry_after_timestamp = time.time() + retry_seconds
                        logger.warning(f"Will retry after {retry_seconds} seconds")
                    except (AttributeError, ValueError):
                        self.retry_after_timestamp = time.time() + 60  # Default 60 seconds
            else:
                logger.warning(f"Error checking Gemini API: {error_str}")
            
        return False
    
    def shutdown(self):
        """Clean shutdown of the handler"""
        self.is_running = False
        if self.connection_check_event:
            self.connection_check_event.set()
        logger.info("Gemini handler shut down")


# For testing and demonstration
if __name__ == "__main__":
    handler = GeminiHandler()
    
    # Check if Gemini API is accessible
    status = handler.check_status()
    print(f"Gemini API status: {'Accessible' if status else 'Not accessible'}")
    
    if status:
        # Get some example responses
        test_inputs = [
            "hello",
            "thanks",
            "iloveyou",
            "hello iloveyou thanks"
        ]
        
        for test in test_inputs:
            response = handler.get_response(test)
            print(f"Input: '{test}' -> Response: '{response}'")
    
    # Clean shutdown
    handler.shutdown() 