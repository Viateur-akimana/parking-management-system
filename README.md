# 🚗 Smart Parking Management System

A robust automated parking system featuring **license plate detection (YOLOv8)**, **OCR (Tesseract)**, **payment processing**, and **Arduino gate control**.

## ✨ Key Features

* **Real-time License Plate Detection** (YOLOv8)
* **OCR Text Extraction** (Tesseract)
* **Automated Payment Processing** (Card payment method)
* **Arduino Gate Control** (Ultrasonic sensor)
* **Logging & Analytics** (CSV/JSON logs)

## ⚙️ Installation

### **Prerequisites**
* Python 3.8+
* Tesseract OCR (`v5.3.0+`)
* Arduino IDE (for gate hardware)
* Webcam/USB Camera

### **1. Clone the Repository**
```bash
https://github.com/Viateur-akimana/parking-management-system.git
cd parking-management-system  
```

### **2. Install Python Dependencies**
```bash
pip install -r requirements.txt  
```

*(Example `requirements.txt`):*
```plaintext
ultralytics==8.0.0
opencv-python==4.8.0
pytesseract==0.3.10
pyserial==3.5
```

### **3. Set Up Tesseract OCR**
**Linux (Ubuntu)**:
```bash
sudo apt update && sudo apt install tesseract-ocr  
```

**Windows**: Download installer from Tesseract GitHub.

Verify installation:
```bash
tesseract --version  
```

### **4. Configure Paths**
Update `config.py` (or `car_entry.py`) with your Tesseract path:
```python
# For Linux/Mac  
pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'  

# For Windows  
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
```

### **5. Add YOLOv8 Model**
Place your trained model (`best.pt`) in:
```bash
mkdir -p trained/ && cp /path/to/your/model.pt trained/best.pt  
```

### **6. Hardware Setup**
* Connect Arduino via USB (`/dev/ttyUSB0` or `COM3`).
* Attach **ultrasonic sensor** (vehicle detection).
* Test with Arduino IDE's Serial Monitor.

## 🚀 Usage

### **1. Start Vehicle Entry System**
```bash
python car_entry.py  
```
* Detects plates → Saves crops to `/plates/`.
* Logs entries in `plates_log.csv`.

### **2. Run Payment System**
```bash
python payment.py  
```
* Set hourly rate in `payment.py`:
```python
HOURLY_RATE = 10  # $10/hour
MINIMUM_BALANCE = 20  # Reject if balance < $20
```

## 📝 Configuration

| File | Key Settings |
|------|-------------|
| `config.py` | Tesseract path, YOLO model path |
| `payment.py` | Hourly rate, payment APIs |
| `arduino_gate.ino` | Servo angles, sensor thresholds |

## 📂 Logs & Data

* **Detected Plates**: `logs/plates_log.csv`
```csv
Plate,Status,Timestamp
ABC123,PAID,2025-05-08 14:30:22
XYZ789,UNPAID,2025-05-08 15:12:10
```
* **Payments**: `logs/payment_log.txt`
* **System Errors**: `logs/error.log`

## 🛠 Troubleshooting

| Issue | Solution |
|-------|----------|
| Tesseract not found | Verify path in `config.py` |
| YOLOv8 model missing | Check `trained/best.pt` exists |
| Arduino not detected | Update port in `arduino_gate.ino` |
| Webcam error | Test with `cv2.VideoCapture(0)` |


## 📊 System Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Webcam/    │────▶│  YOLOv8     │────▶│  Tesseract  │
│  Camera     │     │  Detection  │     │  OCR        │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                              │
                                              ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Arduino    │◀────│  Payment    │◀────│  Plate      │
│  Gate       │     │  Processing │     │  Database   │
└─────────────┘     └─────────────┘     └─────────────┘
```


## 🙏 Acknowledgments

* **YOLOv8**: For object detection
* **Tesseract OCR**: For text recognition
* **Arduino Community**: For hardware integration examples
