# Arduino Nano + 15V Buzzer Integration Guide

## 📋 Components Needed

1. **Arduino Nano V3.0** (ATmega328P)
2. **15V Active Buzzer**
3. **Relay Module** (5V relay with 1 channel) OR **NPN Transistor** (2N2222)
4. **Diode** (1N4007) - for reverse voltage protection
5. **15V Power Supply** 
6. **Jumper Wires**
7. **USB Cable** (Mini-USB for Arduino)

## 🔌 Circuit Connections

### Option 1: Using 5V Relay Module (RECOMMENDED)

```
Arduino Nano
    |
    +--- Pin 9 (Digital Output) -----> Relay IN+
    |                                   Relay IN-
    +--- GND ----> Relay GND

Relay Module
    |
    +--- COM ------> 15V Power+ 
    +--- NO -------> 15V Buzzer+ 
    |                15V Buzzer- -----> 15V Power-
    +--- GND ------> 15V Power- (GND)

15V Power Supply
    |
    +--- VCC (15V) ------> Relay COM
    +--- GND --------> Common Ground
```

### Option 2: Using NPN Transistor (2N2222)

```
Arduino Nano Pin 9 
    |
    +--- 1kΩ Resistor ---> Transistor Base (B)
    
Transistor (2N2222)
    |
    +--- Collector (C) ------> 15V Power+
    +--- Emitter (E) -------> 15V Buzzer+ 
    |                         15V Buzzer- -----> 15V Power-
    +--- Base (B) <--------- 1kΩ Resistor from Pin 9

Add 1N4007 Diode across buzzer (Anode to +, Cathode to -)
```

## 📝 Setup Instructions

### Step 1: Upload Arduino Code
1. Open Arduino IDE
2. Select: **Tools → Board → Arduino Nano**
3. Select: **Tools → Processor → ATmega328P**
4. Select: **Tools → Port → COM3** (adjust if different)
5. Copy code from `arduino_buzzer_control.ino`
6. Click **Upload**

### Step 2: Find Arduino COM Port
```powershell
# In PowerShell, list all COM ports
Get-Content -Path 'HKLM:\HARDWARE\DEVICEMAP\SERIALCOMM' | Select-Object -ExpandProperty '*'
# Or check Device Manager: Ports (COM & LPT)
```

### Step 3: Update Python Code
In `detect_danger_zone.py`, change:
```python
ARDUINO_PORT = "COM3"  # Change to your actual port
```

### Step 4: Install Python Serial Library
```bash
pip install pyserial
```

## ⚡ How It Works

### IF-ELSE Logic in Python:
```python
if ENABLE_ARDUINO_BUZZER and arduino:
    arduino.write(b'1')  # Send '1' → Buzzer ON
else:
    winsound.Beep()      # Fallback to system beep
```

### IF-ELSE Logic in Arduino:
```cpp
if (command == '1') {
    digitalWrite(BUZZER_PIN, HIGH);  // Turn ON
}
else if (command == '0') {
    digitalWrite(BUZZER_PIN, LOW);   // Turn OFF
}
```

## 🧪 Testing

### Test 1: Check Serial Connection
```python
import serial
import time

arduino = serial.Serial("COM3", 9600, timeout=1)
time.sleep(2)

# Turn buzzer ON
arduino.write(b'1')
time.sleep(2)

# Turn buzzer OFF
arduino.write(b'0')

arduino.close()
```

### Test 2: Run Detection System
```bash
python detect_danger_zone.py
```
- Draw danger zone with mouse
- Press ENTER to start
- Enter the danger zone
- Buzzer should trigger automatically

## 🔧 Troubleshooting

| Problem | Solution |
|---------|----------|
| Arduino not detected | Check COM port in Device Manager |
| Buzzer not working | Verify relay/transistor connections |
| Serial error | Install: `pip install pyserial` |
| Wrong port | Update `ARDUINO_PORT` value |
| Buzzer always ON | Check transistor polarity |

## ✅ Features

✓ Remote buzzer control via Arduino
✓ Real-time person detection triggers buzzer
✓ Automatic buzzer OFF when person leaves zone
✓ Fallback to system beep if Arduino fails
✓ Clean exit and resource cleanup
