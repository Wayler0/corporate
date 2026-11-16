// Bus fare terminal - WIRELESS firmware for the ESP32
//
// Same terminal as terminal_mvp (Uno), but the link to the server is Wi-Fi
// instead of a USB cable and a laptop bridge:
//   * Every tap is sent to PK's server:  POST /api/tap/  {"card_uid": "E5734107"}
//     and the server's answer is shown (LCD + LED + beep).
//   * Every 2 s it asks the server for messages:  POST /api/terminal/poll/
//     (top-ups "MSG ...", fare changes "FARE 70", new trips "trip").
//   * At start-up it asks  GET /api/status/  for the current route and fare.
//   * No Wi-Fi, or no answer within 2 s: it decides by itself from the balances
//     kept in its own flash memory (offline mode), exactly like the Uno.
//   * A '*' in the top right corner of the LCD means "connected to the server".
//   * Every request carries  Authorization: Terminal <TERMINAL_TOKEN>  so the
//     server knows which vehicle is calling (demo token: demo-terminal-bus-1).
//
// Wi-Fi name, password, server address and vehicle token go in secrets.h
// (copy secrets.example.h to secrets.h). secrets.h is never committed to git.
//
// Board: "ESP32 Dev Module". Libraries: MFRC522 (GithubCommunity). The rest is
// built into the ESP32 core (WiFi, HTTPClient, Preferences, Wire, SPI).
//
// Wiring (ESP32 pin labels):
//   RC522   SDA G5, SCK G18, MOSI G23, MISO G19, RST G4, 3.3V -> 3V3 (NOT V5), GND
//   LCD     SDA G21, SCL G22, VCC -> V5, GND   (I2C backpack, address found automatically)
//   RGB LED R G25, G G26, B G27, GND
//   Piezo   + G13, - GND
//
// Serial Monitor: 115200 baud, line ending "Newline". Type "help" for commands.
// LED: GREEN = paid  RED = refused  YELLOW = already paid this trip  BLUE = asking the server
// Sounds: each result has its own tune - edit them under "Sounds" below.

#include <SPI.h>
#include <Wire.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <MFRC522.h>
#include "secrets.h"

// ---------- Pins ----------
const int RC_SS = 5, RC_RST = 4, RC_SCK = 18, RC_MISO = 19, RC_MOSI = 23;
const int LCD_SDA = 21, LCD_SCL = 22;
const int LED_R = 25, LED_G = 26, LED_B = 27;
const int PIEZO = 13;
const int PIEZO_CH = 0;  // ledc channel for the piezo

// ---------- Sounds: EDIT HERE to customise the payment sounds ----------
// Each sound is a list of {frequency in Hz, length in ms}. Frequency 0 = silence.
// Piezos are loudest around 2000-4000 Hz, so keep tunes in octaves 6-7.
// Try a sound without tapping a card: type "sound paid" (or "sound all") in
// the Serial Monitor. Set SOUND_ON to false to silence the terminal.
const bool SOUND_ON = true;
const uint16_t NOTE_GAP_MS = 15;  // short silence after every note so repeats are heard apart

const uint16_t REST = 0;
const uint16_t C6 = 1047, D6 = 1175, E6 = 1319, F6 = 1397, G6 = 1568, A6 = 1760, B6 = 1976;
const uint16_t C7 = 2093, D7 = 2349, E7 = 2637, F7 = 2794, G7 = 3136, A7 = 3520;
const uint16_t C8 = 4186;

struct Note {
  uint16_t freq;
  uint16_t ms;
};

// Payment went through: bright rising chime
const Note SOUND_PAID[]    = {{C7, 80}, {E7, 80}, {G7, 160}};
// Card already paid on this trip: two neutral beeps
const Note SOUND_REPEAT[]  = {{A6, 90}, {REST, 60}, {A6, 90}};
// Payment failed - not enough balance: falling "uh-oh" then a long low tone
const Note SOUND_LOW[]     = {{E7, 120}, {C7, 120}, {REST, 60}, {G6, 400}};
// Payment failed - card not registered / deactivated: harsh triple buzz
const Note SOUND_UNKNOWN[] = {{D6, 100}, {REST, 50}, {D6, 100}, {REST, 50}, {D6, 300}};
// Top-up arrived from the server
const Note SOUND_TOPUP[]   = {{G6, 70}, {C7, 70}, {E7, 70}, {G7, 70}, {C8, 150}};
// Terminal switched on and ready
const Note SOUND_STARTUP[] = {{C7, 60}, {G7, 120}};

