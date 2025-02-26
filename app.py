# app.py
import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from werkzeug.utils import secure_filename
import google.generativeai as genai
from dotenv import load_dotenv
import base64
import json
from datetime import datetime, timedelta
import threading
import time

# Load environment variables
load_dotenv()

# Configure the Gemini API
# Try to get API key from environment variable, first from HF_SPACES then from .env file
GOOGLE_API_KEY = os.getenv("HF_GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("Google API Key not found. Set it as HF_GOOGLE_API_KEY in the Space settings.")

genai.configure(api_key=GOOGLE_API_KEY)

# Setup the Gemini model
model = genai.GenerativeModel('gemini-1.5-flash')

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your-default-secret-key-for-flash-messages")

# Configure upload folder
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def analyze_plant_image(image_path, plant_name):
    try:
        # Load the image
        image_parts = [
            {
                "mime_type": "image/jpeg",
                "data": encode_image(image_path)
            }
        ]
        
        # Create prompt for Gemini API
        prompt = f"""
        Analyze this image of a {plant_name} plant and priortize the determine if it's healthy or has a disease or pest infestation.
        
        If a disease or pest is detected remember plant can be healthy too , provide the following information in JSON format:
        
        {{
            "results": [
                {{
                    "type": "disease/pest",
                    "name": "Name of disease or pest",
                    "probability": "Probability as a percentage",
                    "symptoms": "Describe the visible symptoms",
                    "causes": "Main causes of the disease or pest",
                    "severity": "Low/Medium/High",
                    "spreading": "How it spreads",
                    "treatment": "Treatment options",
                    "prevention": "Preventive measures"
                }},
                {{
                    // Second most likely disease/pest with the same structure
                }},
                {{
                    // Third most likely disease/pest with the same structure
                }}
            ],
            "is_healthy": boolean indicating if the plant appears healthy,
            "confidence": "Overall confidence in the analysis as a percentage"
        }}
        
        Only return the JSON data and nothing else. Ensure the JSON is valid and properly formatted.
        If the plant appears completely healthy, set is_healthy to true and include an empty results array.
        """
        
        # Send request to Gemini API
        response = model.generate_content([prompt] + image_parts)
        
        # Extract the JSON response
        response_text = response.text
        
        # Find JSON within response text if needed
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1
        
        if json_start >= 0 and json_end > 0:
            json_str = response_text[json_start:json_end]
            return json.loads(json_str)
        else:
            # Return a default response if JSON parsing fails
            return {
                "error": "Failed to parse the API response",
                "raw_response": response_text
            }
            
    except Exception as e:
        return {
            "error": str(e),
            "is_healthy": None,
            "results": []
        }

def cleanup_old_files(directory, max_age_hours=1):  # Reduced to 1 hour for Hugging Face
    """Remove files older than the specified age from the directory"""
    while True:
        now = datetime.now()
        for filename in os.listdir(directory):
            if filename == '.gitkeep':  # Skip the .gitkeep file
                continue
                
            file_path = os.path.join(directory, filename)
            file_age = now - datetime.fromtimestamp(os.path.getctime(file_path))
            if file_age > timedelta(hours=max_age_hours):
                try:
                    os.remove(file_path)
                    print(f"Removed old file: {file_path}")
                except Exception as e:
                    print(f"Error removing {file_path}: {e}")
        # Sleep for 5 minutes before checking again
        time.sleep(300)  # 5 minutes

@app.route('/', methods=['GET'])
def index():
    # GET request - show the upload form
    return render_template('index.html', show_results=False)

@app.route('/analyze', methods=['POST'])
def analyze():
    if 'plant_image' not in request.files:
        flash('No file part')
        return redirect(url_for('index'))
    
    file = request.files['plant_image']
    plant_name = request.form.get('plant_name', 'unknown')
    
    if file.filename == '':
        flash('No selected file')
        return redirect(url_for('index'))
    
    if file and allowed_file(file.filename):
        # Generate a unique filename to avoid collisions
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        original_filename = secure_filename(file.filename)
        filename = f"{timestamp}_{original_filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        try:
            # Analyze the image
            analysis_result = analyze_plant_image(file_path, plant_name)
            
            if 'error' in analysis_result:
                flash(f"Error analyzing image: {analysis_result['error']}")
                # Remove the file if analysis failed
                if os.path.exists(file_path):
                    os.remove(file_path)
                return redirect(url_for('index'))
            
            # Now we need to handle the file - since we've already analyzed it,
            # we can delete it immediately after rendering the template
            response = render_template(
                'results.html',
                results=analysis_result,
                plant_name=plant_name,
                image_path=file_path.replace('static/', '', 1)
            )
            
            # Schedule the file for deletion (will be deleted after rendering)
            # We use a small delay to ensure the file is available for initial page load
            def delete_file_after_delay(path, delay=30):  # Increased delay for Hugging Face
                time.sleep(delay)
                if os.path.exists(path):
                    try:
                        os.remove(path)
                        print(f"Deleted analyzed file: {path}")
                    except Exception as e:
                        print(f"Error deleting {path}: {e}")
            
            # Start a thread to delete the file after a brief delay
            threading.Thread(
                target=delete_file_after_delay, 
                args=(file_path,), 
                daemon=True
            ).start()
            
            return response
            
        except Exception as e:
            flash(f"An error occurred: {str(e)}")
            # Remove the file if there's an error
            if os.path.exists(file_path):
                os.remove(file_path)
            return redirect(url_for('index'))
    
    flash('Invalid file type. Please upload an image (png, jpg, jpeg, gif).')
    return redirect(url_for('index'))

# Hugging Face Spaces requires the app to be available on port 7860
if __name__ == '__main__':
    # Start the cleanup thread when the app starts
    cleanup_thread = threading.Thread(target=cleanup_old_files, args=(app.config['UPLOAD_FOLDER'],), daemon=True)
    cleanup_thread.start()
    
    # Get the port from environment variable for Hugging Face Spaces compatibility
    port = int(os.environ.get("PORT", 7860))
    app.run(host='0.0.0.0', port=port)