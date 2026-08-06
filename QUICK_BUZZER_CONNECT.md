# 🎯 SIMPLE BUZZER CONNECTION - Quick Reference

## IF You Have a 5V Relay Module (Recommended):

### Arduino Nano → Relay Module:
```
Nano 5V  ──(Red wire)──►  Relay VCC
Nano GND ──(Black wire)──► Relay GND  
Nano D9  ──(Yellow)──►     Relay IN+
```

### Relay Module → 15V Buzzer:
```
Relay COM ──► Buzzer Red Wire (+)
Relay NO  ──► Buzzer Black Wire (-) ──► 15V GND

15V Power Supply (+) ──► Relay COM
15V Power Supply (-) ──► Relay NO
```

---

## ELSE IF You Want to Use a Transistor (Advanced):

```
                    ┌─────────────────┐
                    │  2N2222         │
                    │  Transistor     │
                    │                 │
Nano D9 ──1kΩ──────►├─ B (Base)       │
                    │                 │
15V(+) ────────────►├─ C (Collector)  │
                    │                 │
Buzzer Red ─────────├─ E (Emitter) ──►├─ Buzzer Black ──► 15V GND
                    │                 │
                    └─────────────────┘
```

---

## ⚠️ DO NOT:
- ❌ Connect 15V directly to Arduino pins
- ❌ Connect Buzzer RED to 5V
- ❌ Mix up positive and negative
- ❌ Forget the relay/transistor

---

## ✅ DO:
- ✅ Use 5V relay module OR transistor
- ✅ Connect Arduino 5V & GND to relay
- ✅ Connect D9 signal to relay IN
- ✅ Use separate 15V power supply for buzzer
- ✅ Connect buzzer RED to relay COM
- ✅ Connect buzzer BLACK to relay NO

---

**Can't see relay clearly? Take photo of your relay module!**