struct Sound {
  const char *name;  // used by the "sound <name>" command
  const Note *notes;
  uint8_t count;
};
#define SOUND(name, notes) {name, notes, sizeof(notes) / sizeof(notes[0])}
const Sound SOUNDS[] = {
  SOUND("paid", SOUND_PAID),
  SOUND("repeat", SOUND_REPEAT),
  SOUND("low", SOUND_LOW),
  SOUND("unknown", SOUND_UNKNOWN),
  SOUND("topup", SOUND_TOPUP),
  SOUND("startup", SOUND_STARTUP),
};
enum SoundId { SND_PAID, SND_REPEAT, SND_LOW, SND_UNKNOWN, SND_TOPUP, SND_STARTUP };
const uint8_t SOUND_COUNT = sizeof(SOUNDS) / sizeof(SOUNDS[0]);
static_assert(SOUND_COUNT == SND_STARTUP + 1, "SOUNDS and SoundId must list the same sounds in the same order");

// ---------- Routes (used offline; the server's fare wins when connected) ----------
struct Route {
  const char *name;
  uint16_t fare;
};
const Route ROUTES[] = {
  {"Campus shuttle", 50},
  {"Marimanti-Chuka", 100},
  {"Marimanti-Meru", 250},
};
const uint8_t ROUTE_COUNT = sizeof(ROUTES) / sizeof(ROUTES[0]);

// ---------- Passengers (used offline; same list as the server's seed_demo) ----------
struct Passenger {
  const char *uid;
  const char *name;
  uint16_t startBalance;
};
const Passenger PASSENGERS[] = {
  {"A1B2C3D4", "Test: Kim",       200},
  {"11223344", "Test: low funds",  30},
  {"E5734107", "White card",      500},
  {"008DEC53", "Blue fob",        500},
};
const uint8_t PASSENGER_COUNT = sizeof(PASSENGERS) / sizeof(PASSENGERS[0]);
static_assert(PASSENGER_COUNT <= 32, "trip-paid flags fit in 32 bits");

// ---------- Settings ----------
const uint16_t MAX_BALANCE = 50000;
const unsigned long LED_MS = 1500;
const unsigned long LCD_MESSAGE_MS = 3000;
const unsigned long TAP_TIMEOUT_MS = 2000;     // server must answer a tap within this
const unsigned long POLL_EVERY_MS = 2000;      // ask for messages this often when online
const unsigned long RETRY_EVERY_MS = 5000;     // try to reach the server this often when offline
const unsigned long ONLINE_TIMEOUT_MS = 8000;  // no good answer for this long = offline
const uint8_t LINE_LEN = 64;

// ---------- State ----------
MFRC522 rfid(RC_SS, RC_RST);
Preferences store;

uint8_t lcdAddr = 0;
bool lcdOk = false, readerOk = false;
bool lcdShowingMessage = false;
unsigned long lcdMessageAt = 0;

bool serverOnline = false;
unsigned long lastServerOkAt = 0, lastPollAt = 0;
uint16_t serverFare = 0;          // 0 = use the route's own fare
String serverRouteName;           // empty = use the route's own name
bool wifiWasUp = false;

uint16_t balances[PASSENGER_COUNT];
uint8_t currentRoute = 0;
uint32_t tripPaid = 0;            // bit i set = passenger i already paid this trip

char rxBuf[LINE_LEN];
uint8_t rxLen = 0;

