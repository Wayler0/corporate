// LCD connection checker (I2C backpack on A4 = SDA, A5 = SCL).
// Open the Serial Monitor at 9600 baud: it reports once a second which wires
// are working, and writes "LCD OK" on the screen as soon as it finds the LCD.
//
// Uses hand-made I2C so it can never freeze, whatever is (mis)connected.

byte SDA_PIN = A4, SCL_PIN = A5;  // swapped automatically if the two wires are crossed
void release(byte pin) { pinMode(pin, INPUT_PULLUP); delayMicroseconds(8); }
void pullLow(byte pin) { digitalWrite(pin, LOW); pinMode(pin, OUTPUT); delayMicroseconds(8); }
void i2cStart() { release(SDA_PIN); release(SCL_PIN); pullLow(SDA_PIN); pullLow(SCL_PIN); }
void i2cStop() { pullLow(SDA_PIN); release(SCL_PIN); release(SDA_PIN); }
bool i2cWrite(byte v) {
  for (byte i = 0; i < 8; i++, v <<= 1) {
    if (v & 0x80) release(SDA_PIN); else pullLow(SDA_PIN);
    release(SCL_PIN); pullLow(SCL_PIN);
  }
  release(SDA_PIN); release(SCL_PIN);
  bool ack = !digitalRead(SDA_PIN);
  pullLow(SCL_PIN);
  return ack;
}
bool probe(byte a) { i2cStart(); bool ok = i2cWrite(a << 1); i2cStop(); return ok; }

// Is something outside the Uno pulling this pin up to 5V? (The backpack does,
// through its own resistors, but only when it has power and the wire is good.)
bool pulledUpOutside(byte pin) {
  pullLow(pin);            // empty the pin
  delay(2);
  pinMode(pin, INPUT);     // let go, with the Uno's own pull-up OFF
  delay(5);
  return digitalRead(pin);
}

byte addr = 0;
void expander(byte d) { i2cStart(); i2cWrite(addr << 1); i2cWrite(d | 0x08); i2cStop(); }
void nibble(byte d) { expander(d | 0x04); expander(d); delayMicroseconds(50); }
void send(byte v, byte rs) { nibble((v & 0xF0) | rs); nibble(((v << 4) & 0xF0) | rs); }
void lcdInit() {
  delay(50); expander(0);
  nibble(0x30); delay(5); nibble(0x30); delay(5); nibble(0x30); delay(1); nibble(0x20);
  send(0x28, 0); send(0x0C, 0); send(0x01, 0); delay(2); send(0x06, 0);
}
void lcdPrint(byte row, const char *t) {
  send(0x80 | (row ? 0x40 : 0), 0);
  while (*t) send(*t++, 1);
}

void setup() { Serial.begin(9600); Serial.println(F("LCD checker")); }

void loop() {
  bool sdaUp = pulledUpOutside(SDA);
  bool sclUp = pulledUpOutside(SCL);
  release(SDA); release(SCL); delay(2);
  bool sdaHigh = digitalRead(SDA), sclHigh = digitalRead(SCL);

  Serial.print(F("SDA(A4): "));
  Serial.print(!sdaHigh ? F("STUCK LOW") : sdaUp ? F("connected") : F("nothing connected"));
  Serial.print(F("   SCL(A5): "));
  Serial.print(!sclHigh ? F("STUCK LOW") : sclUp ? F("connected") : F("nothing connected"));

  // Can the Uno pull each line down? If not, something is forcing it high
  // (usually the LCD's GND and VCC wires are swapped). Do not go further then.
  bool forcedHigh = false;
  if (sdaHigh && sclHigh) {
    for (byte i = 0; i < 2; i++) {
      byte pin = i ? SCL : SDA;
      pullLow(pin);
      delayMicroseconds(200);
      if (analogRead(pin) > 300) forcedHigh = true;
      pinMode(pin, INPUT);
    }
  }
  if (forcedHigh) {
    Serial.println(F("   FORCED HIGH: unplug! LCD GND and VCC are probably swapped"));
    addr = 0;
    delay(2000);
    return;
  }

  byte found = 0;
  if (sdaHigh && sclHigh) {
    for (byte attempt = 0; attempt < 2 && !found; attempt++) {
      for (byte a = 0x08; a < 0x78; a++) {
        if (probe(a)) {
          Serial.print(F("   device at 0x")); Serial.print(a, HEX);
          if (SDA_PIN == A5) Serial.print(F(" (SDA and SCL wires are CROSSED)"));
          if (!found) found = a;
        }
      }
      if (!found) { byte t = SDA_PIN; SDA_PIN = SCL_PIN; SCL_PIN = t; }  // try the other way round
    }
  }
  if (!found) Serial.print(F("   no device answers"));
  Serial.println();

  if (found && found != addr) {
    addr = found;
    lcdInit();
    lcdPrint(0, "LCD OK");
    lcdPrint(1, "Turn blue screw");
  }
  if (!found) addr = 0;
  delay(1000);
}
