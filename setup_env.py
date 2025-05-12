import subprocess
import sys
import os
import venv
import shutil

def run_command(command, check=True):
    try:
        process = subprocess.run(command, shell=True, check=check, text=True)
        return process.stdout
    except subprocess.CalledProcessError as e:
        print(f"Warning: Command failed: {e}")
        return None

def main():
    # Remove existing venv if it exists
    venv_path = "venv"
    if os.path.exists(venv_path):
        print("Removing existing virtual environment...")
        shutil.rmtree(venv_path)

    # Create virtual environment
    print("Creating virtual environment...")
    venv.create(venv_path, with_pip=True)

    # Determine the path to the Python executable in the virtual environment
    if sys.platform == "win32":
        python_path = os.path.join(venv_path, "Scripts", "python.exe")
        pip_path = os.path.join(venv_path, "Scripts", "pip.exe")
    else:
        python_path = os.path.join(venv_path, "bin", "python")
        pip_path = os.path.join(venv_path, "bin", "pip")

    # Try to upgrade pip, but continue if it fails
    print("Attempting to upgrade pip...")
    run_command(f'"{pip_path}" install --upgrade pip', check=False)

    # Install required packages with specific versions
    print("\nInstalling required packages...")
    packages = [
        "tensorflow==2.12.0",
        "numpy==1.23.5",
        "opencv-python==4.7.0.72",
        "flask==2.3.3",
        "flask-cors==4.0.0",
        "mediapipe==0.10.0"
    ]
    
    for package in packages:
        print(f"Installing {package}...")
        if run_command(f'"{pip_path}" install {package}', check=False) is None:
            print(f"Failed to install {package}, trying alternative method...")
            run_command(f'"{python_path}" -m pip install {package}', check=False)

    print("\nSetup complete! To activate the virtual environment:")
    if sys.platform == "win32":
        print("venv\\Scripts\\activate")
    else:
        print("source venv/bin/activate")

if __name__ == "__main__":
    main() 