// ---------- LCD (PCF8574 backpack: P0=RS P2=E P3=backlight P4-P7=D4-D7) ----------
bool lcdProbe(uint8_t a) {
  Wire.beginTransmission(a);
  return Wire.endTransmission() == 0;
}
void lcdOut(uint8_t d) {
  if (!lcdAddr) return;
  Wire.beginTransmission(lcdAddr);
  Wire.write(d | 0x08);
  Wire.endTransmission();
}
void lcdNibble(uint8_t d) { lcdOut(d | 0x04); delayMicroseconds(1); lcdOut(d); delayMicroseconds(50); }
void lcdSend(uint8_t v, uint8_t rs) { lcdNibble((v & 0xF0) | rs); lcdNibble(((v << 4) & 0xF0) | rs); }
void lcdInit() {
  if (!lcdAddr) return;
  delay(50); lcdOut(0);
  lcdNibble(0x30); delay(5); lcdNibble(0x30); delay(5); lcdNibble(0x30); delay(1); lcdNibble(0x20);
  lcdSend(0x28, 0); lcdSend(0x0C, 0); lcdSend(0x01, 0); delay(2); lcdSend(0x06, 0);
}
bool lcdFind() {
  lcdAddr = 0;
  for (uint8_t a = 0x20; a < 0x40 && !lcdAddr; a++) {
    if (a == 0x28) a = 0x38;  // PCF8574: 0x20-0x27, PCF8574A: 0x38-0x3F
    if (lcdProbe(a)) lcdAddr = a;
  }
  if (lcdAddr) lcdInit();
  return lcdAddr != 0;
}
void lcdLine(uint8_t row, const String &text) {
  if (!lcdAddr) return;
  lcdSend(row ? 0xC0 : 0x80, 0);
  for (uint8_t i = 0; i < 16; i++) lcdSend(i < text.length() ? text[i] : ' ', 1);
}
void lcdMessage(const String &l1, const String &l2) {
  lcdLine(0, l1);
  lcdLine(1, l2);
  lcdMessageAt = millis();
  lcdShowingMessage = true;
}

// ---------- LED and sound ----------
void setColor(bool r, bool g, bool b) {
  digitalWrite(LED_R, r); digitalWrite(LED_G, g); digitalWrite(LED_B, b);
}
void playSound(SoundId id) {
  if (!SOUND_ON) return;
  const Sound &s = SOUNDS[id];
  for (uint8_t i = 0; i < s.count; i++) {
    ledcWriteTone(PIEZO_CH, s.notes[i].freq);
    delay(s.notes[i].ms);
    ledcWriteTone(PIEZO_CH, 0);
    if (s.notes[i].freq) delay(NOTE_GAP_MS);
  }
}
// LED colour + sound together, LED stays on for at least LED_MS
void flash(bool r, bool g, bool b, SoundId sound) {
  setColor(r, g, b);
  unsigned long start = millis();
  playSound(sound);
  unsigned long used = millis() - start;
  if (used < LED_MS) delay(LED_MS - used);
  setColor(false, false, false);
}

// ---------- Storage (flash memory: survives power cuts) ----------
void saveBalances() { store.putBytes("bal", balances, sizeof(balances)); }
void saveRoute() { store.putUChar("route", currentRoute); }
void saveTripPaid() { store.putUInt("paid", tripPaid); }

void resetBalances() {
  for (uint8_t i = 0; i < PASSENGER_COUNT; i++) balances[i] = PASSENGERS[i].startBalance;
  currentRoute = 0;
  tripPaid = 0;
  saveBalances(); saveRoute(); saveTripPaid();
  store.putUChar("count", PASSENGER_COUNT);
}

void loadState() {
  if (store.getUChar("count", 0) != PASSENGER_COUNT ||
      store.getBytes("bal", balances, sizeof(balances)) != sizeof(balances)) {
    Serial.println("First run (or passenger list changed): loading start balances.");
    resetBalances();
    return;
  }
  currentRoute = store.getUChar("route", 0);
  tripPaid = store.getUInt("paid", 0);
  if (currentRoute >= ROUTE_COUNT) currentRoute = 0;
}

// ---------- Helpers ----------
bool hasPaid(uint8_t i) { return tripPaid & (1UL << i); }
void markPaid(uint8_t i) { tripPaid |= (1UL << i); saveTripPaid(); }

int findPassenger(const char *uid) {
  for (uint8_t i = 0; i < PASSENGER_COUNT; i++)
    if (strcmp(uid, PASSENGERS[i].uid) == 0) return i;
  return -1;
}

void normalizeUid(const char *in, char *out, size_t outSize) {
  size_t n = 0;
  for (; *in && n < outSize - 1; in++) {
    char c = toupper(*in);
    if ((c >= '0' && c <= '9') || (c >= 'A' && c <= 'F')) out[n++] = c;
  }
  out[n] = '\0';
}

