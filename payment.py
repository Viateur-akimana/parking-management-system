import math
import serial
import csv
from datetime import datetime, timedelta
import os
import time
import glob

# Configuration
CSV_FILE = 'plates_log.csv'
HOURLY_RATE = 500       # RWF per hour
MINIMUM_CHARGE = 500    # Always charge 500 RWF minimum for any parking
FREE_MINUTES = 0        # No free time - charge from first minute

def find_arduino_port():
    """Automatically find the Arduino port"""
    possible_ports = ['/dev/ttyACM0', '/dev/ttyACM1', '/dev/ttyUSB0', '/dev/ttyUSB1']
    possible_ports.extend(glob.glob('/dev/ttyACM*'))
    possible_ports.extend(glob.glob('/dev/ttyUSB*'))
    
    for port in list(set(possible_ports)):
        try:
            print(f"🔌 Trying {port}...")
            ser = serial.Serial(port, 9600, timeout=1)
            time.sleep(2)
            if ser.is_open:
                print(f"✅ Found Arduino on {port}")
                return ser
        except (serial.SerialException, OSError):
            continue
    
    print("❌ No Arduino found")
    return None

def calculate_charges(plate_number):
    """Calculate charges with 500 RWF minimum for any parking session"""
    if not os.path.exists(CSV_FILE):
        return 0, 0, "No records"

    total_charge = 0
    unpaid_sessions = 0
    total_duration_minutes = 0
    current_time = datetime.now()

    print(f"💰 Calculating charges for {plate_number}...")

    try:
        with open(CSV_FILE, 'r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row['Plate Number'] == plate_number and row['Payment Status'] == '0':
                    try:
                        entry_time = datetime.strptime(row['Timestamp'], '%Y-%m-%d %H:%M:%S')
                        duration = current_time - entry_time
                        minutes = duration.total_seconds() / 60
                        total_duration_minutes += minutes
                        
                        print(f"   📅 Session: {entry_time} → {minutes:.1f} minutes")
                        
                        # Calculate charge for this session
                        if minutes > 0:  # Any parking time gets charged
                            # Round up to nearest hour for additional charges beyond first 500
                            hours = math.ceil(minutes / 60)
                            session_charge = max(hours * HOURLY_RATE, MINIMUM_CHARGE)
                            total_charge += session_charge
                            unpaid_sessions += 1
                            
                            print(f"   💸 Session charge: {session_charge} RWF ({hours} hour(s))")
                        
                    except ValueError as e:
                        print(f"   ⚠️ Date parsing error: {e}")
                        continue

        # Format duration string
        if total_duration_minutes > 0:
            hours = int(total_duration_minutes // 60)
            minutes = int(total_duration_minutes % 60)
            duration_str = f"{hours}:{minutes:02d}:00"
        else:
            duration_str = "No active sessions"

        print(f"📊 Summary: {unpaid_sessions} sessions, {total_charge} RWF total")
        return total_charge, unpaid_sessions, duration_str

    except Exception as e:
        print(f"❌ Error calculating charges: {e}")
        return 0, 0, "Calculation error"

def update_csv(plate_number):
    """Update payment status for all unpaid sessions"""
    if not os.path.exists(CSV_FILE):
        return False

    try:
        updated_rows = []
        sessions_updated = 0

        with open(CSV_FILE, 'r') as file:
            reader = csv.DictReader(file)
            fieldnames = reader.fieldnames
            for row in reader:
                if row['Plate Number'] == plate_number and row['Payment Status'] == '0':
                    row['Payment Status'] = '1'  # Mark as paid
                    sessions_updated += 1
                updated_rows.append(row)

        with open(CSV_FILE, 'w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(updated_rows)

        print(f"✅ Updated {sessions_updated} sessions to PAID")
        return True

    except Exception as e:
        print(f"❌ Error updating CSV: {e}")
        return False

def process_payment(plate_number, current_balance):
    """Process payment with 500 RWF minimum charge"""
    try:
        print(f"\n💳 Processing payment for {plate_number} (Balance: {current_balance} RWF)")
        
        total_charge, sessions, duration = calculate_charges(plate_number)

        if sessions == 0:
            print(f"✅ No unpaid parking sessions for {plate_number}")
            return "NO_PARKING_SESSIONS", current_balance, duration

        print(f"💰 Total charge: {total_charge} RWF for {sessions} session(s)")
        print(f"⏱️ Duration: {duration}")

        if current_balance < total_charge:
            shortage = total_charge - current_balance
            print(f"❌ Insufficient funds: Need {total_charge}, have {current_balance} (short {shortage})")
            return f"INSUFFICIENT_FUNDS:{total_charge},{current_balance}", current_balance, duration

        # Process payment
        new_balance = current_balance - total_charge
        
        if update_csv(plate_number):
            print(f"✅ Payment successful: {total_charge} RWF charged, new balance: {new_balance} RWF")
            return "PAYMENT_SUCCESS", new_balance, duration
        else:
            print(f"❌ Failed to update payment records")
            return "UPDATE_ERROR", current_balance, duration

    except Exception as e:
        error_msg = f"PROCESSING_ERROR: {str(e)}"
        print(f"❌ {error_msg}")
        return error_msg, current_balance, "Error"

def safe_serial_read(ser):
    """Safely read from serial with error handling"""
    try:
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            return line
    except Exception as e:
        print(f"⚠️ Read error: {e}")
        return None
    return None

def safe_serial_write(ser, message):
    """Safely write to serial with error handling"""
    try:
        response = f"{message}\n".encode('utf-8')
        ser.write(response)
        print(f"📤 Sent: {message}")
        return True
    except Exception as e:
        print(f"❌ Write error: {e}")
        return False

def main():
    """Main payment processing loop"""
    print("🏧 PARKING PAYMENT SYSTEM")
    print("=" * 50)
    print(f"💰 Hourly Rate: {HOURLY_RATE} RWF")
    print(f"🎯 Minimum Charge: {MINIMUM_CHARGE} RWF (for any parking)")
    print(f"⚡ Policy: ANY parking session = {MINIMUM_CHARGE} RWF minimum")
    print("=" * 50)

    # Initialize serial connection
    ser = find_arduino_port()
    if not ser:
        print("❌ Cannot start without Arduino connection")
        return

    print("✅ Payment System Running. Waiting for RFID scans...")
    print("🛑 Press Ctrl+C to stop\n")

    while True:
        try:
            line = safe_serial_read(ser)
            
            if line:
                print(f"📨 Received: '{line}'")

                # Handle both PROCESS_PAYMENT and CALCULATE_PAYMENT formats
                if line.startswith("PROCESS_PAYMENT:") or line.startswith("CALCULATE_PAYMENT:"):
                    try:
                        # Extract data based on prefix
                        if line.startswith("CALCULATE_PAYMENT:"):
                            data = line[18:].split(',')  # Remove "CALCULATE_PAYMENT:"
                        else:
                            data = line[16:].split(',')  # Remove "PROCESS_PAYMENT:"
                        
                        if len(data) >= 2:
                            plate_number = data[0].strip()
                            current_balance = int(data[1].strip())

                            # Process payment
                            status, new_balance, duration = process_payment(plate_number, current_balance)

                            # Send appropriate response based on status
                            if status == "PAYMENT_SUCCESS":
                                charged_amount = current_balance - new_balance
                                safe_serial_write(ser, f"PAYMENT_SUCCESS:{new_balance},{charged_amount},{duration}")
                                
                            elif status.startswith("INSUFFICIENT_FUNDS:"):
                                safe_serial_write(ser, status)
                                
                            elif status == "NO_PARKING_SESSIONS":
                                safe_serial_write(ser, "NO_PARKING_SESSIONS")
                                
                            else:
                                safe_serial_write(ser, f"ERROR:{status}")

                            # Log transaction
                            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            
                            if status == "PAYMENT_SUCCESS":
                                charged_amount = current_balance - new_balance
                                log_entry = f"{timestamp} - {plate_number} - SUCCESS: Charged {charged_amount} RWF for {duration} parking, Balance: {current_balance} → {new_balance} RWF"
                            elif status.startswith("INSUFFICIENT_FUNDS:"):
                                parts = status.split(':')[1].split(',')
                                required = parts[0] if len(parts) > 0 else "Unknown"
                                log_entry = f"{timestamp} - {plate_number} - INSUFFICIENT_FUNDS: Required {required} RWF, Available {current_balance} RWF"
                            elif status == "NO_PARKING_SESSIONS":
                                log_entry = f"{timestamp} - {plate_number} - NO_PARKING_SESSIONS: No unpaid sessions found"
                            else:
                                log_entry = f"{timestamp} - {plate_number} - ERROR: {status}"

                            print(f"📝 {log_entry}")
                            
                            try:
                                with open('payment_log.txt', 'a') as log_file:
                                    log_file.write(log_entry + '\n')
                            except Exception as e:
                                print(f"⚠️ Log write error: {e}")

                        else:
                            print(f"❌ Invalid data format: {line}")
                            safe_serial_write(ser, "ERROR:Invalid data format")
                            
                    except ValueError as e:
                        print(f"❌ Value error: {e}")
                        safe_serial_write(ser, "ERROR:Invalid balance format")
                    except Exception as e:
                        print(f"❌ Processing error: {e}")
                        safe_serial_write(ser, f"ERROR:Processing failed")

                elif line.startswith("INSUFFICIENT_BALANCE:"):
                    balance = line[len("INSUFFICIENT_BALANCE:"):]
                    print(f"⚠️ Insufficient balance detected: {balance}")

                elif line:  # Any other message
                    print(f"ℹ️ Info: {line}")

            time.sleep(0.05)  # Small delay to prevent CPU overload

        except KeyboardInterrupt:
            print("\n🛑 Shutting down payment system...")
            break
            
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            time.sleep(1)
            continue

    # Cleanup
    try:
        if ser and ser.is_open:
            ser.close()
            print("📴 Serial connection closed")
    except:
        pass

if __name__ == "__main__":
    # Create CSV file if it doesn't exist
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['Plate Number', 'Payment Status', 'Timestamp'])
        print(f"📄 Created {CSV_FILE}")

    main()