/*
  Arduino Nano V3.0 - 15V Buzzer Control
  Receives commands from Python via Serial
  '1' = Turn ON buzzer
  '0' = Turn OFF buzzer
*/

// Define the buzzer pin (Digital Pin 9 - PWM capable)
#define BUZZER_PIN 9

void setup() {
  // Initialize serial communication at 9600 baud
  Serial.begin(9600);
  
  // Set buzzer pin as OUTPUT
  pinMode(BUZZER_PIN, OUTPUT);
  
  // Start with buzzer OFF
  digitalWrite(BUZZER_PIN, LOW);
  
  Serial.println("Arduino Buzzer Control Ready");
}

void loop() {
  // Check if data is available from Python
  if (Serial.available() > 0) {
    // Read incoming byte
    char command = Serial.read();
    
    // IF-ELSE condition to control buzzer
    if (command == '1') {
      // Turn ON the buzzer
      digitalWrite(BUZZER_PIN, HIGH);
      Serial.println("Buzzer: ON");
    }
    else if (command == '0') {
      // Turn OFF the buzzer
      digitalWrite(BUZZER_PIN, LOW);
      Serial.println("Buzzer: OFF");
    }
    else {
      Serial.println("Unknown command");
    }
  }
}
