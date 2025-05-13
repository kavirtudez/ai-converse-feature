import requests
import time
import json

def send_test_sign(sign_name):
    """Send a test sign to app.py to simulate recognition"""
    print(f"Sending test sign: {sign_name}")
    
    # Clear existing sentence
    try:
        clear_response = requests.post(
            "http://localhost:5000/clear_sentence",
            json={"clientId": "default"},
            timeout=5
        )
        print(f"Clear response: {clear_response.status_code}, {clear_response.text}")
    except Exception as e:
        print(f"Error clearing sentence: {e}")
    
    # Wait a bit
    time.sleep(1)
    
    # Use the new test_sign endpoint
    try:
        test_sign_response = requests.post(
            "http://localhost:5000/test_sign",
            json={"sign": sign_name, "clientId": "default"},
            timeout=5
        )
        print(f"Test sign response: {test_sign_response.status_code}, {test_sign_response.text}")
    except Exception as e:
        print(f"Error sending test sign: {e}")
    
    # Wait a bit more
    time.sleep(1)
    
    # Check if our sign was added to the sentence
    try:
        result_response = requests.get(
            "http://localhost:5000/get_sentence?clientId=default",
            timeout=5
        )
        print(f"Final sentence: {result_response.status_code}, {result_response.text}")
    except Exception as e:
        print(f"Error getting final sentence: {e}")

if __name__ == "__main__":
    # Test signs - these match the signs in app.py
    signs = ["hello", "thanks", "iloveyou"]
    
    # Send each test sign with some delay
    for sign in signs:
        send_test_sign(sign)
        time.sleep(3)  # Wait 3 seconds between signs
    
    print("Finished sending test signs. Check the conversation UI to see if they appeared.") 