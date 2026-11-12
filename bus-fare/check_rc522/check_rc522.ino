// RC522 connection check: LED shows reader status twice a second.
// GREEN = reader answers, RED = no answer. Serial prints the version byte.
// LED module plugged into A0 (R), A1 (G), A2 (B), A3 (GND).
#include <SPI.h>
#include <MFRC522.h>

MFRC522 rfid(10, 9);  // SDA, RST

void led(bool r, bool g) {
  digitalWrite(A0, r);
  digitalWrite(A1, g);
  digitalWrite(A2, LOW);
}

void setup() {
  Serial.begin(9600);
  pinMode(A0, OUTPUT); pinMode(A1, OUTPUT); pinMode(A2, OUTPUT);
  pinMode(A3, OUTPUT); digitalWrite(A3, LOW);
  SPI.begin();
  rfid.PCD_Init();
  Serial.println(F("RC522 check: GREEN = connected, RED = not connected"));
}

bool wasOk = false;
unsigned long lastStatus = 0;

void loop() {
  // Status check twice a second
  if (millis() - lastStatus > 500) {
    lastStatus = millis();
    byte v = rfid.PCD_ReadRegister(MFRC522::VersionReg);
    bool ok = !(v == 0x00 || v == 0xFF);
    if (ok && !wasOk) rfid.PCD_Init();  // re-init only after a reconnect
    wasOk = ok;
    led(!ok, ok);
    Serial.print(ok ? F("OK  version 0x") : F("--  no reader  0x"));
    Serial.println(v, HEX);
  }

  // Look for a card about 20 times a second
  if (wasOk && rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    Serial.print(F("CARD UID: "));
    for (byte i = 0; i < rfid.uid.size; i++) {
      if (rfid.uid.uidByte[i] < 0x10) Serial.print('0');
      Serial.print(rfid.uid.uidByte[i], HEX);
    }
    Serial.println();
    led(false, false); delay(300);  // blink off = card seen
    led(false, true);
    rfid.PICC_HaltA();
  }
  delay(50);
}
