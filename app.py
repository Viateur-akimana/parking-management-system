from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
import csv
import os
import time
import json
from threading import Thread
from datetime import datetime, timedelta
import re

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# File paths
CSV_FILE = 'plates_log.csv'
PAYMENT_LOG = 'payment_log.txt'
EXIT_LOG = 'exit_log.csv'
SECURITY_LOG_FILE = 'security_alerts.csv'

# Enhanced system stats
system_stats = {
    "total_vehicles": 0,
    "vehicles_inside": 0,
    "paid_vehicles": 0,
    "pending_payments": 0,
    "vehicles_exited": 0,
    "active_sessions": 0,
    "hourly_rate": 200
}

# Activity tracking
recent_activities = []
MAX_ACTIVITIES = 50

def create_exit_log_if_not_exists():
    """Create exit log file with headers if it doesn't exist"""
    if not os.path.exists(EXIT_LOG):
        with open(EXIT_LOG, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Plate Number', 'Entry Time', 'Exit Time', 'Duration', 'Amount Paid'])

def log_activity(activity_type, plate_number, details="", status="INFO"):
    """Log system activities for real-time monitoring"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    activity = {
        'timestamp': timestamp,
        'type': activity_type,  # 'ENTRY', 'PAYMENT', 'EXIT', 'ALERT'
        'plate': plate_number,
        'details': details,
        'status': status  # 'SUCCESS', 'ERROR', 'WARNING', 'INFO'
    }
    
    recent_activities.insert(0, activity)
    if len(recent_activities) > MAX_ACTIVITIES:
        recent_activities.pop()
    
    # Emit to all connected clients
    socketio.emit('new_activity', activity)

def update_system_stats():
    """Update comprehensive system statistics"""
    try:
        vehicles = set()
        paid_count = 0
        pending_count = 0
        entry_times = {}
        exited_vehicles = set()
        
        # Process entry logs
        if os.path.exists(CSV_FILE):
            with open(CSV_FILE, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    plate = row['Plate Number']
                    vehicles.add(plate)
                    entry_times[plate] = row['Timestamp']
                    
                    if row['Payment Status'] == '1':
                        paid_count += 1
                    else:
                        pending_count += 1
        
        # Process exit logs
        if os.path.exists(EXIT_LOG):
            with open(EXIT_LOG, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    exited_vehicles.add(row['Plate Number'])
        
        # Calculate vehicles still inside
        vehicles_inside = len(vehicles - exited_vehicles)
        
      
        
        # Calculate active sessions (vehicles inside with pending payments)
        active_sessions = 0
        for plate in vehicles:
            if plate not in exited_vehicles:
                # Check if payment is pending
                with open(CSV_FILE, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row['Plate Number'] == plate and row['Payment Status'] == '0':
                            active_sessions += 1
                            break
        
        # Update stats
        system_stats.update({
            "total_vehicles": len(vehicles),
            "vehicles_inside": vehicles_inside,
            "paid_vehicles": paid_count,
            "pending_payments": pending_count,
            "vehicles_exited": len(exited_vehicles),
            "active_sessions": active_sessions
        })
        
    except Exception as e:
        print(f"Error updating stats: {e}")

def watch_logs():
    """Enhanced log monitoring for all system components including security alerts"""
    last_csv_size = 0
    last_payment_size = 0
    last_exit_size = 0
    last_security_size = 0  # NEW: Track security alerts
    
    while True:
        try:
            # Monitor entry logs
            current_csv_size = os.path.getsize(CSV_FILE) if os.path.exists(CSV_FILE) else 0
            if current_csv_size != last_csv_size:
                update_system_stats()
                
                # Check for new entries
                if os.path.exists(CSV_FILE):
                    with open(CSV_FILE, 'r') as f:
                        lines = f.readlines()
                        if len(lines) > 1:  # Skip header
                            last_line = lines[-1].strip()
                            parts = last_line.split(',')
                            if len(parts) >= 3:
                                plate = parts[0]
                                timestamp = parts[2]
                                log_activity('ENTRY', plate, f'Vehicle entered at {timestamp}', 'SUCCESS')
                
                socketio.emit('stats_update', system_stats)
                last_csv_size = current_csv_size
            
            # Monitor payment logs
            current_payment_size = os.path.getsize(PAYMENT_LOG) if os.path.exists(PAYMENT_LOG) else 0
            if current_payment_size != last_payment_size:
                if os.path.exists(PAYMENT_LOG):
                    with open(PAYMENT_LOG, 'r') as f:
                        lines = f.readlines()
                        if lines:
                            last_line = lines[-1].strip()
                            
                            # Parse payment log entry
                            if ' - ' in last_line:
                                parts = last_line.split(' - ')
                                if len(parts) >= 3:
                                    timestamp = parts[0]
                                    plate = parts[1]
                                    status_info = parts[2]
                                    
                                    if 'SUCCESS' in status_info:
                                        log_activity('PAYMENT', plate, 'Payment processed successfully', 'SUCCESS')
                                    elif 'INSUFFICIENT' in status_info:
                                        log_activity('PAYMENT', plate, 'Insufficient balance', 'WARNING')
                                    elif 'ERROR' in status_info:
                                        log_activity('PAYMENT', plate, 'Payment processing error', 'ERROR')
                                    else:
                                        log_activity('PAYMENT', plate, status_info, 'INFO')
                            
                            socketio.emit('new_transaction', {
                                'log': last_line,
                                'type': 'payment',
                                'stats': system_stats
                            })
                
                update_system_stats()
                socketio.emit('stats_update', system_stats)
                last_payment_size = current_payment_size
            
            # Monitor exit logs
            current_exit_size = os.path.getsize(EXIT_LOG) if os.path.exists(EXIT_LOG) else 0
            if current_exit_size != last_exit_size:
                if os.path.exists(EXIT_LOG):
                    with open(EXIT_LOG, 'r') as f:
                        lines = f.readlines()
                        if len(lines) > 1:  # Skip header
                            last_line = lines[-1].strip()
                            parts = last_line.split(',')
                            if len(parts) >= 4:
                                plate = parts[0]
                                exit_time = parts[2]
                                duration = parts[3] if len(parts) > 3 else 'N/A'
                                log_activity('EXIT', plate, f'Vehicle exited after {duration}', 'SUCCESS')
                
                update_system_stats()
                socketio.emit('stats_update', system_stats)
                last_exit_size = current_exit_size
            
            # NEW: Monitor security alerts
            current_security_size = os.path.getsize(SECURITY_LOG_FILE) if os.path.exists(SECURITY_LOG_FILE) else 0
            if current_security_size != last_security_size:
                if os.path.exists(SECURITY_LOG_FILE):
                    with open(SECURITY_LOG_FILE, 'r') as f:
                        lines = f.readlines()
                        if len(lines) > 1:  # Skip header
                            last_line = lines[-1].strip()
                            parts = last_line.split(',')
                            if len(parts) >= 6:
                                timestamp = parts[0]
                                plate = parts[1]
                                alert_type = parts[2]
                                action_taken = parts[4]
                                
                                # Create security alert for dashboard
                                security_alert = {
                                    'timestamp': timestamp,
                                    'type': 'SECURITY_ALERT',
                                    'plate': plate,
                                    'details': f'{alert_type}: {action_taken}',
                                    'status': 'ERROR',
                                    'alert_type': alert_type
                                }
                                
                                # Emit to dashboard
                                socketio.emit('security_alert', security_alert)
                                log_activity('SECURITY_ALERT', plate, f'{alert_type} - {action_taken}', 'ERROR')
                
                last_security_size = current_security_size
            
            time.sleep(1)
        except Exception as e:
            print(f"Log watcher error: {str(e)}")
            time.sleep(5)

# Routes
@app.route('/')
def index():
    update_system_stats()
    return render_template('index.html', stats=system_stats)

@app.route('/logs')
def get_logs():
    """Get entry logs"""
    logs = []
    try:
        with open(CSV_FILE, 'r') as f:
            reader = csv.DictReader(f)
            logs = [row for row in reader]
    except FileNotFoundError:
        with open(CSV_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Plate Number', 'Payment Status', 'Timestamp'])
    return jsonify(logs)

@app.route('/transactions')
def get_transactions():
    """Get payment transaction logs"""
    transactions = []
    try:
        with open(PAYMENT_LOG, 'r') as f:
            transactions = [line.strip() for line in f.readlines() if line.strip()]
    except FileNotFoundError:
        open(PAYMENT_LOG, 'w').close()
    return jsonify(transactions)

@app.route('/exits')
def get_exits():
    """Get exit logs"""
    exits = []
    try:
        with open(EXIT_LOG, 'r') as f:
            reader = csv.DictReader(f)
            exits = [row for row in reader]
    except FileNotFoundError:
        create_exit_log_if_not_exists()
    return jsonify(exits)

@app.route('/activities')
def get_activities():
    """Get recent system activities"""
    return jsonify(recent_activities)

@app.route('/stats')
def get_stats():
    """Get current system statistics"""
    update_system_stats()
    return jsonify(system_stats)

@app.route('/vehicles/inside')
def get_vehicles_inside():
    """Get list of vehicles currently inside"""
    vehicles_inside = []
    try:
        entered_vehicles = {}
        exited_vehicles = set()
        
        # Get all entries
        if os.path.exists(CSV_FILE):
            with open(CSV_FILE, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    entered_vehicles[row['Plate Number']] = {
                        'entry_time': row['Timestamp'],
                        'payment_status': row['Payment Status']
                    }
        
        # Get all exits
        if os.path.exists(EXIT_LOG):
            with open(EXIT_LOG, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    exited_vehicles.add(row['Plate Number'])
        
        # Calculate vehicles still inside
        for plate, info in entered_vehicles.items():
            if plate not in exited_vehicles:
                entry_time = datetime.strptime(info['entry_time'], '%Y-%m-%d %H:%M:%S')
                duration = datetime.now() - entry_time
                hours = duration.total_seconds() / 3600
                
                vehicles_inside.append({
                    'plate': plate,
                    'entry_time': info['entry_time'],
                    'duration_hours': round(hours, 2),
                    'payment_status': 'Paid' if info['payment_status'] == '1' else 'Pending',
                    'estimated_fee': round(hours * system_stats['hourly_rate'], 2)
                })
    
    except Exception as e:
        print(f"Error getting vehicles inside: {e}")
    
    return jsonify(vehicles_inside)

@app.route('/security-alerts')
def get_security_alerts():
    """Get security alerts from CSV"""
    alerts = []
    try:
        if os.path.exists(SECURITY_LOG_FILE):
            with open(SECURITY_LOG_FILE, 'r') as f:
                reader = csv.DictReader(f)
                alerts = [row for row in reader]
    except FileNotFoundError:
        # Create empty security alerts file
        with open(SECURITY_LOG_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Timestamp', 'Plate Number', 'Alert Type', 'Status', 'Action Taken', 'Personnel Notified'])
    return jsonify(alerts)

# Socket events
@socketio.on('connect')
def on_connect():
    update_system_stats()
    socketio.emit('stats_update', system_stats)
    socketio.emit('activities_update', recent_activities)

@socketio.on('request_update')
def handle_update_request():
    update_system_stats()
    socketio.emit('stats_update', system_stats)

# Simulated exit logging function (call this from car_exit.py)
def log_vehicle_exit(plate_number, entry_time_str, amount_paid=0):
    """Log vehicle exit - call this from car_exit.py"""
    try:
        entry_time = datetime.strptime(entry_time_str, '%Y-%m-%d %H:%M:%S')
        exit_time = datetime.now()
        duration = exit_time - entry_time
        duration_str = str(duration).split('.')[0]  # Remove microseconds
        
        with open(EXIT_LOG, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                plate_number,
                entry_time_str,
                exit_time.strftime('%Y-%m-%d %H:%M:%S'),
                duration_str,
                amount_paid
            ])
        
        log_activity('EXIT', plate_number, f'Exited after {duration_str}', 'SUCCESS')
        
    except Exception as e:
        print(f"Error logging exit: {e}")

if __name__ == '__main__':
    # Create necessary files
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Plate Number', 'Payment Status', 'Timestamp'])
    
    if not os.path.exists(PAYMENT_LOG):
        open(PAYMENT_LOG, 'w').close()
    
    if not os.path.exists(SECURITY_LOG_FILE):
        with open(SECURITY_LOG_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Timestamp', 'Plate Number', 'Alert Type', 'Status', 'Action Taken', 'Personnel Notified'])
    
    create_exit_log_if_not_exists()
    
    # Start log watcher thread
    Thread(target=watch_logs, daemon=True).start()
    
    print("🚗 Smart Parking Management System Web Interface")
    print("🌐 Access dashboard at: http://localhost:5000")
    print("📊 Real-time monitoring: Entry | Payment | Exit | Security")
    
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)