#include <Servo.h>

// Pin Definitions (matching your existing setup)
#define TRIGGER_PIN 2
#define ECHO_PIN 3
#define RED_LED_PIN 4
#define BLUE_LED_PIN 5
#define SERVO_PIN 6
#define GND_PIN_1 7
#define GND_PIN_2 8
#define BUZZER_PIN 11

// System State
bool gateOpen = false;
unsigned long lastBuzzTime = 0;
const unsigned long buzzInterval = 300;
bool buzzerState = false;
bool alertActive = false;
bool securityAlertActive = false;

// Security Alert Configuration
int alertType = 0; // 0=none, 1=standard, 2=high, 3=critical
unsigned long alertStartTime = 0;
const unsigned long ALERT_DURATION = 5000;  // 5 seconds for all alerts

Servo barrierServo;

// ================== INITIALIZATION ==================
void setup() {
  Serial.begin(9600);
  
  // Initialize pins
  pinMode(TRIGGER_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(BLUE_LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(GND_PIN_1, OUTPUT);
  pinMode(GND_PIN_2, OUTPUT);
  
  // Set ground pins
  digitalWrite(GND_PIN_1, LOW);
  digitalWrite(GND_PIN_2, LOW);
  
  // Initialize servo
  barrierServo.attach(SERVO_PIN);
  barrierServo.write(6); // Start with closed gate
  
  // Initial state
  digitalWrite(RED_LED_PIN, HIGH);
  
  // Startup indication
  tone(BUZZER_PIN, 1000, 500);
  delay(1000);
  
  Serial.println(F("READY"));
}

// ================== CORE FUNCTIONS ==================
float measureDistance() {
  digitalWrite(TRIGGER_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIGGER_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIGGER_PIN, LOW);
  
  long duration = pulseIn(ECHO_PIN, HIGH);
  return (duration * 0.0343) / 2.0;
}

// ================== GATE CONTROL ==================
void openGate() {
  if(alertActive || securityAlertActive) return;
  
  barrierServo.write(90);
  gateOpen = true;
  digitalWrite(BLUE_LED_PIN, HIGH);
  digitalWrite(RED_LED_PIN, LOW);
}

void closeGate() {
  barrierServo.write(6);
  gateOpen = false;
  digitalWrite(BLUE_LED_PIN, LOW);
  digitalWrite(RED_LED_PIN, HIGH);
}

// ================== SECURITY ALERT SYSTEM ==================
void triggerStandardSecurityAlert() {
  securityAlertActive = true;
  alertType = 1;
  alertStartTime = millis();
  closeGate();
}

void triggerHighPriorityAlert() {
  securityAlertActive = true;
  alertType = 2;
  alertStartTime = millis();
  closeGate();
}

void triggerCriticalSecurityAlert() {
  securityAlertActive = true;
  alertType = 3;
  alertStartTime = millis();
  closeGate();
}

void triggerBasicAlert() {
  alertActive = true;
  digitalWrite(RED_LED_PIN, HIGH);
  digitalWrite(BUZZER_PIN, HIGH);
}

void stopAllAlerts() {
  securityAlertActive = false;
  alertActive = false;
  alertType = 0;
  digitalWrite(RED_LED_PIN, LOW);
  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(BLUE_LED_PIN, LOW);
  noTone(BUZZER_PIN);
}

// ================== SECURITY ALERT PATTERNS ==================
void handleSecurityAlerts() {
  if (!securityAlertActive) return;
  
  unsigned long currentTime = millis();
  unsigned long alertDuration = currentTime - alertStartTime;
  
  if (alertDuration >= ALERT_DURATION) {
    stopAllAlerts();
    return;
  }
  
  switch(alertType) {
    case 1: // Standard unauthorized exit - 500ms cycles
      {
        int cycle = (alertDuration / 500) % 2;
        if (cycle == 0) {
          digitalWrite(RED_LED_PIN, HIGH);
          tone(BUZZER_PIN, 3000, 450);
        } else {
          digitalWrite(RED_LED_PIN, LOW);
          noTone(BUZZER_PIN);
        }
      }
      break;
      
    case 2: // High priority - 200ms cycles (faster)
      {
        int cycle = (alertDuration / 200) % 2;
        if (cycle == 0) {
          digitalWrite(RED_LED_PIN, HIGH);
          tone(BUZZER_PIN, 3500, 180);
        } else {
          digitalWrite(RED_LED_PIN, LOW);
          noTone(BUZZER_PIN);
        }
      }
      break;
      
    case 3: // Critical - 1000ms cycles with alternating LEDs
      {
        int cycle = (alertDuration / 1000) % 2;
        if (cycle == 0) {
          digitalWrite(RED_LED_PIN, HIGH);
          digitalWrite(BLUE_LED_PIN, LOW);
          tone(BUZZER_PIN, 4000, 900);
        } else {
          digitalWrite(RED_LED_PIN, LOW);
          digitalWrite(BLUE_LED_PIN, HIGH);
          tone(BUZZER_PIN, 3000, 900);
        }
      }
      break;
  }
}

// ================== COMMAND HANDLER ==================
void handleSerialCommands() {
  if (Serial.available()) {
    char cmd = Serial.read();
    
    switch(cmd) {
      case '1': // Open gate (authorized exit)
        openGate();
        break;
        
      case '0': // Close gate / Stop all alerts
        closeGate();
        stopAllAlerts();
        break;
        
      case '2': // Standard unauthorized exit alert
        triggerStandardSecurityAlert();
        break;
        
      case '3': // Warning signal (payment pending)
        triggerBasicAlert();
        delay(2000);
        stopAllAlerts();
        break;
        
      case '8': // High priority alert
        triggerHighPriorityAlert();
        break;
        
      case '9': // Critical security breach
        triggerCriticalSecurityAlert();
        break;
    }
  }
}

// ================== NORMAL BUZZER CONTROL ==================
void handleNormalBuzzer() {
  if (gateOpen && !alertActive && !securityAlertActive) {
    unsigned long currentMillis = millis();
    if (currentMillis - lastBuzzTime >= buzzInterval) {
      buzzerState = !buzzerState;
      digitalWrite(BUZZER_PIN, buzzerState);
      lastBuzzTime = currentMillis;
    }
  }
}

// ================== MAIN LOOP ==================
void loop() {
  // 1. Distance monitoring and reporting
  float distance = measureDistance();
  Serial.println(distance);
  
  // 2. Handle incoming commands from Python
  handleSerialCommands();
  
  // 3. Process active security alerts
  handleSecurityAlerts();
  
  // 4. Handle normal buzzer operation
  handleNormalBuzzer();
  
  // Main loop delay
  delay(50);
}