uint16_t currentFare() { return serverFare ? serverFare : ROUTES[currentRoute].fare; }
String routeName() { return serverRouteName.length() ? serverRouteName : String(ROUTES[currentRoute].name); }

void lcdIdle() {
  lcdInit();  // self-heal if the display lost power for a moment
  String top = routeName().substring(0, 14);
  if (serverOnline) {
    while (top.length() < 15) top += ' ';
    top += '*';
  }
  lcdLine(0, top);
  lcdLine(1, readerOk ? String("KSh ") + currentFare() + "  Tap card" : String("Check reader!"));
  lcdShowingMessage = false;
}

void newTrip() {
  tripPaid = 0;
  saveTripPaid();
  Serial.println("New trip started: every card can pay once.");
  lcdMessage("New trip", routeName());
}

// ---------- Tiny JSON readers (enough for the server's flat answers) ----------
// {"result": "PAID", "fare": 50, "balance": 450}
String jsonString(const String &json, const char *key) {
  int k = json.indexOf(String("\"") + key + "\"");
  if (k < 0) return "";
  int q1 = json.indexOf('"', json.indexOf(':', k) + 1);
  int q2 = json.indexOf('"', q1 + 1);
  return (q1 < 0 || q2 < 0) ? "" : json.substring(q1 + 1, q2);
}
long jsonNumber(const String &json, const char *key, long fallback) {
  int k = json.indexOf(String("\"") + key + "\"");
  if (k < 0) return fallback;
  int c = json.indexOf(':', k) + 1;
  while (c < (int)json.length() && json[c] == ' ') c++;
  if (c >= (int)json.length() || !(isdigit(json[c]) || json[c] == '-')) return fallback;
  return json.substring(c).toInt();
}

// ---------- Talking to the server ----------
// Returns the HTTP status (or a negative error); the answer body goes in `body`.
int serverRequest(const char *method, const char *path, const String &payload, String &body,
                  unsigned long timeoutMs) {
  if (WiFi.status() != WL_CONNECTED) return -100;
  HTTPClient http;
  http.setConnectTimeout(timeoutMs);
  http.setTimeout(timeoutMs);
  if (!http.begin(String(SERVER_URL) + path)) return -101;
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", String("Terminal ") + TERMINAL_TOKEN);  // identifies this vehicle
  int code = strcmp(method, "GET") == 0 ? http.GET() : http.POST(payload);
  body = code > 0 ? http.getString() : "";
  http.end();
  if (code == 401 || code == 403) Serial.println("Server refused the terminal token: check TERMINAL_TOKEN in secrets.h");
  return code;
}

void markServer(bool ok) {
  if (ok) {
    lastServerOkAt = millis();
    if (!serverOnline) {
      serverOnline = true;
      Serial.println("Server: connected");
      lcdMessage("Server linked", "Online mode");
    }
  } else if (serverOnline && millis() - lastServerOkAt > ONLINE_TIMEOUT_MS) {
    serverOnline = false;
    serverFare = 0;
    serverRouteName = "";
    Serial.println("Server: lost, offline mode");
    lcdMessage("Server offline", "Offline mode");
  }
}

void fetchStatus() {
  String body;
  int code = serverRequest("GET", "/api/status/", "", body, 1500);
  if (code == 200) {
    long fare = jsonNumber(body, "fare", 0);
    if (fare > 0 && fare <= MAX_BALANCE) serverFare = fare;
    serverRouteName = jsonString(body, "route_name");
    Serial.printf("Server status: %s, KSh %u\n", routeName().c_str(), currentFare());
  }
}

void handleLine(char *line);  // below

// Ask the server for waiting messages: {"lines": ["MSG Top-up +100|Bal: KSh 600", "FARE 70"]}
void pollServer() {
  String body;
  int code = serverRequest("POST", "/api/terminal/poll/", "{}", body, serverOnline ? 1500 : 800);
  bool wasOnline = serverOnline;
  markServer(code == 200);
  if (code != 200) {
    if (wasOnline && !serverOnline && code != -100) Serial.printf("Server: no answer (%d)\n", code);
    return;
  }
  if (!wasOnline) fetchStatus();
  int pos = body.indexOf('[');
  while (pos >= 0) {
    int q1 = body.indexOf('"', pos + 1);
    if (q1 < 0) break;
    int q2 = body.indexOf('"', q1 + 1);
    if (q2 < 0) break;
    String one = body.substring(q1 + 1, q2);
    char buf[LINE_LEN];
    one.toCharArray(buf, sizeof(buf));
    Serial.printf("Server says: %s\n", buf);
    handleLine(buf);
    pos = q2;
  }
}

