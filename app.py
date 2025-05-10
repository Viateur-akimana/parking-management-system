from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
import csv
import os
import time
import json
from threading import Thread
from datetime import datetime

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# File paths
CSV_FILE = 'plates_log.csv'
PAYMENT_LOG = 'payment_log.txt'

# System stats
system_stats = {
    "total_vehicles": 0,
    "paid_vehicles": 0,
    "pending_payments": 0,
    "total_revenue": 0
}

def update_system_stats():
    """Update system statistics based on log files"""
    try:
        # Count vehicles and payment status
        vehicles = set()
        paid = 0
        pending = 0
        
        with open(CSV_FILE, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                plate = row['Plate Number']
                vehicles.add(plate)
                if row['Payment Status'] == '1':
                    paid += 1
                else:
                    pending += 1
        
        # Calculate revenue from payment log
        revenue = 0
        with open(PAYMENT_LOG, 'r') as f:
            for line in f:
                if "SUCCESS" in line:
                    parts = line.split(", ")
                    for part in parts:
                        if "Old Balance:" in part and "New Balance:" in part:
                            old_bal = int(part.split("Old Balance: ")[1].split(",")[0])
                            new_bal = int(part.split("New Balance: ")[1])
                            revenue += (old_bal - new_bal)
        
        # Update stats
        system_stats["total_vehicles"] = len(vehicles)
        system_stats["paid_vehicles"] = paid
        system_stats["pending_payments"] = pending
        system_stats["total_revenue"] = revenue
        
    except Exception as e:
        print(f"Error updating stats: {e}")

def watch_logs():
    """Monitor log files for changes and emit updates"""
    last_csv_size = 0
    last_payment_size = 0
    
    while True:
        try:
            # Check plates log
            current_csv_size = os.path.getsize(CSV_FILE) if os.path.exists(CSV_FILE) else 0
            if current_csv_size != last_csv_size:
                update_system_stats()
                socketio.emit('log_update', {
                    'file': 'plates', 
                    'time': datetime.now().timestamp(),
                    'stats': system_stats
                })
                last_csv_size = current_csv_size
            
            # Check payment log
            current_payment_size = os.path.getsize(PAYMENT_LOG) if os.path.exists(PAYMENT_LOG) else 0
            if current_payment_size != last_payment_size:
                with open(PAYMENT_LOG, 'r') as f:
                    lines = f.readlines()
                    if lines:
                        update_system_stats()
                        socketio.emit('new_transaction', {
                            'log': lines[-1].strip(),
                            'type': 'payment',
                            'stats': system_stats
                        })
                last_payment_size = current_payment_size
            
            time.sleep(1)
        except Exception as e:
            print(f"Log watcher error: {str(e)}")
            time.sleep(5)

@app.route('/')
def index():
    update_system_stats()
    return render_template('index.html', stats=system_stats)

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

@app.route('/stats')
def get_stats():
    update_system_stats()
    return jsonify(system_stats)

@socketio.on('connect')
def on_connect():
    update_system_stats()
    socketio.emit('stats_update', system_stats)

if __name__ == '__main__':
    # Start log watcher thread
    Thread(target=watch_logs, daemon=True).start()
    
    # Ensure log files exist
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Plate Number', 'Payment Status', 'Timestamp'])
    
    if not os.path.exists(PAYMENT_LOG):
        open(PAYMENT_LOG, 'w').close()
        
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)