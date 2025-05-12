// Initialize variables
let model;
let holistic;
let sequence = [];
let actions = ['hello', 'thanks', 'iloveyou'];
let isModelLoaded = false;

// DOM elements
const video = document.getElementById('webcam');
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const predictionText = document.getElementById('prediction-text');
const confidenceText = document.getElementById('confidence');

// Set canvas dimensions
canvas.width = 640;
canvas.height = 480;

// Initialize MediaPipe Holistic
holistic = new Holistic({
    locateFile: (file) => {
        return `https://cdn.jsdelivr.net/npm/@mediapipe/holistic/${file}`;
    }
});

holistic.setOptions({
    modelComplexity: 1,
    smoothLandmarks: true,
    minDetectionConfidence: 0.5,
    minTrackingConfidence: 0.5
});

holistic.onResults(onResults);

// Load the TensorFlow.js model
async function loadModel() {
    try {
        model = await tf.loadLayersModel('tfjs_model/model.json');
        isModelLoaded = true;
        console.log('Model loaded successfully');
    } catch (error) {
        console.error('Error loading model:', error);
    }
}

// Process MediaPipe results
function onResults(results) {
    // Draw the pose, face, and hand landmarks
    ctx.save();
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(results.image, 0, 0, canvas.width, canvas.height);
    
    // Draw pose landmarks
    if (results.poseLandmarks) {
        drawConnectors(ctx, results.poseLandmarks, POSE_CONNECTIONS, { color: '#00FF00', lineWidth: 2 });
        drawLandmarks(ctx, results.poseLandmarks, { color: '#FF0000', lineWidth: 1 });
    }
    
    // Draw face landmarks
    if (results.faceLandmarks) {
        drawConnectors(ctx, results.faceLandmarks, FACEMESH_TESSELATION, { color: '#C0C0C0', lineWidth: 1 });
        drawLandmarks(ctx, results.faceLandmarks, { color: '#C0C0C0', lineWidth: 0.5 });
    }
    
    // Draw hand landmarks
    if (results.leftHandLandmarks) {
        drawConnectors(ctx, results.leftHandLandmarks, HAND_CONNECTIONS, { color: '#CC0000', lineWidth: 2 });
        drawLandmarks(ctx, results.leftHandLandmarks, { color: '#00FF00', lineWidth: 1 });
    }
    if (results.rightHandLandmarks) {
        drawConnectors(ctx, results.rightHandLandmarks, HAND_CONNECTIONS, { color: '#00CC00', lineWidth: 2 });
        drawLandmarks(ctx, results.rightHandLandmarks, { color: '#FF0000', lineWidth: 1 });
    }
    
    ctx.restore();

    // Extract keypoints
    const keypoints = extractKeypoints(results);
    
    // Add to sequence
    sequence.push(keypoints);
    if (sequence.length > 30) {
        sequence.shift();
    }

    // Make prediction if we have enough frames and model is loaded
    if (sequence.length === 30 && isModelLoaded) {
        const prediction = model.predict(tf.tensor([sequence]));
        const scores = prediction.dataSync();
        const maxScore = Math.max(...scores);
        const predictedAction = actions[scores.indexOf(maxScore)];
        
        // Update UI
        predictionText.textContent = predictedAction;
        confidenceText.textContent = `Confidence: ${(maxScore * 100).toFixed(2)}%`;
    }
}

// Extract keypoints from MediaPipe results
function extractKeypoints(results) {
    const pose = results.poseLandmarks ? 
        results.poseLandmarks.map(landmark => [landmark.x, landmark.y, landmark.z, landmark.visibility]).flat() : 
        Array(33 * 4).fill(0);
    
    const face = results.faceLandmarks ? 
        results.faceLandmarks.map(landmark => [landmark.x, landmark.y, landmark.z]).flat() : 
        Array(468 * 3).fill(0);
    
    const leftHand = results.leftHandLandmarks ? 
        results.leftHandLandmarks.map(landmark => [landmark.x, landmark.y, landmark.z]).flat() : 
        Array(21 * 3).fill(0);
    
    const rightHand = results.rightHandLandmarks ? 
        results.rightHandLandmarks.map(landmark => [landmark.x, landmark.y, landmark.z]).flat() : 
        Array(21 * 3).fill(0);
    
    return [...pose, ...face, ...leftHand, ...rightHand];
}

// Start the webcam
async function startWebcam() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: {
                width: 640,
                height: 480
            }
        });
        video.srcObject = stream;
        
        // Start processing frames
        video.addEventListener('play', () => {
            const camera = new Camera(video, {
                onFrame: async () => {
                    await holistic.send({image: video});
                },
                width: 640,
                height: 480
            });
            camera.start();
        });
    } catch (error) {
        console.error('Error accessing webcam:', error);
    }
}

// Initialize the application
async function init() {
    await loadModel();
    await startWebcam();
}

// Start the application
init(); 