// Show what the server decided, and copy it into our own memory so that offline
// mode carries on from the same balances if the server goes away.
void showServerResult(const char *uid, const String &result, long fare, long balance) {
  int p = findPassenger(uid);
  if (p >= 0 && balance >= 0 && balance <= MAX_BALANCE && result != "UNKNOWN") {
    balances[p] = balance;
    saveBalances();
  }
  Serial.printf("Server: %s  fare %ld  balance %ld\n", result.c_str(), fare, balance);
  if (result == "PAID") {
    if (p >= 0) markPaid(p);
    lcdMessage(String("PAID KSh ") + fare, String("Bal: KSh ") + balance);
    flash(false, true, false, SND_PAID);
  } else if (result == "REPEAT") {
    if (p >= 0) markPaid(p);
    lcdMessage("Already paid", String("Bal: KSh ") + balance);
    flash(true, true, false, SND_REPEAT);
  } else if (result == "LOW") {
    lcdMessage("Low balance", String("Has ") + balance + " need " + fare);
    flash(true, false, false, SND_LOW);
  } else {
    lcdMessage("Unknown card", "See conductor");
    flash(true, false, false, SND_UNKNOWN);
  }
}

bool serverTap(const char *uid) {
  lcdLine(0, "Checking...");
  lcdLine(1, uid);
  setColor(false, false, true);  // blue = asking the server
  String body;
  int code = serverRequest("POST", "/api/tap/", String("{\"card_uid\": \"") + uid + "\"}", body, TAP_TIMEOUT_MS);
  setColor(false, false, false);
  String result = jsonString(body, "result");
  if (code != 200 || result.length() == 0) {
    Serial.printf("Server did not answer the tap (%d): deciding offline\n", code);
    lastServerOkAt = 0;
    markServer(false);
    return false;
  }
  markServer(true);
  showServerResult(uid, result, jsonNumber(body, "fare", currentFare()), jsonNumber(body, "balance", 0));
  return true;
}

// ---------- Offline decision (same rules as the server) ----------
void offlineTap(const char *uid) {
  uint16_t fare = currentFare();
  int p = findPassenger(uid);
  if (p < 0) {
    Serial.println("OFFLINE: unknown card");
    lcdMessage("Unknown card", "See conductor");
    flash(true, false, false, SND_UNKNOWN);
    return;
  }
  Serial.printf("OFFLINE: %s\n", PASSENGERS[p].name);
  if (hasPaid(p)) {
    Serial.println("  already paid this trip");
    lcdMessage("Already paid", String("Bal: KSh ") + balances[p]);
    flash(true, true, false, SND_REPEAT);
    return;
  }
  if (balances[p] < fare) {
    Serial.printf("  low balance: has %u, needs %u\n", balances[p], fare);
    lcdMessage("Low balance", String("Has ") + balances[p] + " need " + fare);
    flash(true, false, false, SND_LOW);
    return;
  }
  balances[p] -= fare;
  saveBalances();
  markPaid(p);
  Serial.printf("  PAID KSh %u, balance KSh %u\n", fare, balances[p]);
  lcdMessage(String("PAID KSh ") + fare, String("Bal: KSh ") + balances[p]);
  flash(false, true, false, SND_PAID);
}

void handleTap(const char *uid) {
  Serial.println("----------------------------------------");
  Serial.printf("Card: %s\n", uid);
  if (serverOnline && serverTap(uid)) return;
  offlineTap(uid);
}

// ---------- Commands (Serial Monitor) and server lines ----------
void listPassengers() {
  for (uint8_t i = 0; i < PASSENGER_COUNT; i++)
    Serial.printf("%s  %-16s KSh %u%s\n", PASSENGERS[i].uid, PASSENGERS[i].name, balances[i],
                  hasPaid(i) ? "  (paid this trip)" : "");
}

