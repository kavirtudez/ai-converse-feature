from flask import Flask, request, jsonify
from google.cloud import translate_v2 as translate
import os
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Set the path to your service account JSON file
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "./starlit-rite-452918-k8-ff712369ea61.json"

# Initialize the Google Translate client
translate_client = translate.Client()

@app.route('/translate', methods=['POST'])
def translate_text():
    data = request.json
    text = data.get('text')
    source = data.get('source', 'tl')
    target = data.get('target', 'en')
    
    if not text:
        return jsonify({'error': 'No text provided'}), 400

    try:
        result = translate_client.translate(text, source_language=source, target_language=target)
        print(f"Translated '{text}' from {source} to {target}: {result['translatedText']}")
        return jsonify({'translatedText': result['translatedText']})
    except Exception as e:
        print(f"Translation error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/test', methods=['GET'])
def test():
    return jsonify({'status': 'Backend is running'})

if __name__ == '__main__':
    print("Starting translation backend on http://localhost:5000")
    print("Service account file: starlit-rite-452918-k8-ff712369ea61.json")
    app.run(port=5000, debug=True) 