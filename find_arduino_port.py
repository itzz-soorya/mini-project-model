"""
Arduino COM Port Detector
Finds and lists all available serial COM ports
"""

import serial.tools.list_ports
import time

print("=" * 60)
print("SCANNING FOR ARDUINO NANO...")
print("=" * 60)

ports = serial.tools.list_ports.comports()

if not ports:
    print("❌ No COM ports found!")
    print("\nTroubleshooting:")
    print("1. Check if Arduino is connected via USB")
    print("2. Install CH340 drivers (Arduino Nano uses CH340 chip)")
    print("3. Try: https://github.com/WCHSoftware/ch341ser")
else:
    print(f"\n✓ Found {len(ports)} COM port(s):\n")
    
    arduino_found = False
    for i, port in enumerate(ports, 1):
        print(f"{i}. Port: {port.device}")
        print(f"   Description: {port.description}")
        print(f"   Hardware ID: {port.hwid}")
        
        # Check if it's likely an Arduino
        if 'Arduino' in port.description or 'CH340' in port.description or 'CH341' in port.description:
            print(f"   ✓ This looks like ARDUINO NANO!")
            arduino_found = True
        print()
    
    if arduino_found:
        print("✅ Arduino detected! Update ARDUINO_PORT in detect_danger_zone.py")
    else:
        print("⚠️  Arduino Nano not detected")
        print("   Check: Device Manager → Ports (COM & LPT)")

print("=" * 60)
