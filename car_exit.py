import os
import time
import glob
import serial
import serial.tools.list_ports
import pytesseract
import cv2
from ultralytics import YOLO
import re
import threading
from collections import deque, Counter
from datetime import datetime
import csv

# Point pytesseract at the system binary on Linux
pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

MODEL_PATH = os.path.expanduser("/home/viateur/Documents/parking-management-system/best.pt")
model = YOLO(MODEL_PATH)

# BUFFER & PLATE-FINDING SETUP
BUFFER_SIZE = 3
plate_buffer = deque(maxlen=BUFFER_SIZE)
plate_pattern = re.compile(r'([A-Z]{3}\d{3}[A-Z])')
exit_cooldown = 60  # Shorter cooldown for exit
last_processed_plate = None
last_exit_time = 0

# CSV log files
CSV_FILE = 'plates_log.csv'
SECURITY_LOG_FILE = 'security_alerts.csv'

# Security Alert Configuration - REDUCED TO 5 SECONDS
ALERT_DURATION = 5  # 5 seconds for ALL unauthorized exit attempts
MAX_UNAUTHORIZED_ATTEMPTS = 3  # Max attempts before lockdown
unauthorized_attempts = {}  # Track attempts per plate

print("[EXIT SYSTEM] 🚨 Enhanced Security Mode - 5 Second Alerts. Press 'q' to exit.")

# ===== Auto-detect Arduino Serial Port =====
def detect_arduino_port():
    for dev in glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"):
        return dev
    for port in serial.tools.list_ports.comports():
        desc = port.description.lower()
        if 'arduino' in desc or 'usb-serial' in desc:
            return port.device
    return None

arduino_port = detect_arduino_port()
if arduino_port:
    print(f"[CONNECTED] Arduino on {arduino_port}")
    arduino = serial.Serial(arduino_port, 9600, timeout=1)
    time.sleep(2)
else:
    print("[ERROR] Arduino not detected.")
    arduino = None

