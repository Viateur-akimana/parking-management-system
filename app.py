from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO
import csv
import os
import time
from threading import Thread
from datetime import datetime

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# File paths
CSV_FILE = 'plates_log.csv'
PAYMENT_LOG = 'payment_log.txt'

def watch_logs():
    """Monitor log files for changes and emit updates"""
    last_csv_size = 0
    last_payment_size = 0
    
    while True:
        try:
            # Check plates log
            current_csv_size = os.path.getsize(CSV_FILE) if os.path.exists(CSV_FILE) else 0
            if current_csv_size != last_csv_size:
                socketio.emit('log_update', {'file': 'plates', 'time': datetime.now().timestamp()})
                last_csv_size = current_csv_size
            
            # Check payment log
            current_payment_size = os.path.getsize(PAYMENT_LOG) if os.path.exists(PAYMENT_LOG) else 0
            if current_payment_size != last_payment_size:
                with open(PAYMENT_LOG, 'r') as f:
                    lines = f.readlines()
                    if lines:
                        socketio.emit('new_transaction', {
                            'log': lines[-1].strip(),
                            'type': 'payment'
                        })
                last_payment_size = current_payment_size
            
            time.sleep(1)
        except Exception as e:
            print(f"Log watcher error: {str(e)}")
            time.sleep(5)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/logs')
def get_logs():
    logs = []
    try:
        with open(CSV_FILE, 'r') as f:
            reader = csv.DictReader(f)
            logs = [row for row in reader]
    except FileNotFoundError:
        # Create file if it doesn't exist
        with open(CSV_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Plate Number', 'Payment Status', 'Timestamp'])
    return jsonify(logs)

@app.route('/transactions')
def get_transactions():
    transactions = []
    try:
        with open(PAYMENT_LOG, 'r') as f:
            transactions = [line.strip() for line in f.readlines() if line.strip()]
    except FileNotFoundError:
        open(PAYMENT_LOG, 'w').close()
    return jsonify(transactions)

if __name__ == '__main__':
    # Start log watcher thread
    Thread(target=watch_logs, daemon=True).start()
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)