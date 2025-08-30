#define BLYNK_TEMPLATE_ID "TMPL377-UGdlS"
#define BLYNK_TEMPLATE_NAME "Smart Bin IOT Based"  
#define BLYNK_AUTH_TOKEN "odwMhoGzbgdBqtK0XKF1Tx4WY5t3827F"
#define BLYNK_PRINT Serial

#include <WiFi.h>
#include <BlynkSimpleEsp32.h>

// WiFi credentials
char ssid[] = "Wifi";
char pass[] = "Password";

// Ultrasonic sensor pins
#define TRIG_PIN1 5   // ESP32 GPIO5 -> HC-SR04 Trig
#define ECHO_PIN1 18  // ESP32 GPIO18 -> HC-SR04 Echo
#define TRIG_PIN2 25   // ESP32 GPIO25 -> HC-SR04 Trig
#define ECHO_PIN2 33  // ESP32 GPIO33 -> HC-SR04 Echo

// Gas sensor
int mq2Pin = 34;

// Bin configuration  
#define BIN_HEIGHT 30  // Define your actual bin height in cm

// Sleep configuration
#define uS_TO_S_FACTOR 1000000ULL  
#define TIME_TO_SLEEP  3600        // 1 hour = 3600 seconds

// Motor control pins (adapted for ESP32)
const int ENALeft = 19;   // PWM pin for left motor speed
const int ENBRight = 21;  // PWM pin for right motor speed
const int motorIN1 = 4;   // Left motor direction
const int motorIN2 = 16;  // Left motor direction
const int motorIN3 = 17;  // Right motor direction
const int motorIN4 = 2;   // Right motor direction

// Line following IR sensor pins (adapted for ESP32)
const int SensorPin1 = 13;
const int SensorPin2 = 12;
const int SensorPin3 = 14;
const int SensorPin4 = 27;
const int SensorPin5 = 26;

// Blynk virtual pins
#define FILL_PIN V0          // Fill Level
#define BATTERY_PIN V1       // Battery Voltage  
#define ALERT_PIN V2         // Alert Status
#define GAS_PIN V3           // Gas Sensor PPM
#define MOTOR_STATUS_PIN V4  // Motor Status
#define IR_STATUS_PIN V5     // IR Sensor Status
#define NAV_STATE_PIN V6     // Navigation State

// PID constants for line follower
float Kp = 10;
float Ki = 0.5;
float Kd = 0;
float integral = 0;
int setvalue = 0;

// Motor speed settings
int baseSpeed = 170;
int leftmSpeed = 0;
int rightmSpeed = 0;

// System flags
bool isMoving = false;
bool isTurning = false;
bool isStalled = false;

BlynkTimer timer;

// Function to stop all motors
void stopMotor() {
  digitalWrite(motorIN1, LOW);
  digitalWrite(motorIN2, LOW);
  digitalWrite(motorIN3, LOW);
  digitalWrite(motorIN4, LOW);  
  analogWrite(ENALeft, 0);
  analogWrite(ENBRight, 0);
  isMoving = false;
  isTurning = false;
}

// Function to control motor movement
void TurnMotor(int left, int right) {
  // Left motor control
  if(left > 0) {
    digitalWrite(motorIN1, HIGH);
    digitalWrite(motorIN2, LOW);
  } else if(left < 0) {
    digitalWrite(motorIN1, LOW);
    digitalWrite(motorIN2, HIGH);
    left = -left;
  } else {
    digitalWrite(motorIN1, LOW);
    digitalWrite(motorIN2, LOW);
  }
  
  // Right motor control  
  if(right > 0) {
    digitalWrite(motorIN3, LOW);
    digitalWrite(motorIN4, HIGH);
  } else if(right < 0) {
    digitalWrite(motorIN3, HIGH);
    digitalWrite(motorIN4, LOW);
    right = -right;
  } else {
    digitalWrite(motorIN3, LOW);
    digitalWrite(motorIN4, LOW);
  }
  
  analogWrite(ENALeft, constrain(abs(left), 0, 255));
  analogWrite(ENBRight, constrain(abs(right), 0, 255));
  
  if(left != 0 || right != 0) {
    isMoving = true;
  }
}

// Function to rotate in place when line is lost
void Rotate() {
  digitalWrite(motorIN1, HIGH);
  digitalWrite(motorIN2, LOW);
  digitalWrite(motorIN3, HIGH);
  digitalWrite(motorIN4, LOW);  
  analogWrite(ENALeft, 150);
  analogWrite(ENBRight, 150);
  isTurning = true;
}

