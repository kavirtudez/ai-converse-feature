# Gemini Integration for Sign Language Recognition System

This integration replaces the Ollama backend with Google's Gemini API for faster, smarter responses to sign language inputs.

## Setup Instructions

1. Install the required dependencies:
   ```
   pip install flask requests google-generativeai
   ```

2. The API key is already included in the code (`AIzaSyC1NYbUuZLEbVuAfJRQ4-wYtP2a4FgV9_U`), but you can also set it as an environment variable:
   ```
   set GEMINI_API_KEY=AIzaSyC1NYbUuZLEbVuAfJRQ4-wYtP2a4FgV9_U   # Windows
   export GEMINI_API_KEY=AIzaSyC1NYbUuZLEbVuAfJRQ4-wYtP2a4FgV9_U  # Linux/Mac
   ```

## Running the Integration

1. Start the Gemini integration service:
   ```
   python integrate_gemini.py
   ```

2. The service runs on port 5002, the same as the previous Ollama integration, so no changes to app.py or other components are needed.

3. The service maintains the same API endpoints, just replacing "ollama" with "gemini" in the route names:
   - `/api/gemini_status` - Check if Gemini API is accessible
   - `/api/gemini_response` - Get a response from Gemini
   - `/process_sign_sentence` - Process a sign language sentence (main endpoint used by app.py)

## Benefits of Gemini Integration

- **Faster responses** - Gemini API is typically faster than running Ollama locally
- **No local model required** - No need to download and manage large language models
- **Improved quality** - Better understanding of sign language inputs
- **Same post-processing** - Still limits to 5 words max and removes emojis/hashtags

## Troubleshooting

If you experience any issues:

1. Check if the Gemini API is accessible by visiting: http://localhost:5002/test
2. Verify your internet connection as the Gemini API requires internet access
3. Check the console logs for any error messages

## Switching Between Ollama and Gemini

You can easily switch between the two integrations:

- To use Gemini: `python integrate_gemini.py`
- To use Ollama: `python integrate_ollama.py`

Both services use port 5002, so make sure only one is running at a time.

## How It Works

The integration follows the same pattern as the Ollama integration:

1. User signs are detected and assembled into words/sentences
2. The sentence is sent to the Gemini API
3. The response is post-processed to ensure it's clean and concise (maximum 5 words)
4. The processed response is returned to the frontend

The GeminiHandler class handles all interaction with the Gemini API, including retries, timeouts, and post-processing. 