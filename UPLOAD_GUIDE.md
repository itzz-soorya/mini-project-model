# 📝 Quick Upload Guide - Arduino Nano Buzzer Code

## ✅ Before You Start
- Arduino Nano connected to PC via USB ✓
- Arduino IDE installed ([Download here](https://www.arduino.cc/en/software))

## 🔧 Step 1: Open Arduino IDE

## 🔧 Step 2: Select Board & Port
1. Click **Tools → Board → Arduino Nano**
2. Click **Tools → Processor → ATmega328P**
3. Click **Tools → Port → COM5** (or your port)

## 🔧 Step 3: Upload Code
1. Create a new sketch
2. Copy ALL code from: `arduino_buzzer_control.ino` 
3. Replace the default code in Arduino IDE
4. Click **Upload** (or Ctrl+U)

Expected output:
```
Compiling sketch...
Uploading...
Done uploading.
```

## ✅ Verify Upload Success
- LED on Arduino should flash during upload
- No error messages in the console

## 🧪 Next: Test Connection
```bash
python test_arduino_connection.py
```

If successful:
```
✓ Connected successfully!

TEST 1: Turning buzzer ON...
  Arduino says: Buzzer: ON
  ✓ Buzzer should be ON now

TEST 2: Turning buzzer OFF...
  Arduino says: Buzzer: OFF
  ✓ Buzzer should be OFF now

✅ ALL TESTS PASSED!
```

## 🚀 Run Detection System
```bash
python detect_danger_zone.py
```

---

**Issues?** 
- If upload fails: Check Device Manager for COM port
- If no response: Verify sketch uploaded correctly
- Need help? See ARDUINO_SETUP.md for troubleshooting
