from flask import Flask, render_template, request, redirect, url_for, flash, render_template_string
from twilio.rest import Client
import os
from dotenv import load_dotenv  # Load environment variables from .env file
import time
import threading
import queue

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# Twilio credentials from environment variables
account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')

# Validate required environment variables
if not account_sid or not auth_token:
    raise ValueError(
        "Missing required environment variables: TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN. "
        "Please set these in your Render dashboard or .env file."
    )

client = Client(account_sid, auth_token)

NUMBERS_FILE = "numbers.txt"
CALL_STATUS_QUEUE = queue.Queue()

@app.errorhandler(ValueError)
def handle_value_error(error):
    """Handle missing environment variables gracefully."""
    error_message = str(error)
    if "environment variables" in error_message.lower():
        return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head><title>Configuration Error</title></head>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px;">
            <h1 style="color: #e74c3c;">⚠️ Configuration Error</h1>
            <p>{{ error_message }}</p>
            <h3>Required Environment Variables:</h3>
            <ul>
                <li><code>TWILIO_ACCOUNT_SID</code> - Your Twilio Account SID</li>
                <li><code>TWILIO_AUTH_TOKEN</code> - Your Twilio Auth Token</li>
                <li><code>SECRET_KEY</code> - Flask secret key (optional, will use default)</li>
            </ul>
            <p><strong>For Render deployment:</strong> Add these in your Render service dashboard under "Environment"</p>
        </body>
        </html>
        """, error_message=error_message), 500
    return error

def read_numbers():
    """Read all numbers from file."""
    if not os.path.exists(NUMBERS_FILE):
        return []
    numbers = []
    with open(NUMBERS_FILE, "r") as f:
        for line in f:
            number = line.strip()
            # Validate phone number format (basic validation)
            if number and (number.startswith('+') and len(number) >= 10):
                numbers.append(number)
            elif number:
                print(f"Warning: Invalid phone number format: {number}")
    return numbers

def write_numbers(numbers):
    """Rewrite numbers to file."""
    with open(NUMBERS_FILE, "w") as f:
        for num in numbers:
            f.write(num + "\n")

def make_calls():
    """Make calls to all numbers in the file."""
    numbers = read_numbers()

    for number in numbers.copy():
        try:
            CALL_STATUS_QUEUE.put(f"📞 Calling {number}...")
            call = client.calls.create(
                url="https://calling.shopiespot.com/voice.xml",
                to=number,
                from_="+16812442941"
            )
            CALL_STATUS_QUEUE.put(f"✅ Call started (SID: {call.sid})")

            # Delay between calls
            time.sleep(3)

            # Remove number from file after calling
            numbers.remove(number)
            write_numbers(numbers)
            CALL_STATUS_QUEUE.put(f"🗑️ {number} removed from numbers.txt")

        except Exception as e:
            CALL_STATUS_QUEUE.put(f"❌ Failed to call {number}: {e}")
            continue

@app.route('/')
def index():
    numbers = read_numbers()
    return render_template('index.html', numbers=numbers)

@app.route('/add_number', methods=['POST'])
def add_number():
    number = request.form.get('number', '').strip()
    if not number:
        flash('Phone number is required!', 'error')
        return redirect(url_for('index'))

    # Validate phone number format
    if not (number.startswith('+') and len(number) >= 10):
        flash('Please enter a valid phone number starting with + and at least 10 digits!', 'error')
        return redirect(url_for('index'))

    numbers = read_numbers()
    if number not in numbers:
        numbers.append(number)
        write_numbers(numbers)
        flash(f'Number {number} added successfully!', 'success')
    else:
        flash(f'Number {number} already exists!', 'warning')
    return redirect(url_for('index'))

@app.route('/remove_number/<number>')
def remove_number(number):
    numbers = read_numbers()
    if number in numbers:
        numbers.remove(number)
        write_numbers(numbers)
        flash(f'Number {number} removed successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/call_all', methods=['POST'])
def call_all():
    # Start calling process in background thread
    call_thread = threading.Thread(target=make_calls)
    call_thread.daemon = True
    call_thread.start()
    flash('Calling process started! Check status below.', 'info')
    return redirect(url_for('index'))

@app.route('/get_status')
def get_status():
    """Get real-time call status updates."""
    def generate():
        while True:
            try:
                status = CALL_STATUS_QUEUE.get(timeout=1)
                yield f"data: {status}\n\n"
            except queue.Empty:
                break

    return app.response_class(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    app.run(debug=True)