// Line following algorithm
void lineFollowingAlgorithm() {
  // Read IR sensors (0 for black line, 1 for white surface)
  int r1 = digitalRead(SensorPin1);
  int r2 = digitalRead(SensorPin2);
  int r3 = digitalRead(SensorPin3);
  int r4 = digitalRead(SensorPin4);
  int r5 = digitalRead(SensorPin5);
  
  delay(10);
  int total = r1 + r2 + r3 + r4 + r5;
  
  // If no sensors detect line, stop
  if (total == 0) {
    stopMotor();
    Blynk.virtualWrite(IR_STATUS_PIN, "No Line Detected");
    return;
  }
  
  // If all sensors detect white (line lost), rotate to find line
  if (r1 == 1 && r2 == 1 && r3 == 1 && r4 == 1 && r5 == 1) {
    Serial.println("Line Lost - Searching");
    Blynk.virtualWrite(IR_STATUS_PIN, "Line Lost - Searching");
    Rotate();
    delay(1000);
    return;
  }
  
  // Calculate position and error for PID control
  int position = (-2 * r1) + (-1 * r2) + (0 * r3) + (1 * r4) + (2 * r5);
  float avgpos = (float)position / total;
  int error = setvalue - avgpos;
  
  integral += error;
  int correction = (Kp * error) + (Ki * integral);
  
  leftmSpeed = constrain(baseSpeed + correction, 0, 255);
  rightmSpeed = constrain(baseSpeed - correction, 0, 255);
  
  TurnMotor(leftmSpeed, rightmSpeed);
  Blynk.virtualWrite(IR_STATUS_PIN, "Following Line");
}

// Update motor status for Blynk
void updateMotorStatus() {
  String motorStatus = "Stopped";
  
  if (isTurning) {
    motorStatus = "Searching for Line";
  } else if (isMoving) {
    motorStatus = "Moving";
  }
  
  Blynk.virtualWrite(MOTOR_STATUS_PIN, motorStatus);
}

// Gas sensor reading and transmission
void sendSensor() {
  int sensorValue = analogRead(mq2Pin);
  float voltage = sensorValue * (3.3 / 4095.0);
  int ppm = map(sensorValue, 0, 4095, 200, 10000);
  
  // Determine hazard status
  String status;
  if (ppm < 1000) {
    status = "SAFE ";
  } else if (ppm >= 1000 && ppm < 5000) {
    status = "CAUTION";
  } else {
    status = "DANGER";
  }
  
  Serial.print("Methane Level PPM: ");
  Serial.print(ppm);
  Serial.print("  Status: ");
  Serial.println(status);
  
  // Send to Blynk
  Blynk.virtualWrite(GAS_PIN, ppm);
  
  // Trigger gas alert if dangerous
  if (ppm > 5000) {
    Blynk.logEvent("gas_alert", "Dangerous methane levels detected!");
  }
}

// Measure bin fill level using ultrasonic sensors
float measureBinLevel() {
  long duration1, duration2;
  float distance_cm1, distance_cm2;

  // First sensor
  digitalWrite(TRIG_PIN1, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN1, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN1, LOW);
  duration1 = pulseIn(ECHO_PIN1, HIGH);
  distance_cm1 = duration1 * 0.034 / 2;

  // Second sensor  
  digitalWrite(TRIG_PIN2, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN2, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN2, LOW);
  duration2 = pulseIn(ECHO_PIN2, HIGH);
  distance_cm2 = duration2 * 0.034 / 2;

  // Calculate fill percentage
  float avgDistance = (distance_cm1 + distance_cm2) / 2.0;
  float fillPercent = ((BIN_HEIGHT - avgDistance) / BIN_HEIGHT) * 100;
  
  // Ensure percentage stays within bounds
  if (fillPercent < 0) fillPercent = 0;
  if (fillPercent > 100) fillPercent = 100;

  Serial.print("Distance1: ");
  Serial.print(distance_cm1);
  Serial.print(" cm, Distance2: ");
  Serial.print(distance_cm2);
  Serial.print(" cm, Fill Level: ");
  Serial.print(fillPercent);
  Serial.println("%");

  return fillPercent;
}

