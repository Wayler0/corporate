// SIM800 GSM module checker (works WITHOUT a SIM card).
// Tested board: blue "SIM800C GSM/GPRS BOARD", header 5V V_TTL GND TXD RXD DTR SPKP SPKN.
// 5V -> Uno 5V, V_TTL -> Uno 5V, GND -> GND, TXD -> pin 2, RXD -> pin 3, rest empty.
// The chip does NOT start by itself: after power-up, bridge PWX (top row, 3rd hole
// from the square VBAT hole) to the GND hole beside it for 2 s; the status LED then blinks.
// Tested 14 Nov 2026: AT OK, ATI "SIM800 R14.18", CSQ 8 with no antenna, CBC 3867 mV.
// Open the Serial Monitor at 9600, line ending "Both NL & CR".
// It asks the module a few questions at start, then you can type AT commands yourself.
// LED module (A0-A3): GREEN = module answers, RED = no answer.

#include <SoftwareSerial.h>

SoftwareSerial gsm(2, 3);  // RX (from module TXD), TX (to module RXD)
const byte LED_R = A0, LED_G = A1, LED_B = A2, LED_GND = A3;

String ask(const char *cmd, unsigned long waitMs) {
  while (gsm.available()) gsm.read();
  gsm.print(cmd);
  gsm.print("\r");
  String reply;
  unsigned long start = millis();
  while (millis() - start < waitMs) {
    while (gsm.available()) reply += (char)gsm.read();
  }
  reply.trim();
  return reply;
}

void show(const char *cmd, const __FlashStringHelper *meaning, unsigned long waitMs = 1500) {
  String r = ask(cmd, waitMs);
  Serial.print(F("> "));
  Serial.print(cmd);
  Serial.print(F("   ("));
  Serial.print(meaning);
  Serial.println(F(")"));
  Serial.println(r.length() ? r : String(F("  (no answer)")));
  Serial.println();
}

void setup() {
  pinMode(LED_R, OUTPUT); pinMode(LED_G, OUTPUT); pinMode(LED_B, OUTPUT);
  pinMode(LED_GND, OUTPUT); digitalWrite(LED_GND, LOW);
  Serial.begin(9600);
  gsm.begin(9600);
  Serial.println(F("SIM800L check. Waiting 5 s for the module to start..."));
  digitalWrite(LED_B, HIGH);
  delay(5000);
  digitalWrite(LED_B, LOW);

  // The module learns the speed from the first "AT"s it hears.
  bool ok = false;
  for (byte i = 0; i < 5 && !ok; i++) ok = ask("AT", 800).indexOf("OK") >= 0;
  if (!ok) {
    digitalWrite(LED_R, HIGH);
    Serial.println(F("NO ANSWER. Check: power (module LED lit?), GND shared with the Uno,"));
    Serial.println(F("TXD->2 and RXD->3 (try swapping them), and a 2 A supply."));
    return;
  }
  digitalWrite(LED_G, HIGH);
  Serial.println(F("Module answers AT: wiring and power OK.\n"));
  show("ATI", F("model and firmware"));
  show("AT+CPIN?", F("SIM status: an error or NOT INSERTED is expected without a SIM"));
  show("AT+CSQ", F("signal 0-31, 99 = unknown"));
  show("AT+CBC", F("supply voltage in mV, should be 3500-4300"));
  Serial.println(F("Now type your own AT commands."));
}

void loop() {
  if (Serial.available()) gsm.write(Serial.read());
  if (gsm.available()) Serial.write(gsm.read());
}