void printStatus() {
  Serial.printf("Wi-Fi: %s", WiFi.status() == WL_CONNECTED ? "connected" : "NOT connected");
  if (WiFi.status() == WL_CONNECTED) Serial.printf(" (%s, IP %s, %d dBm)", WIFI_SSID, WiFi.localIP().toString().c_str(), WiFi.RSSI());
  Serial.printf("\nServer: %s  %s\n", SERVER_URL, serverOnline ? "ONLINE" : "offline");
  Serial.printf("Route: %s  |  Fare: KSh %u\n", routeName().c_str(), currentFare());
}

// "sound paid" plays one sound, "sound all" plays every sound, "sound" lists them
void testSound(const char *arg) {
  while (*arg == ' ') arg++;
  for (uint8_t i = 0; i < SOUND_COUNT; i++) {
    if (*arg == '\0') { Serial.printf("  sound %s\n", SOUNDS[i].name); continue; }
    bool all = strcasecmp(arg, "all") == 0;
    if (all || strcasecmp(arg, SOUNDS[i].name) == 0) {
      Serial.printf("Playing: %s\n", SOUNDS[i].name);
      playSound((SoundId)i);
      if (!all) return;
      delay(600);
    }
  }
  if (*arg == '\0') Serial.println("  sound all");
  else if (strcasecmp(arg, "all") != 0) Serial.println("No such sound. Type: sound");
  if (!SOUND_ON) Serial.println("(SOUND_ON is false: the terminal is muted)");
}

void handleLine(char *line) {
  while (*line == ' ') line++;
  if (*line == '\0') return;

  if (strncmp(line, "MSG ", 4) == 0) {
    char *second = strchr(line + 4, '|');
    if (second) *second++ = '\0';
    lcdMessage(line + 4, second ? second : "");
    if (strncasecmp(line + 4, "Top-up", 6) == 0) playSound(SND_TOPUP);
  } else if (strncasecmp(line, "fare ", 5) == 0) {
    long f = atol(line + 5);
    if (f > 0 && f <= MAX_BALANCE) {
      serverFare = f;
      Serial.printf("Fare is now KSh %ld\n", f);
      if (!lcdShowingMessage) lcdIdle();
    }
  } else if (strcasecmp(line, "trip") == 0) {
    newTrip();
  } else if (strcasecmp(line, "help") == 0) {
    Serial.println("Commands:\n  <card id>     simulate a tap, e.g. E5734107\n  list          passengers and offline balances\n  status        Wi-Fi and server\n  route <n>     switch route offline (starts a new trip)\n  trip          new trip\n  sound [name]  play a payment sound (sound all = every one)\n  reset         restore start balances (offline copy)");
  } else if (strncasecmp(line, "sound", 5) == 0 && (line[5] == '\0' || line[5] == ' ')) {
    testSound(line + 5);
  } else if (strcasecmp(line, "list") == 0) {
    listPassengers();
  } else if (strcasecmp(line, "status") == 0) {
    printStatus();
  } else if (strncasecmp(line, "route ", 6) == 0) {
    int n = atoi(line + 6);
    if (n >= 1 && n <= ROUTE_COUNT) {
      currentRoute = n - 1;
      saveRoute();
      newTrip();
    } else {
      Serial.println("No such route.");
    }
  } else if (strcasecmp(line, "reset") == 0) {
    resetBalances();
    Serial.println("Balances reset.");
    lcdMessage("Balances reset", "New trip");
    listPassengers();
  } else {
    char uid[21];
    normalizeUid(line, uid, sizeof(uid));
    if (strlen(uid) >= 8) handleTap(uid);
    else Serial.println("Not a command or card ID. Type: help");
  }
}

bool readLine(char *out) {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      rxBuf[rxLen] = '\0';
      strcpy(out, rxBuf);
      rxLen = 0;
      return true;
    }
    if (rxLen < LINE_LEN - 1) rxBuf[rxLen++] = c;
  }
  return false;
}