// Send all data to Blynk dashboard
void sendDataToBlynk(float fillPercent) {
  float batteryVoltage = 3.7; // Placeholder - replace with actual reading

  // Determine alert status
  String alertStatus = "Normal";
  if (fillPercent > 85) {
    alertStatus = "Overflow Alert!";
    Blynk.logEvent("overflow_alert", "Bin is nearly full!");
    Serial.println("OVERFLOW ALERT SENT!");
  } else if (batteryVoltage < 3.2) {
    alertStatus = "Low Battery";
  }

  // Send data to Blynk
  if (Blynk.connected()) {
    Serial.println("---------------------------------");
    Serial.println("Sending data to Blynk...");
    
    Blynk.virtualWrite(FILL_PIN, fillPercent);
    Blynk.virtualWrite(BATTERY_PIN, batteryVoltage);
    Blynk.virtualWrite(ALERT_PIN, alertStatus);
    
    sendSensor(); // Send gas data
    updateMotorStatus(); // Send motor status
    
    // REMOVED: Navigation state logic - just show monitoring
    Blynk.virtualWrite(NAV_STATE_PIN, "Monitoring");
    
    Blynk.run();
    delay(2000);
    
    Serial.println("Data sent to dashboard successfully!");
  } else {
    Serial.println("Skipping data transmission (Blynk not connected)");
  }
  
  // Debug output
  Serial.printf("Fill: %.1f%%, Battery: %.2fV, Alert: %s\n", 
                fillPercent, batteryVoltage, alertStatus.c_str());
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("=================================");
  Serial.println("    SMART BIN SYSTEM STARTING    ");
  Serial.println("=================================");
  
  // WiFi Connection
  Serial.print("Connecting to WiFi: ");
  Serial.println(ssid);
  WiFi.begin(ssid, pass);
  
  int wifi_attempts = 0;
  while (WiFi.status() != WL_CONNECTED && wifi_attempts < 20) {
    delay(500);
    Serial.print(".");
    wifi_attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.println("WiFi Connected Successfully!");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());
    Serial.print("Signal Strength: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");
  } else {
    Serial.println();
    Serial.println("WiFi Connection Failed!");
    Serial.println("Check your WiFi credentials and try again.");
    return;
  }

  // Blynk Connection
  Serial.println("---------------------------------");
  Serial.println("Connecting to Blynk Server...");
  Blynk.begin(BLYNK_AUTH_TOKEN, ssid, pass);
  
  unsigned long startTime = millis();
  int blynk_attempts = 0;
  while (!Blynk.connected() && millis() - startTime < 30000) {
    Blynk.run();
    delay(500);
    Serial.print(".");
    blynk_attempts++;
    
    if (blynk_attempts % 10 == 0) {
      Serial.println();
      Serial.print("Still trying to connect... (");
      Serial.print((millis() - startTime) / 1000);
      Serial.println("s)");
    }
  }

  Serial.println();
  if (Blynk.connected()) {
    Serial.println("BLYNK CONNECTED SUCCESSFULLY!");
    Serial.println("Dashboard is now receiving data");
    Serial.println("Check your Blynk app/web dashboard");
  } else {
    Serial.println("BLYNK CONNECTION FAILED!");
    Serial.println("Proceeding with local operation only");
    Serial.println("Check your auth token and internet connection");
  }

  Serial.println("=================================");

  // Pin setup
  pinMode(TRIG_PIN1, OUTPUT);
  pinMode(ECHO_PIN1, INPUT);
  pinMode(TRIG_PIN2, OUTPUT);
  pinMode(ECHO_PIN2, INPUT);
  
  pinMode(SensorPin1, INPUT);
  pinMode(SensorPin2, INPUT);
  pinMode(SensorPin3, INPUT);
  pinMode(SensorPin4, INPUT);
  pinMode(SensorPin5, INPUT);
  
  pinMode(ENALeft, OUTPUT);
  pinMode(ENBRight, OUTPUT);
  pinMode(motorIN1, OUTPUT);
  pinMode(motorIN2, OUTPUT);
  pinMode(motorIN3, OUTPUT);
  pinMode(motorIN4, OUTPUT);

  // Measure current fill level
  float currentFillLevel = measureBinLevel();
  
  // Send data to dashboard
  sendDataToBlynk(currentFillLevel);
  
  // REMOVED: Conditional navigation logic - just sleep regardless
  Serial.println("BIN STATUS CHECKED - ENTERING SLEEP MODE");
  Serial.println("Motors will remain OFF to save power");
  
  // Ensure motors are stopped
  stopMotor();
  
  // Configure and enter deep sleep
  esp_sleep_enable_timer_wakeup(TIME_TO_SLEEP * uS_TO_S_FACTOR);
  Serial.println("Going to sleep for 1 hour (3600 seconds)...");
  Serial.println("System will wake up automatically to check bin status");
  Serial.println("=================================");
  delay(100);
  
  // Enter deep sleep for 1 hour
  esp_deep_sleep_start();
}

void loop() {
  // This will not be used because ESP32 goes to deep sleep
  // ESP32 wakes up and runs setup() again after 1 hour
}
