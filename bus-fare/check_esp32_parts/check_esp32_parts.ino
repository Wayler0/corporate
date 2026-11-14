// ESP32 parts check: tests each part of the fare terminal on its own.
// Board: "ESP32 Dev Module". Serial Monitor 115200.
//
// Wiring (ESP32 pin labels):
//   RC522   SDA G5, SCK G18, MOSI G23, MISO G19, RST G4, 3.3V -> 3V3 (NOT V5), GND
//   LCD     SDA G21, SCL G22, VCC -> V5, GND
//   RGB LED R G25, G G26, B G27, GND
//   Piezo   + G13 (220 ohm optional), - GND
//
// It repeats every 5 s, so wires can be fixed while it runs.

#include <SPI.h>
#include <Wire.h>
#include <WiFi.h>
#include <MFRC522.h>

const int RC_SS = 5, RC_RST = 4;
const int LCD_SDA = 21, LCD_SCL = 22;
const int LED_R = 25, LED_G = 26, LED_B = 27;
const int PIEZO = 13;
const int ONBOARD_LED = 2;

MFRC522 rfid(RC_SS, RC_RST);
byte lcdAddr = 0;

// ---- tiny PCF8574 LCD driver (P0=RS P2=E P3=backlight P4-P7=D4-D7) ----
void lcdOut(byte d) { Wire.beginTransmission(lcdAddr); Wire.write(d | 0x08); Wire.endTransmission(); }
void lcdNibble(byte d) { lcdOut(d | 0x04); delayMicroseconds(1); lcdOut(d); delayMicroseconds(50); }
void lcdSend(byte v, byte rs) { lcdNibble((v & 0xF0) | rs); lcdNibble(((v << 4) & 0xF0) | rs); }
void lcdInit() {
  delay(50); lcdOut(0);
  lcdNibble(0x30); delay(5); lcdNibble(0x30); delay(1); lcdNibble(0x30); lcdNibble(0x20);
  lcdSend(0x28, 0); lcdSend(0x0C, 0); lcdSend(0x01, 0); delay(2); lcdSend(0x06, 0);
}
void lcdPrint(byte row, const char *s) {
  lcdSend(row ? 0xC0 : 0x80, 0);
  for (byte i = 0; i < 16; i++) lcdSend(*s ? *s++ : ' ', 1);
}

void setRGB(bool r, bool g, bool b) {
  digitalWrite(LED_R, r); digitalWrite(LED_G, g); digitalWrite(LED_B, b);
}

void beep(int freq, int ms) {
  ledcWriteTone(0, freq); delay(ms); ledcWriteTone(0, 0);
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_R, OUTPUT); pinMode(LED_G, OUTPUT); pinMode(LED_B, OUTPUT);
  pinMode(ONBOARD_LED, OUTPUT);
  ledcSetup(0, 3000, 8);
  ledcAttachPin(PIEZO, 0);
  SPI.begin(18, 19, 23, RC_SS);
  Wire.begin(LCD_SDA, LCD_SCL);
  WiFi.mode(WIFI_STA);
  delay(500);
  Serial.println(F("\n=== ESP32 parts check ==="));
}

void loop() {
  digitalWrite(ONBOARD_LED, !digitalRead(ONBOARD_LED));
  Serial.println(F("\n----------------------------------------"));

  // 1. RGB LED: red, green, blue
  Serial.println(F("RGB LED: showing red, green, blue now (check by eye)"));
  setRGB(1, 0, 0); delay(300); setRGB(0, 1, 0); delay(300); setRGB(0, 0, 1); delay(300); setRGB(0, 0, 0);

  // 2. Piezo
  Serial.println(F("Piezo: one beep now (check by ear)"));
  beep(3000, 200);

  // 3. LCD
  lcdAddr = 0;
  for (byte a = 0x20; a < 0x40 && !lcdAddr; a++) {
    if (a == 0x28) a = 0x38;
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) lcdAddr = a;
  }
  if (lcdAddr) {
    Serial.printf("LCD: OK at address 0x%02X (screen should say ESP32 OK)\n", lcdAddr);
    lcdInit();
    lcdPrint(0, "ESP32 OK");
    lcdPrint(1, "Tap a card...");
  } else {
    Serial.println(F("LCD: NOT FOUND - check SDA->G21, SCL->G22, VCC->V5, GND"));
  }

  // 4. RC522
  rfid.PCD_Init();
  byte v = rfid.PCD_ReadRegister(MFRC522::VersionReg);
  if (v == 0x00 || v == 0xFF) {
    Serial.println(F("RC522: NOT FOUND - check SDA->G5 SCK->G18 MOSI->G23 MISO->G19 RST->G4, 3.3V->3V3"));
  } else {
    Serial.printf("RC522: OK, version 0x%02X. Hold a card on it now...\n", v);
    unsigned long t = millis();
    bool got = false;
    while (millis() - t < 2500 && !got) {
      if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
        Serial.print(F("  Card: "));
        char buf[3];
        for (byte i = 0; i < rfid.uid.size; i++) { sprintf(buf, "%02X", rfid.uid.uidByte[i]); Serial.print(buf); }
        Serial.println();
        rfid.PICC_HaltA();
        setRGB(0, 1, 0); beep(3000, 150); delay(300); setRGB(0, 0, 0);
        if (lcdAddr) lcdPrint(1, "Card read!");
        got = true;
      }
      delay(50);
    }
    if (!got) Serial.println(F("  (no card this round)"));
  }

  // 5. Wi-Fi scan
  int n = WiFi.scanNetworks();
  Serial.printf("Wi-Fi: %d networks seen\n", n);
  for (int i = 0; i < n && i < 8; i++)
    Serial.printf("  %-24s signal %d dBm\n", WiFi.SSID(i).c_str(), WiFi.RSSI(i));
  WiFi.scanDelete();

  delay(5000);
}
