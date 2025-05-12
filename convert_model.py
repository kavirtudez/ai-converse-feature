import tensorflow as tf
import tensorflowjs as tfjs
import os

def main():
    # Create output directory if it doesn't exist
    output_dir = 'tfjs_model'
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Load the Keras model
    print("Loading Keras model...")
    model = tf.keras.models.load_model('action.h5')

    # Convert and save the model
    print("Converting model to TensorFlow.js format...")
    tfjs.converters.save_keras_model(model, output_dir)

    print(f"Model converted and saved to {output_dir}")

if __name__ == "__main__":
    main() 