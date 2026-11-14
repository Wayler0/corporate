// ESP32 Wi-Fi check: joins the network in secrets.h and tests the internet.
// Serial Monitor 115200. LCD (G21/G22) and RGB LED (G25/26/27) show the result too.
#include <WiFi.h>
#include <HTTPClient.h>
#include "secrets.h"

const int LED_R = 25, LED_G = 26, LED_B = 27;

void setRGB(bool r, bool g, bool b) { digitalWrite(LED_R, r); digitalWrite(LED_G, g); digitalWrite(LED_B, b); }

void setup() {
  Serial.begin(115200);
  pinMode(LED_R, OUTPUT); pinMode(LED_G, OUTPUT); pinMode(LED_B, OUTPUT);
  delay(500);
  Serial.printf("\n=== ESP32 Wi-Fi check ===\nMAC: %s\nJoining \"%s\"...\n",
                WiFi.macAddress().c_str(), WIFI_SSID);
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    setRGB(0, 0, 1);  // blue = trying
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    unsigned long t = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - t < 15000) delay(250);
    if (WiFi.status() != WL_CONNECTED) {
      setRGB(1, 0, 0);
      Serial.printf("NOT CONNECTED (status %d). If the router filters MACs, allow %s\n",
                    WiFi.status(), WiFi.macAddress().c_str());
      WiFi.disconnect();
      delay(5000);
      return;
    }
    Serial.printf("CONNECTED. IP %s, gateway %s, signal %d dBm\n",
                  WiFi.localIP().toString().c_str(), WiFi.gatewayIP().toString().c_str(), WiFi.RSSI());
  }
  HTTPClient http;
  http.setTimeout(5000);
  http.begin("http://connectivitycheck.gstatic.com/generate_204");
  int code = http.GET();
  http.end();
  if (code == 204) { setRGB(0, 1, 0); Serial.println("Internet: OK"); }
  else { setRGB(1, 1, 0); Serial.printf("Internet: no (HTTP %d). Local network still works.\n", code); }
  delay(10000);
}
