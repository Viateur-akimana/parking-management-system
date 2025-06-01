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

# CSV log file
CSV_FILE = 'plates_log.csv'

print("[EXIT SYSTEM] Ready. Press 'q' to exit.")

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
                    print(f"[PAYMENT VERIFIED] {plate_number} has paid")
                    return True
        
        print(f"[PAYMENT PENDING] {plate_number} has not paid or not found")
        return False
        
    except Exception as e:
        print(f"[ERROR] Failed to read CSV: {e}")
        return False

# ===== Open Gate Function =====
def open_gate(arduino_conn, open_duration=10):
    """Open the exit gate for paid vehicles"""
    try:
        arduino_conn.write(b'1')
        print("[GATE] Opening exit gate")
        time.sleep(open_duration)
        arduino_conn.write(b'0')
        print("[GATE] Closing exit gate")
    except Exception as e:
        print(f"[ERROR] Gate control failed: {e}")

# ===== Trigger Alert =====
def trigger_alert(arduino_conn):
    """Trigger alert for unpaid vehicles"""
    try:
        arduino_conn.write(b'2')  # Send alert signal
        print("[ALERT] Access denied - payment required")
        time.sleep(3)
        arduino_conn.write(b'0')  # Stop alert
    except Exception as e:
        print(f"[ERROR] Alert trigger failed: {e}")

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
        # Simulation mode for testing without camera
        print("[SIMULATION] Press Enter to simulate vehicle detection or 'q' to quit:")
        user_input = input().strip().lower()
        if user_input == 'q':
            break
        
        # Simulate plate detection
        test_plates = ["RAH972U", "RAB123A", "RAC456B"]
        for plate in test_plates:
            print(f"[SIMULATED] Testing plate: {plate}")
            if is_payment_complete(plate):
                print(f"[ACCESS GRANTED] {plate} - Opening gate")
                if arduino:
                    threading.Thread(target=open_gate, args=(arduino,)).start()
            else:
                print(f"[ACCESS DENIED] {plate} - Payment required")
                if arduino:
                    threading.Thread(target=trigger_alert, args=(arduino,)).start()
            time.sleep(2)
        continue
    
    # Camera mode
    ret, frame = cap.read()
    if not ret:
        print("[ERROR] Failed to read from camera")
        break

    distance = read_distance()
    print(f"[SENSOR] Distance: {distance}")

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
                                print(f"[ACCESS GRANTED] {most_common} - Payment verified")
                                if arduino:
                                    threading.Thread(target=open_gate, args=(arduino,)).start()
                                
                                # Log successful exit
                                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                print(f"[EXIT LOGGED] {most_common} exited at {timestamp}")
                                
                            else:
                                print(f"[ACCESS DENIED] {most_common} - Payment required")
                                if arduino:
                                    threading.Thread(target=trigger_alert, args=(arduino,)).start()

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
print("[EXIT SYSTEM] Shutdown complete")