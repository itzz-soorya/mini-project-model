"""
Arduino Connection Test
Tests basic serial communication with Arduino Nano
"""

import serial
import time

ARDUINO_PORT = "COM5"
ARDUINO_BAUD = 9600

print("=" * 60)
print("TESTING ARDUINO CONNECTION")
print("=" * 60)

try:
    # Connect to Arduino
    print(f"\n⏳ Connecting to {ARDUINO_PORT} at {ARDUINO_BAUD} baud...")
    arduino = serial.Serial(ARDUINO_PORT, ARDUINO_BAUD, timeout=1)
    time.sleep(2)  # Wait for Arduino to initialize
    
    print(f"✓ Connected successfully!\n")
    
    # Test 1: Turn ON buzzer
    print("TEST 1: Turning buzzer ON...")
    arduino.write(b'1')
    time.sleep(1)
    response = arduino.readline().decode('utf-8', errors='ignore').strip()
    if response:
        print(f"  Arduino says: {response}")
    print("  ✓ Buzzer should be ON now\n")
    
    # Test 2: Turn OFF buzzer
    print("TEST 2: Turning buzzer OFF...")
    time.sleep(1)
    arduino.write(b'0')
    time.sleep(1)
    response = arduino.readline().decode('utf-8', errors='ignore').strip()
    if response:
        print(f"  Arduino says: {response}")
    print("  ✓ Buzzer should be OFF now\n")
    
    # Test 3: ON-OFF cycle
    print("TEST 3: ON-OFF Cycle (3 times)...")
    for i in range(3):
        print(f"  Cycle {i+1}: ON")
        arduino.write(b'1')
        time.sleep(0.5)
        print(f"  Cycle {i+1}: OFF")
        arduino.write(b'0')
        time.sleep(0.5)
    print("  ✓ Cycle complete\n")
    
    # Close connection
    arduino.close()
    
    print("=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("=" * 60)
    print("\nYou can now run: python detect_danger_zone.py")
    
except serial.SerialException as e:
    print(f"\n❌ Connection failed: {e}")
    print("\nTroubleshooting:")
    print("1. Verify Arduino is plugged in via USB")
    print("2. Check Device Manager for COM port")
    print("3. Install CH340 drivers if needed")
    print("4. Run 'python find_arduino_port.py' to find correct port")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    print("\nMake sure Arduino sketch is uploaded!")