// ---------- Hardware watch: parts plugged in late or pushed back start working ----------
unsigned long lastHwCheck = 0;
void checkHardware() {
  if (millis() - lastHwCheck < 2000) return;
  lastHwCheck = millis();

  bool lcdNow = lcdAddr ? lcdProbe(lcdAddr) : lcdFind();
  if (lcdNow && !lcdOk) { Serial.printf("LCD: connected at 0x%02X\n", lcdAddr); lcdOk = true; lcdIdle(); }
  else if (!lcdNow && lcdOk) { Serial.println("LCD: LOST - check the 4 wires"); lcdAddr = 0; }
  lcdOk = lcdNow;

  uint8_t v = rfid.PCD_ReadRegister(MFRC522::VersionReg);
  bool ok = !(v == 0x00 || v == 0xFF);
  if (ok && !readerOk) { rfid.PCD_Init(); Serial.println("RC522 reader: connected"); }
  else if (!ok && readerOk) Serial.println("RC522 reader: LOST - check the wires");
  bool changed = ok != readerOk;
  readerOk = ok;
  if (changed && !lcdShowingMessage) lcdIdle();

  bool wifiUp = WiFi.status() == WL_CONNECTED;
  if (wifiUp && !wifiWasUp) Serial.printf("Wi-Fi: connected, IP %s\n", WiFi.localIP().toString().c_str());
  if (!wifiUp && wifiWasUp) Serial.println("Wi-Fi: lost (reconnecting by itself)");
  wifiWasUp = wifiUp;
}

// ---------- Setup / loop ----------
void setup() {
  Serial.begin(115200);
  pinMode(LED_R, OUTPUT); pinMode(LED_G, OUTPUT); pinMode(LED_B, OUTPUT);
  setColor(false, false, false);
  ledcSetup(PIEZO_CH, 3000, 8);
  ledcAttachPin(PIEZO, PIEZO_CH);

  Wire.begin(LCD_SDA, LCD_SCL);
  Wire.setTimeOut(50);
  lcdOk = lcdFind();
  lcdLine(0, "Bus Fare System");
  lcdLine(1, "Starting...");

  SPI.begin(RC_SCK, RC_MISO, RC_MOSI, RC_SS);
  rfid.PCD_Init();
  delay(50);
  uint8_t v = rfid.PCD_ReadRegister(MFRC522::VersionReg);
  readerOk = !(v == 0x00 || v == 0xFF);

  store.begin("fare", false);
  loadState();

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  Serial.println("\n========================================");
  Serial.println(" Bus fare terminal - ESP32 wireless");
  Serial.println("========================================");
  Serial.printf("MAC %s\n", WiFi.macAddress().c_str());
  Serial.println(lcdOk ? "LCD: found" : "LCD: not detected (check SDA->G21 SCL->G22 VCC->V5 GND)");
  Serial.println(readerOk ? "RC522 reader: found" : "RC522 reader: not detected (check wiring, 3.3V on 3V3)");

  setColor(1, 0, 0); delay(300); setColor(0, 1, 0); delay(300); setColor(0, 0, 1); delay(300); setColor(0, 0, 0);
  lcdLine(1, "Joining Wi-Fi...");
  unsigned long t = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t < 8000) delay(200);
  wifiWasUp = WiFi.status() == WL_CONNECTED;
  if (wifiWasUp) Serial.printf("Wi-Fi: connected, IP %s\n", WiFi.localIP().toString().c_str());
  else Serial.println("Wi-Fi: not connected yet (keeps trying; offline mode meanwhile)");

  pollServer();
  printStatus();
  lcdIdle();
  playSound(SND_STARTUP);
  Serial.println("READY. Type 'help' for commands.");
}

void loop() {
  checkHardware();

  unsigned long every = serverOnline ? POLL_EVERY_MS : RETRY_EVERY_MS;
  if (millis() - lastPollAt >= every) {
    lastPollAt = millis();
    pollServer();
  }

  if (lcdShowingMessage && millis() - lcdMessageAt > LCD_MESSAGE_MS) lcdIdle();

  char line[LINE_LEN];
  if (readLine(line)) handleLine(line);

  if (readerOk && rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    char uid[21];
    uint8_t n = 0;
    for (uint8_t i = 0; i < rfid.uid.size && n < sizeof(uid) - 2; i++) {
      const char hex[] = "0123456789ABCDEF";
      uid[n++] = hex[rfid.uid.uidByte[i] >> 4];
      uid[n++] = hex[rfid.uid.uidByte[i] & 0x0F];
    }
    uid[n] = '\0';
    handleTap(uid);
    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
  }
}
