// Bus fare terminal - Stage 1: read an RFID card's ID
// Board: Arduino Uno   Reader: RC522   Library: "MFRC522" by GithubCommunity
//
// Wiring (RC522 -> Uno):  SDA->10  SCK->13  MOSI->11  MISO->12  RST->9
//                         3.3V->3.3V (NEVER 5V)  GND->GND  IRQ->not connected
//
// No reader yet? Open Serial Monitor (9600 baud, "Newline"), type a card ID
// such as  A1 B2 C3 D4  and press Enter. It is treated as a tap.

#include <SPI.h>
#include <MFRC522.h>

const byte SS_PIN = 10;
const byte RST_PIN = 9;

MFRC522 rfid(SS_PIN, RST_PIN);

void handleTap(const String &uid, bool simulated) {
  if (simulated) Serial.print(F("[SIM] "));
  Serial.print(F("Card UID: "));
  Serial.println(uid);
}

String readUid() {
  String uid;
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) uid += '0';
    uid += String(rfid.uid.uidByte[i], HEX);
    if (i < rfid.uid.size - 1) uid += ' ';
  }
  uid.toUpperCase();
  return uid;
}

void setup() {
  Serial.begin(9600);
  SPI.begin();
  rfid.PCD_Init();
  delay(50);

  Serial.println(F("Bus fare terminal - Stage 1: read card"));
  byte version = rfid.PCD_ReadRegister(MFRC522::VersionReg);
  if (version == 0x00 || version == 0xFF) {
    Serial.println(F("RC522 NOT detected: check wiring and the header pins."));
    Serial.println(F("Simulation still works: type a card ID and press Enter."));
  } else {
    Serial.print(F("RC522 found, firmware 0x"));
    Serial.println(version, HEX);
  }
  Serial.println(F("Tap a card..."));
}

void loop() {
  // Simulated tap from the Serial Monitor
  if (Serial.available()) {
    String uid = Serial.readStringUntil('\n');
    uid.trim();
    uid.toUpperCase();
    if (uid.length() > 0) handleTap(uid, true);
  }

  // Real tap from the RC522
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) return;
  handleTap(readUid(), false);
  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
  delay(1000);  // ignore the same card for a second
}
