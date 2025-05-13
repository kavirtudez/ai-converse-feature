import requests
import time
import json

def add_sign_to_sentence(sign_name):
    """Add a sign to the sentence without clearing previous signs"""
    print(f"Adding sign: {sign_name}")
    
    try:
        test_sign_response = requests.post(
            "http://localhost:5000/test_sign",
            json={"sign": sign_name, "clientId": "default"},
            timeout=5
        )
        print(f"Test sign response: {test_sign_response.status_code}, {test_sign_response.text}")
    except Exception as e:
        print(f"Error sending test sign: {e}")
    
    # Check the current sentence
    try:
        result_response = requests.get(
            "http://localhost:5000/get_sentence?clientId=default",
            timeout=5
        )
        print(f"Current sentence: {result_response.status_code}, {result_response.text}")
    except Exception as e:
        print(f"Error getting sentence: {e}")
    
    # Check if sign_conversation.py received the update
    try:
        conversation_response = requests.get(
            "http://localhost:5001/api/sentence",
            timeout=5
        )
        print(f"Conversation API response: {conversation_response.status_code}, {conversation_response.text}")
    except Exception as e:
        print(f"Error getting conversation API: {e}")

if __name__ == "__main__":
    # First clear any existing sentence
    print("Clearing existing sentence...")
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
    time.sleep(2)
    
    # Add signs one by one to form a sentence
    signs = ["hello", "thanks", "iloveyou"]
    
    for sign in signs:
        add_sign_to_sentence(sign)
        time.sleep(3)  # Wait between signs
    
    print("\nFinal sentence check:")
    try:
        # Check app.py sentence
        app_response = requests.get(
            "http://localhost:5000/get_sentence?clientId=default",
            timeout=5
        )
        print(f"App.py sentence: {app_response.status_code}, {app_response.text}")
        
        # Check sign_conversation.py sentence
        conversation_response = requests.get(
            "http://localhost:5001/api/sentence",
            timeout=5
        )
        print(f"Conversation API sentence: {conversation_response.status_code}, {conversation_response.text}")
    except Exception as e:
        print(f"Error in final check: {e}")
        
    print("\nTest completed. Check the web UI to see if the sentence is displayed correctly.") 