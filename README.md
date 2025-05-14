# Dynamic Sign Language Translation Application

This project is a multi-component application designed to translate sign language to text, generate an AI response using Gemini, and then animate that AI response back into sign language.

## Project Components

*   **Sign Recognition (`app.py`):** A Flask application that captures webcam input, uses MediaPipe for hand/pose detection, and a TensorFlow model to recognize predefined signs (hello, thanks, iloveyou). It displays the recognized signs and can send the formed sentence to an AI service. (Runs on port 5000)
*   **Gemini Integration (`integrate_gemini.py`):** A Flask service that acts as a dedicated interface to the Google Gemini API. It receives text input and returns an AI-generated response. (Runs on port 5002)
*   **Translation Backend (`asl&fslmodel/backend/translate_backend.py`):** A Flask service using Google Cloud Translate API to translate text (e.g., Gemini's English response to Tagalog). (Runs on port 5003)
*   **Angular Frontend (`asl&fslmodel/frontend`):** An Angular application responsible for animating text (Gemini's response, potentially translated) into sign language using a pose model. (Runs on port 4200)
*   **Conversation Orchestrator (`sign_conversation.py`):** A Flask + Socket.IO application that serves a main HTML page embedding the sign input app (`app.py`) and the Angular animation app as iframes, facilitating communication between them. (Runs on port 5001)

## Prerequisites

*   **Python:** Version 3.9 or higher recommended.
*   **Node.js and Angular CLI:** For running the Angular frontend.
    *   Node.js (LTS version recommended)
    *   Angular CLI: Install globally using `npm install -g @angular/cli`
*   **Git:** For cloning the repository (if applicable).
*   **Google Cloud SDK (`gcloud` CLI):** Optional, but helpful for managing Google Cloud credentials if not solely relying on API keys/service account files placed directly in the project.

## Setup Instructions

1.  **Clone the Repository (if you haven't already):**
```bash
    # git clone <repository-url>
    # cd <repository-directory>
    ```

2.  **Create and Activate Python Virtual Environment:**
    Navigate to the project root directory (`dynamic sign recognizer`):
    ```bash
python -m venv signenv
signenv\Scripts\activate
    ```
    (On macOS/Linux, use `source signenv/bin/activate`)

3.  **Install Python Dependencies:**
    With the virtual environment activated, install all required packages:
    ```bash
pip install -r requirements.txt
```

4.  **Setup Angular Frontend Dependencies:**
```bash
cd asl&fslmodel/frontend
npm install
    cd ../.. 
    ```
    (Returns to the project root directory)

5.  **Configure Google Cloud Services:**
    *   **Translation Backend:**
        *   Ensure the service account JSON file `starlit-rite-452918-k8-ff712369ea61.json` is present in the project root directory (as referenced by `asl&fslmodel/backend/translate_backend.py`, which sets `os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "./starlit-rite-452918-k8-ff712369ea61.json"`).
        *   Make sure the Google Cloud Translation API is enabled for the project associated with this service account.
    *   **Gemini Integration:**
        *   The API key for Gemini is currently hardcoded in `integrate_gemini.py`. For better security in a shared or production environment, consider moving this to an environment variable.
        *   Ensure the Generative Language API (or Vertex AI API for Gemini Pro) is enabled for your Google Cloud project associated with this API key.

## Running the Application

You will need to open multiple terminals to run all the components. Ensure the Python virtual environment (`signenv`) is activated in each terminal where you run a Python script.

1.  **Terminal 1: Start Sign Recognition UI (`app.py`)**
    *   Activate virtual environment: `signenv\Scripts\activate`
    *   Run: `python app.py`
    *   *Service will run on `http://127.0.0.1:5000`*

2.  **Terminal 2: Start Gemini Integration Service (`integrate_gemini.py`)**
    *   Activate virtual environment: `signenv\Scripts\activate`
    *   Run: `python integrate_gemini.py`
    *   *Service will run on `http://127.0.0.1:5002`*

3.  **Terminal 3: Start Angular Frontend**
    *   Navigate to the Angular app directory: `cd asl&fslmodel\frontend`
    *   Run: `ng serve`
    *   *Service will run on `http://localhost:4200`*

4.  **Terminal 4: Start Translation Backend**
    *   Activate virtual environment: `signenv\Scripts\activate`
    *   Navigate to the backend directory: `cd asl&fslmodel\backend`
    *   Run: `python translate_backend.py`
    *   *Service will run on `http://localhost:5003`*

5.  **Terminal 5: Start Conversation Orchestrator (`sign_conversation.py`)**
    *   Activate virtual environment: `signenv\Scripts\activate`
    *   (You should be in the project root: `C:\Users\kazzv\Downloads\dynamic sign recognizer`)
    *   Run: `python sign_conversation.py`
    *   *Service will run on `http://127.0.0.1:5001`*

## Accessing the Application

Once all services are running, open your web browser and navigate to the main conversation orchestrator page:

**`http://127.0.0.1:5001/conversation`**

This page embeds the sign input and sign animation iframes.

## Notes

*   The order of starting the services is important, especially ensuring backend services (`integrate_gemini.py`, `translate_backend.py`) are running before `app.py` or `sign_conversation.py` try to connect to them. The Angular dev server (`ng serve`) should also be up for the iframes to load.
*   Ensure all specified ports (5000, 5001, 5002, 5003, 4200) are not in use by other applications.
*   The provided paths for `cd` commands in the "Running the Application" section are specific to your machine (`C:\Users\kazzv\Downloads\dynamic sign recognizer`). Users on other machines will need to adjust these paths relative to their project root. The README uses relative paths for `cd` where appropriate for general use.

## System Architecture

- **app.py**: Core sign language recognition service using MediaPipe and TensorFlow
- **sign_conversation.py**: Orchestration service connecting sign recognition with Ollama
- **Angular frontend**: Provides sign language animation based on text input

## Project Workflow: From Sign to Animated Response

This section outlines the journey of communication within the application, from recognizing a user's sign language to presenting an AI-generated, animated sign language response.

**Imagine this:** You're using sign language in front of your webcam. Here's how the system understands you and talks back:

**Overall Flow Diagram (Conceptual):**

```
[User Signs via Webcam]
       |
       v
[1. Sign Recognition (app.py)] -- Recognized Text --> [2. AI Conversation (integrate_gemini.py)]
       |                                                         |
       | (If Orchestrated)                                       | AI Text Response
       v                                                         v
[Orchestrator (sign_conversation.py)]                             [3. Forward to SL Avatar (app.py)]
       |                                                         |
       +------------------- Display Update ----------------------+
                                   |
                                   v
      [4. (Optional) Text Translation (asl&fslmodel/backend/translate_backend.py)]
                                   |
                                   v
        [5. SL Avatar (asl&fslmodel/frontend) for Sign Animation]
                                   |
                                   v
                         [Animated Sign Output]
```

**Step-by-Step Breakdown (IPO Format):**

1.  **Sign Recognition Service (`app.py`)**
    *   **Input:** Live video stream from the user's webcam.
    *   **Process:**
        *   Captures video frames.
        *   Uses MediaPipe to detect hand landmarks and body pose from the frames.
        *   Feeds these landmarks into a pre-trained TensorFlow model.
        *   The model predicts individual signs (e.g., "hello", "thank you").
        *   Collects recognized signs to form a sentence (e.g., "hello thank you").
        *   Displays the recognized sentence on its local web interface.
    *   **Output:** A string of recognized text (e.g., "hello thank you"). This text is then prepared to be sent for AI processing.

2.  **Gemini Integration Service (`integrate_gemini.py`)**
    *   **Input:** The recognized text sentence from `app.py`.
    *   **Process:**
        *   Receives the text via an HTTP request from `app.py`.
        *   Sends this text to the Google Gemini API.
        *   Receives the AI-generated text response from Gemini.
    *   **Output:** A string containing the AI's response (e.g., "You are very welcome!"). This is sent back to `app.py`.

3.  **Response Handling & Forwarding in `app.py`**
    *   **Input:** The AI-generated text response from `integrate_gemini.py`.
    *   **Process:**
        *   `app.py` receives the AI's text.
        *   It then makes an HTTP request to the Angular application's backend (or a designated endpoint on the Angular development server). The goal is to trigger the Angular app to process this text for animation.
        *   The primary method is to send it to an API endpoint like `http://127.0.0.1:4200/api/spoken-to-signed` (or a similar one expected by the Angular app's `TranslationService`).
    *   **Output:** The AI's text is forwarded to the Angular application.

4.  **(Optional) Translation Service (`asl&fslmodel/backend/translate_backend.py`)**
    *   **Input:** Text that needs translation (this could be Gemini's response if, for example, it needed to be translated from English to another spoken language like Tagalog before being animated). *Currently, the primary flow sends English text directly for ASL animation.*
    *   **Process:**
        *   Receives text via an HTTP request.
        *   Uses the Google Cloud Translation API to translate the text to a target language.
    *   **Output:** The translated text. This would typically be consumed by the Angular frontend if a spoken language translation step is part of the desired workflow before animation.

5.  **SL Avatar (`asl&fslmodel/frontend`) & Sign Animation**
    *   **Input:** The AI-generated (and potentially translated) text, received via its backend services/API endpoints from `app.py`.
    *   **Process:**
        *   The Angular `TranslationService` (or a similar mechanism) takes the input text.
        *   The frontend then utilizes a sophisticated two-stage model system, typically drawing from its assets (e.g., models located under `src/assets/models/`):
            *   **Text-to-Pose Conversion Model:** This model first interprets the input text and converts it into an initial sequence of pose keypoints. These keypoints define the fundamental body and hand positions and movements required to represent the sign language gestures.
            *   **Sign Language Detection & Refinement Model:** The generated pose keypoints are then processed and refined by a second model (e.g., a sign detector trained on sign language datasets like ASL-LEX and adapted for pose estimation frameworks like MediaPipe, which the overall system uses). This model enhances the accuracy, naturalness, and expressiveness of the gestures.
        *   These two models work in concert: the first generates the foundational poses from text, and the second ensures these poses accurately represent clear and understandable sign language.
        *   The Angular components then render the final, refined pose data, creating a fluid animation of a character performing the sign language.
    *   **Output:** Visual animation of the AI's response in sign language, displayed in the browser.

**The Role of `sign_conversation.py` (Orchestrator):**

*   **Input:** Status updates from `app.py` and the Angular app; potentially the recognized sentence from `app.py` if the flow is manually controlled through its UI.
*   **Process:**
    *   Provides a central web page (`http://127.0.0.1:5001/conversation`) that embeds `app.py` (for sign input) and the Angular app (for sign animation) in iframes.
    *   Monitors the status of the other services (`app.py`, Angular app, `integrate_gemini.py`).
    *   Historically, it was designed to facilitate the message passing:
        1. Get sentence from `app.py`.
        2. Send to `integrate_gemini.py`.
        3. Get Gemini response.
        4. Send Gemini response to Angular app for animation.
    *   While `app.py` now directly forwards to Angular, `sign_conversation.py` can still serve as a control panel and a way to view both parts of the interaction (input and animated output) side-by-side. It also manages the overall user session.
*   **Output:** A unified view of the system and status information. It can also display the conversational text.

**Methodology Summary:**

The project employs a microservice-oriented architecture. Each major function (sign recognition, AI interaction, text translation, sign animation) is handled by a distinct component.

1.  **Capture & Recognition:** User's physical signs are captured and translated into digital text.
2.  **AI Augmentation:** This text is used to prompt an AI, generating a contextually relevant response.
3.  **Transformation & Display:** The AI's text response is then transformed back into a visual medium (animated sign language) for the user.

This modular design allows for independent development, testing, and scaling of each part of the system. Communication between these services is primarily managed through HTTP requests, with `sign_conversation.py` offering an optional layer of orchestration and user interface integration. The ultimate goal is a seamless, dynamic conversation loop where signed input receives an animated signed response.