# ===== Initialize Security Log =====
def initialize_security_log():
    """Create security alerts log if it doesn't exist"""
    if not os.path.exists(SECURITY_LOG_FILE):
        with open(SECURITY_LOG_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Timestamp', 'Plate Number', 'Alert Type', 'Status', 'Action Taken', 'Personnel Notified'])
        print(f"[SECURITY] Created {SECURITY_LOG_FILE}")

initialize_security_log()

# ===== Read Distance from Arduino =====
def read_distance():
    """
    Reads a distance (float) value from the Arduino via serial.
    Returns the float if valid, or None if invalid/empty.
    """
    if arduino and arduino.in_waiting > 0:
        try:
            line = arduino.readline().decode('utf-8').strip()
            return float(line)
        except ValueError:
            return None
    return None

# ===== Check Payment Status in CSV =====
def is_payment_complete(plate_number):
    """
    Check if the plate has completed payment (Payment Status = '1')
    Returns True if payment is complete, False otherwise
    """
    if not os.path.exists(CSV_FILE):
        print(f"[ERROR] CSV file {CSV_FILE} not found")
        return False
    
    try:
        with open(CSV_FILE, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if (row['Plate Number'] == plate_number and 
                    row['Payment Status'] == '1'):
                    print(f"[PAYMENT VERIFIED] ✅ {plate_number} has paid")
                    return True
        
        print(f"[PAYMENT PENDING] ⚠️ {plate_number} has not paid or not found")
        return False
        
    except Exception as e:
        print(f"[ERROR] Failed to read CSV: {e}")
        return False

# ===== Security Alert Functions =====
def log_security_alert(plate_number, alert_type, status, action_taken):
    """Log security alerts to CSV"""
    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(SECURITY_LOG_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, plate_number, alert_type, status, action_taken, 'YES'])
        print(f"[SECURITY LOG] 📝 {alert_type} alert logged for {plate_number}")
    except Exception as e:
        print(f"[ERROR] Failed to log security alert: {e}")

def trigger_unauthorized_exit_alarm(plate_number, arduino_conn):
    """
    Trigger 5-second alarm for ALL unauthorized exit attempts
    """
    try:
        print(f"[🚨 SECURITY ALERT] UNAUTHORIZED EXIT ATTEMPT: {plate_number}")
        print(f"[🚨 ALERT] Sounding 5-second alarm...")
        print(f"[📞 ALERT] Security personnel notification activated!")
        
        # Track unauthorized attempts
        if plate_number not in unauthorized_attempts:
            unauthorized_attempts[plate_number] = 0
        unauthorized_attempts[plate_number] += 1
        
        attempt_count = unauthorized_attempts[plate_number]
        print(f"[⚠️ WARNING] Attempt #{attempt_count} for {plate_number}")
        
        # Determine alert type based on attempts (but ALL get 5-second duration)
        if attempt_count >= MAX_UNAUTHORIZED_ATTEMPTS:
            alert_type = "CRITICAL_SECURITY_BREACH"
            action_taken = f"LOCKDOWN_INITIATED_AFTER_{attempt_count}_ATTEMPTS"
            arduino_signal = b'9'  # Critical alert signal
            print(f"[🔒 LOCKDOWN] Critical security breach - {attempt_count} unauthorized attempts!")
        elif attempt_count >= 2:
            alert_type = "HIGH_PRIORITY_ALERT"
            action_taken = f"REPEATED_UNAUTHORIZED_ATTEMPT_{attempt_count}"
            arduino_signal = b'8'  # High priority alert signal
            print(f"[⚡ HIGH ALERT] Repeated unauthorized attempt!")
        else:
            alert_type = "UNAUTHORIZED_EXIT_ATTEMPT"
            action_taken = "ALARM_ACTIVATED_GATE_BLOCKED"
            arduino_signal = b'2'  # Standard alert signal
            print(f"[🚨 ALERT] First unauthorized attempt!")
        
        # Send alarm signal to Arduino
        arduino_conn.write(arduino_signal)
        print(f"[🔊 ALARM] {alert_type} - 5 SECOND BUZZER ACTIVATED")
        
        # Display security message
        print("=" * 60)
        print("🚨 5-SECOND SECURITY ALERT ACTIVATED 🚨")
        print(f"Vehicle: {plate_number}")
        print(f"Alert Level: {alert_type}")
        print(f"Attempt Count: #{attempt_count}")
        print(f"Duration: 5 SECONDS (ALL ATTEMPTS)")
        print(f"Status: PAYMENT REQUIRED - EXIT DENIED")
        print(f"Action: SECURITY PERSONNEL NOTIFIED")
        print("=" * 60)
        
        # ALL alerts get exactly 5 seconds - no exceptions
        print(f"[⏰ TIMER] 5-second alarm countdown:")
        for remaining in range(5, 0, -1):
            print(f"   🔊 {remaining} seconds remaining - BUZZER ACTIVE")
            time.sleep(1)
        
        # Stop alarm after exactly 5 seconds
        arduino_conn.write(b'0')
        print(f"[🔕 ALARM] Security alarm deactivated after 5 seconds")
        
        # Log the security incident
        log_security_alert(plate_number, alert_type, "ACTIVE", action_taken)
        
        # Generate incident report for critical cases only
        if attempt_count >= MAX_UNAUTHORIZED_ATTEMPTS:
            print(f"[📋 REPORT] Generating incident report for {plate_number}")
            generate_incident_report(plate_number, attempt_count)
        
    except Exception as e:
        print(f"[ERROR] Security alarm failed: {e}")

def generate_incident_report(plate_number, attempts):
    """Generate detailed incident report for security review"""
    try:
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        report_file = f"incident_report_{plate_number}_{timestamp}.txt"
        
        with open(report_file, 'w') as f:
            f.write("=" * 50 + "\n")
            f.write("PARKING SECURITY INCIDENT REPORT\n")
            f.write("=" * 50 + "\n")
            f.write(f"Incident Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Vehicle Plate: {plate_number}\n")
            f.write(f"Total Unauthorized Attempts: {attempts}\n")
            f.write(f"Alert Duration: 5 seconds (standard for all)\n")
            f.write(f"Alert Level: CRITICAL SECURITY BREACH\n")
            f.write(f"Action Taken: SYSTEM LOCKDOWN INITIATED\n")
            f.write(f"Security Personnel: NOTIFIED\n")
            f.write("=" * 50 + "\n")
            f.write("RECOMMENDED ACTIONS:\n")
            f.write("1. Manual security intervention required\n")
            f.write("2. Verify vehicle and driver identity\n")
            f.write("3. Check payment status manually\n")
            f.write("4. Consider penalties for repeated violations\n")
            f.write("=" * 50 + "\n")
        
        print(f"[📄 REPORT] Incident report saved: {report_file}")
        
    except Exception as e:
        print(f"[ERROR] Failed to generate incident report: {e}")

def reset_unauthorized_attempts(plate_number):
    """Reset unauthorized attempts counter after successful payment"""
    if plate_number in unauthorized_attempts:
        del unauthorized_attempts[plate_number]
        print(f"[✅ CLEARED] Unauthorized attempts reset for {plate_number}")

# ===== Enhanced Gate Control =====
def open_gate(arduino_conn, open_duration=10):
    """Open the exit gate for paid vehicles"""
    try:
        arduino_conn.write(b'1')
        print("[GATE] ✅ Opening exit gate for authorized vehicle")
        time.sleep(open_duration)
        arduino_conn.write(b'0')
        print("[GATE] 🔒 Closing exit gate")
    except Exception as e:
        print(f"[ERROR] Gate control failed: {e}")

def trigger_alert(arduino_conn):
    """Legacy function - redirects to unauthorized exit alarm"""
    print("[LEGACY] Redirecting to unauthorized exit alarm...")
    # Use a placeholder plate for legacy calls
    trigger_unauthorized_exit_alarm("UNKNOWN", arduino_conn)

# ===== Camera Initialization with Fallback =====
def initialize_camera():
    """Try to find and initialize a working camera"""
    print("[CAMERA] Initializing exit camera...")
    
    for camera_index in range(3):  # Try indices 0-2
        print(f"[CAMERA] Trying camera index {camera_index}...")
        cap = cv2.VideoCapture(camera_index)
        
        if cap.isOpened():
            ret, test_frame = cap.read()
            if ret:
                print(f"[CAMERA] ✅ Exit camera connected at index {camera_index}")
                return cap, camera_index
            else:
                cap.release()
        print(f"[CAMERA] ❌ Camera {camera_index} failed")
    
    print("[CAMERA] ❌ No working cameras found for exit")
    return None, -1

# ===== Enhanced Exit Logging =====
def log_exit_to_csv(plate_number, exit_type="AUTHORIZED"):
    """Log vehicle exit to exit_log.csv with security status"""
    try:
        # Get entry time from plates_log.csv
        entry_time = None
        amount_paid = 0
        
        with open('plates_log.csv', 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['Plate Number'] == plate_number:
                    entry_time = row['Timestamp']
                    break
        
        if entry_time:
            exit_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            entry_dt = datetime.strptime(entry_time, '%Y-%m-%d %H:%M:%S')
            exit_dt = datetime.strptime(exit_time, '%Y-%m-%d %H:%M:%S')
            duration = str(exit_dt - entry_dt).split('.')[0]
            
            # Calculate amount paid (if authorized exit)
            if exit_type == "AUTHORIZED":
                # Calculate based on duration and hourly rate
                hours = (exit_dt - entry_dt).total_seconds() / 3600
                amount_paid = max(500, int(hours * 500))  # 500 RWF per hour, minimum 500
                
            # Create exit log with headers if it doesn't exist
            if not os.path.exists('exit_log.csv'):
                with open('exit_log.csv', 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['Plate Number', 'Entry Time', 'Exit Time', 'Duration', 'Amount Paid', 'Exit Type', 'Security Status'])
            
            with open('exit_log.csv', 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([plate_number, entry_time, exit_time, duration, amount_paid, exit_type, 
                               "CLEARED" if exit_type == "AUTHORIZED" else "FLAGGED"])
                
            print(f"[EXIT LOGGED] 📝 {plate_number} logged as {exit_type} exit")
            
        else:
            print(f"[WARNING] No entry record found for {plate_number}")
            
    except Exception as e:
        print(f"[ERROR] Failed to log exit: {e}")

# Initialize webcam
cap, camera_index = initialize_camera()

if cap is None:
    print("[EXIT SYSTEM] Running without camera - using simulation mode")
    simulation_mode = True
else:
    simulation_mode = False

# Main loop
while True:
    if simulation_mode:
        # Enhanced simulation mode for testing 5-second security features
        print("\n[SIMULATION] 5-Second Security Test Mode:")
        print("1. Press Enter to simulate authorized vehicle")
        print("2. Type 'unauthorized' to simulate unauthorized exit (5s alarm)")
        print("3. Type 'repeat' to simulate repeated unauthorized attempts (5s each)")
        print("4. Type 'q' to quit")
        
        user_input = input("Choice: ").strip().lower()
        if user_input == 'q':
            break
        elif user_input == 'unauthorized':
            test_plates = ["UNAUTH1", "UNAUTH2"]
        elif user_input == 'repeat':
            test_plates = ["REPEAT1"] * 4  # Simulate 4 attempts
        else:
            test_plates = ["RAD667J"]  # Authorized plate
        
        for plate in test_plates:
            print(f"\n[SIMULATED] Testing plate: {plate}")
            if is_payment_complete(plate):
                print(f"[ACCESS GRANTED] ✅ {plate} - Payment verified, opening gate")
                if arduino:
                    threading.Thread(target=open_gate, args=(arduino,)).start()
                
                # Reset unauthorized attempts on successful payment
                reset_unauthorized_attempts(plate)
                
                # Log authorized exit
                log_exit_to_csv(plate, "AUTHORIZED")
                
            else:
                print(f"[ACCESS DENIED] ❌ {plate} - UNAUTHORIZED EXIT ATTEMPT")
                if arduino:
                    # Trigger 5-second security alarm in separate thread
                    threading.Thread(target=trigger_unauthorized_exit_alarm, args=(plate, arduino)).start()
                else:
                    # Simulate 5-second alarm for testing without Arduino
                    print(f"[🚨 SIMULATED ALARM] 5-second security alert for {plate}")
                    log_security_alert(plate, "UNAUTHORIZED_EXIT_ATTEMPT", "SIMULATED", "5_SECOND_ALARM_ACTIVATED")
                
                # Log unauthorized attempt
                log_exit_to_csv(plate, "UNAUTHORIZED")
            
            time.sleep(2)
        continue
    
    # Camera mode
    ret, frame = cap.read()
    if not ret:
        print("[ERROR] Failed to read from camera")
        break

    distance = read_distance()

    # Skip processing if no valid distance
    if distance is None:
        cv2.imshow('Exit Webcam Feed', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        continue

    # Process only when vehicle is close
    if distance <= 50:
        results = model(frame)
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                plate_img = frame[y1:y2, x1:x2]

                # Image preprocessing
                gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
                blur = cv2.GaussianBlur(gray, (5, 5), 0)
                thresh = cv2.threshold(
                    blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
                )[1]

                # OCR
                plate_text = pytesseract.image_to_string(
                    thresh,
                    config='--psm 8 --oem 3 '
                           '-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                ).strip().replace(" ", "")

                match = plate_pattern.search(plate_text)
                if match:
                    plate = match.group(1)
                    print(f"[DETECTED] Exit plate: {plate}")
                    plate_buffer.append(plate)

                    if len(plate_buffer) == BUFFER_SIZE:
                        most_common, _ = Counter(plate_buffer).most_common(1)[0]
                        plate_buffer.clear()
                        now = time.time()

                        # Prevent duplicate processing
                        if (most_common != last_processed_plate or
                           (now - last_exit_time) > exit_cooldown):
                            
                            # Check payment status
                            if is_payment_complete(most_common):
                                print(f"[ACCESS GRANTED] ✅ {most_common} - Payment verified")
                                if arduino:
                                    threading.Thread(target=open_gate, args=(arduino,)).start()
                                
                                # Reset unauthorized attempts on successful payment
                                reset_unauthorized_attempts(most_common)
                                
                                # Log successful exit
                                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                print(f"[EXIT LOGGED] ✅ {most_common} exited at {timestamp}")
                                log_exit_to_csv(most_common, "AUTHORIZED")
                                
                            else:
                                print(f"[ACCESS DENIED] ❌ {most_common} - UNAUTHORIZED EXIT ATTEMPT")
                                if arduino:
                                    # Trigger 5-second security alarm in separate thread
                                    threading.Thread(target=trigger_unauthorized_exit_alarm, args=(most_common, arduino)).start()
                                
                                # Log unauthorized attempt
                                log_exit_to_csv(most_common, "UNAUTHORIZED")

                            last_processed_plate = most_common
                            last_exit_time = now
                        else:
                            print(f"[SKIPPED] {most_common} - Recent exit attempt")

                cv2.imshow("Exit Plate", plate_img)
                cv2.imshow("Processed Plate", thresh)

        annotated_frame = results[0].plot() if results else frame
    else:
        annotated_frame = frame

    cv2.imshow('Exit Webcam Feed', annotated_frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Cleanup
if cap:
    cap.release()
if arduino:
    arduino.close()
cv2.destroyAllWindows()

# Display final security summary
print("\n" + "=" * 60)
print("🚨 EXIT SYSTEM SECURITY SUMMARY")
print("=" * 60)
if unauthorized_attempts:
    print("⚠️ VEHICLES WITH UNAUTHORIZED ATTEMPTS:")
    for plate, attempts in unauthorized_attempts.items():
        print(f"   {plate}: {attempts} attempt(s) - 5 seconds each")
else:
    print("✅ NO UNAUTHORIZED EXIT ATTEMPTS DETECTED")

print(f"📄 Security logs saved to: {SECURITY_LOG_FILE}")
print("[EXIT SYSTEM] 🔒 Shutdown complete")