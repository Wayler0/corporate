// Bus fare terminal - Stage 2: show the tapped card on the 16x2 LCD
// Board: Arduino Uno   Reader: RC522   LCD: 16x2 without I2C (4-bit mode)
// Libraries: "MFRC522" by GithubCommunity, LiquidCrystal (built in)
//
// RC522 -> Uno:  SDA->10  SCK->13  MOSI->11  MISO->12  RST->9  3.3V->3.3V  GND->GND
//
// LCD pin -> Uno:
//   GND -> GND          VCC -> 5V          VO -> 1k resistor -> GND (contrast)
//   RS  -> 7            RW  -> GND         E  -> 6
//   D0-D3 -> not connected
//   D4 -> 5   D5 -> 4   D6 -> 3   D7 -> 2
//   BLA -> 220 ohm resistor -> 5V          BLK -> GND
//
// No reader? Serial Monitor (9600 baud, "Newline"): type a card ID, press Enter.

#include <SPI.h>
#include <MFRC522.h>
#include <LiquidCrystal.h>

const byte SS_PIN = 10;
const byte RST_PIN = 9;

MFRC522 rfid(SS_PIN, RST_PIN);
LiquidCrystal lcd(7, 6, 5, 4, 3, 2);  // RS, E, D4, D5, D6, D7

const unsigned long MESSAGE_MS = 3000;  // how long a tap stays on screen
unsigned long messageShownAt = 0;
bool showingMessage = false;

void showIdle() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(F("Bus Fare System"));
  lcd.setCursor(0, 1);
  lcd.print(F("Tap your card..."));
  showingMessage = false;
}

void handleTap(const String &uid, bool simulated) {
  if (simulated) Serial.print(F("[SIM] "));
  Serial.print(F("Card UID: "));
  Serial.println(uid);

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(simulated ? F("Card (sim):") : F("Card read:"));
  lcd.setCursor(0, 1);
  lcd.print(uid.substring(0, 16));  // 4-byte UID "A1 B2 C3 D4" fits in 11 chars

  messageShownAt = millis();
  showingMessage = true;
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
  lcd.begin(16, 2);
  SPI.begin();
  rfid.PCD_Init();
  delay(50);

  Serial.println(F("Bus fare terminal - Stage 2: LCD"));
  byte version = rfid.PCD_ReadRegister(MFRC522::VersionReg);
  bool readerOk = !(version == 0x00 || version == 0xFF);

  lcd.setCursor(0, 0);
  lcd.print(F("Starting..."));
  lcd.setCursor(0, 1);
  lcd.print(readerOk ? F("Reader OK") : F("No reader: SIM"));
  Serial.println(readerOk ? F("RC522 found.") : F("RC522 NOT detected. Simulation mode."));
  delay(2000);
  showIdle();
}

void loop() {
  // Return to the idle screen after a tap message
  if (showingMessage && millis() - messageShownAt > MESSAGE_MS) showIdle();

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
  delay(1000);
}
