// Bus fare terminal - WIRELESS firmware for the ESP32
//
// Same terminal as terminal_mvp (Uno), but the link to the server is Wi-Fi
// instead of a USB cable and a laptop bridge:
//   * Every tap is sent to PK's server:  POST /api/tap/  {"card_uid": "E5734107"}
//     and the server's answer is shown (LCD + LED + beep).
//   * Every 2 s it asks the server for messages:  POST /api/terminal/poll/
//     (top-ups "MSG ...", fare changes "FARE 70", new trips "trip").
//   * At start-up it asks  GET /api/status/  for the current route and fare.
//   * Offline mode: no Wi-Fi, or no answer within 2 s, and it decides by itself
//     from a copy of every card (GET /api/terminal/cards/: balance, blocked,
//     company pays, already paid this trip), kept in flash. Payments it takes
//     offline wait in a queue in flash (safe through power cuts) and are sent
//     with POST /api/terminal/sync/ as soon as the server answers again, before
//     anything else. Trips started offline ("trip", "route <n>") are sent too.
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
#include <LittleFS.h>
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
// Note names start with N_ because A6, A7 etc. are already ESP32 pin names.
const uint16_t N_C6 = 1047, N_D6 = 1175, N_E6 = 1319, N_F6 = 1397, N_G6 = 1568, N_A6 = 1760, N_B6 = 1976;
const uint16_t N_C7 = 2093, N_D7 = 2349, N_E7 = 2637, N_F7 = 2794, N_G7 = 3136, N_A7 = 3520;
const uint16_t N_C8 = 4186;

struct Note {
  uint16_t freq;
  uint16_t ms;
};

// Payment went through: bright rising chime
const Note SOUND_PAID[]    = {{N_C7, 80}, {N_E7, 80}, {N_G7, 160}};
// Card already paid on this trip: two neutral beeps
const Note SOUND_REPEAT[]  = {{N_A6, 90}, {REST, 60}, {N_A6, 90}};
// Payment failed - not enough balance: falling "uh-oh" then a long low tone
const Note SOUND_LOW[]     = {{N_E7, 120}, {N_C7, 120}, {REST, 60}, {N_G6, 400}};
// Payment failed - card not registered / deactivated: harsh triple buzz
const Note SOUND_UNKNOWN[] = {{N_D6, 100}, {REST, 50}, {N_D6, 100}, {REST, 50}, {N_D6, 300}};
// Top-up arrived from the server
const Note SOUND_TOPUP[]   = {{N_G6, 70}, {N_C7, 70}, {N_E7, 70}, {N_G7, 70}, {N_C8, 150}};
// Terminal switched on and ready
const Note SOUND_STARTUP[] = {{N_C7, 60}, {N_G7, 120}};

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

// ---------- Cards ----------
// The real list comes from the server (GET /api/terminal/cards/) and is kept in
// flash. These demo cards (same as the server's seed_demo) are only used until
// the terminal has reached the server once, or after "reset".
struct DemoCard {
  const char *uid;
  uint16_t balance;
  uint8_t flags;
};
const uint8_t F_PAID = 1, F_COMPANY = 2, F_OVER_LIMIT = 4, F_BLOCKED = 8;
const DemoCard DEMO_CARDS[] = {
  {"A1B2C3D4", 200, F_COMPANY},
  {"11223344",  30, 0},
  {"E5734107", 500, 0},
  {"008DEC53", 500, 0},
};
const uint8_t DEMO_COUNT = sizeof(DEMO_CARDS) / sizeof(DEMO_CARDS[0]);

const uint16_t MAX_CARDS = 1000;  // 24 bytes each in memory and in flash
struct Card {
  char uid[21];
  uint16_t balance;
  uint8_t flags;   // F_PAID (this trip), F_COMPANY (company pays), F_OVER_LIMIT, F_BLOCKED
};

// One payment taken offline, waiting to be sent to the server
struct QueuedTap {
  uint32_t ref;       // this terminal's own tap number, so a resend is never charged twice
  char uid[21];
  uint16_t fare;
  uint32_t trip;      // the server trip the terminal knew
  uint16_t offset;    // trips started offline since that one (0 = that trip)
  uint32_t boot;      // which power-on; "at" is millis() of that power-on
  uint32_t at;
};
const char *CARDS_FILE = "/cards.bin";
const char *QUEUE_FILE = "/queue.bin";
const uint8_t SYNC_BATCH = 50;    // taps per sync request (the server takes up to 100)

// ---------- Settings ----------
const uint16_t MAX_BALANCE = 50000;
const unsigned long LED_MS = 1500;
const unsigned long LCD_MESSAGE_MS = 3000;
const unsigned long TAP_TIMEOUT_MS = 2000;     // server must answer a tap within this
const unsigned long POLL_EVERY_MS = 2000;      // ask for messages this often when online
const unsigned long RETRY_EVERY_MS = 5000;     // try to reach the server this often when offline
const unsigned long ONLINE_TIMEOUT_MS = 8000;  // no good answer for this long = offline
const unsigned long CARDS_EVERY_MS = 30000;    // refresh the card list this often when online
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
uint16_t serverFare = 0;          // 0 = use the route's own fare (kept through offline spells)
String serverRouteName;           // empty = use the route's own name
bool wifiWasUp = false;
unsigned long lastCardsAt = 0;
bool cardsDue = true;             // refresh the card list at the next chance

Card cards[MAX_CARDS];
uint16_t cardCount = 0;
uint8_t currentRoute = 0;
uint32_t serverTrip = 0;          // the server's trip this terminal is on (0 = never heard)
uint16_t tripOffset = 0;          // trips started here since serverTrip, not yet told to the server
char terminalId[9];               // random, made on first power-on; part of every offline tap's ref
uint32_t nextRef = 1, bootNo = 0;

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
// Small values in Preferences; the card list and the offline queue in LittleFS files.
void saveTripState() {
  store.putUInt("strip", serverTrip);
  store.putUShort("toff", tripOffset);
  store.putUChar("route", currentRoute);
  store.putUShort("sfare", serverFare);
  store.putString("sroute", serverRouteName);
}

// cards.bin: card count (2 bytes), then MAX_CARDS fixed-size slots
void saveCards() {
  File f = LittleFS.open(CARDS_FILE, "w");
  if (!f) { Serial.println("Flash: cannot save the card list"); return; }
  f.write((uint8_t *)&cardCount, sizeof(cardCount));
  f.write((uint8_t *)cards, sizeof(Card) * cardCount);
  f.close();
}
// Rewrite just one card (a tap changes one balance; no need to rewrite them all)
void saveCard(uint16_t i) {
  File f = LittleFS.open(CARDS_FILE, "r+");
  if (!f) { saveCards(); return; }
  f.seek(sizeof(cardCount) + sizeof(Card) * i);
  f.write((uint8_t *)&cards[i], sizeof(Card));
  f.close();
}
bool loadCards() {
  File f = LittleFS.open(CARDS_FILE, "r");
  if (!f) return false;
  uint16_t n = 0;
  bool ok = f.read((uint8_t *)&n, sizeof(n)) == sizeof(n) && n <= MAX_CARDS &&
            f.read((uint8_t *)cards, sizeof(Card) * n) == sizeof(Card) * n;
  f.close();
  cardCount = ok ? n : 0;
  return ok;
}
void loadDemoCards() {
  cardCount = DEMO_COUNT;
  for (uint8_t i = 0; i < DEMO_COUNT; i++) {
    strncpy(cards[i].uid, DEMO_CARDS[i].uid, sizeof(cards[i].uid));
    cards[i].balance = DEMO_CARDS[i].balance;
    cards[i].flags = DEMO_CARDS[i].flags;
  }
  saveCards();
}

uint16_t queuedCount() {
  File f = LittleFS.open(QUEUE_FILE, "r");
  if (!f) return 0;
  uint16_t n = f.size() / sizeof(QueuedTap);
  f.close();
  return n;
}
bool enqueue(const char *uid, uint16_t fare) {
  QueuedTap q = {};
  q.ref = nextRef++;
  store.putUInt("ref", nextRef);
  strncpy(q.uid, uid, sizeof(q.uid) - 1);
  q.fare = fare;
  q.trip = serverTrip;
  q.offset = tripOffset;
  q.boot = bootNo;
  q.at = millis();
  File f = LittleFS.open(QUEUE_FILE, "a");
  if (!f) return false;
  bool ok = f.write((uint8_t *)&q, sizeof(q)) == sizeof(q);
  f.close();
  return ok;
}
// Drop the first n taps of the queue (they reached the server)
void dequeue(uint16_t n) {
  File in = LittleFS.open(QUEUE_FILE, "r");
  if (!in) return;
  in.seek(sizeof(QueuedTap) * n);
  File out = LittleFS.open("/queue.tmp", "w");
  QueuedTap q;
  while (in.read((uint8_t *)&q, sizeof(q)) == sizeof(q)) out.write((uint8_t *)&q, sizeof(q));
  in.close();
  out.close();
  LittleFS.remove(QUEUE_FILE);
  LittleFS.rename("/queue.tmp", QUEUE_FILE);
}

void loadState() {
  if (!LittleFS.begin(true)) Serial.println("Flash: LittleFS failed; offline cards will not survive a restart");
  // A random ID per terminal, so its tap numbers never clash with another terminal's
  // (or with its own after the flash is wiped)
  String id = store.getString("tid", "");
  if (id.length() != 8) {
    char buf[9];
    snprintf(buf, sizeof(buf), "%08X", (unsigned)esp_random());
    id = buf;
    store.putString("tid", id);
  }
  id.toCharArray(terminalId, sizeof(terminalId));
  nextRef = store.getUInt("ref", 1);
  bootNo = store.getUInt("boot", 0) + 1;
  store.putUInt("boot", bootNo);
  serverTrip = store.getUInt("strip", 0);
  tripOffset = store.getUShort("toff", 0);
  currentRoute = store.getUChar("route", 0);
  if (currentRoute >= ROUTE_COUNT) currentRoute = 0;
  serverFare = store.getUShort("sfare", 0);
  serverRouteName = store.getString("sroute", "");
  if (!loadCards()) {
    Serial.println("No card list yet: using the demo cards until the server is reached.");
    loadDemoCards();
  }
}

// ---------- Helpers ----------
int findCard(const char *uid) {
  for (uint16_t i = 0; i < cardCount; i++)
    if (strcmp(uid, cards[i].uid) == 0) return i;
  return -1;
}
bool hasPaid(uint16_t i) { return cards[i].flags & F_PAID; }

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

void clearPaid() {
  for (uint16_t i = 0; i < cardCount; i++) cards[i].flags &= ~F_PAID;
  saveCards();
}

bool syncQueue();   // below
bool fetchCards();

// A trip started here ("trip" or "route <n>" typed on the terminal). The server
// hears about it at the next sync.
void newTrip() {
  clearPaid();
  tripOffset++;
  saveTripState();
  Serial.println("New trip started: every card can pay once.");
  lcdMessage("New trip", routeName());
  if (serverOnline && syncQueue()) fetchCards();
}
// The server started a new trip (the crew did it on the dashboard)
void newTripFromServer() {
  clearPaid();
  tripOffset = 0;
  saveTripState();
  Serial.println("New trip started by the server: every card can pay once.");
  lcdMessage("New trip", routeName());
  cardsDue = true;   // learn the new trip's number
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
    serverOnline = false;   // the last fare and route from the server stay in use
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

// Send the payments taken offline (and trips started offline). True when nothing
// is left to send. Safe to repeat: the server skips taps it already has.
bool syncQueue() {
  uint16_t total = queuedCount();
  if (total == 0 && tripOffset == 0) return true;
  Serial.printf("Sync: sending %u offline payment(s), %u trip(s) started offline\n", total, tripOffset);
  bool first = true;
  while (first || queuedCount() > 0) {
    first = false;
    File f = LittleFS.open(QUEUE_FILE, "r");
    String json;
    json.reserve(140 * SYNC_BATCH + 120);
    json = String("{\"terminal\": \"") + terminalId + "\", \"trip\": " + serverTrip +
           ", \"trips_started\": " + tripOffset + ", \"taps\": [";
    uint16_t n = 0;
    QueuedTap q;
    while (f && n < SYNC_BATCH && f.read((uint8_t *)&q, sizeof(q)) == sizeof(q)) {
      if (n) json += ", ";
      json += String("{\"ref\": ") + q.ref + ", \"card_uid\": \"" + q.uid + "\", \"fare\": " + q.fare +
              ", \"trip\": " + q.trip + ", \"offset\": " + q.offset + ", \"seconds_ago\": ";
      json += q.boot == bootNo ? String((millis() - q.at) / 1000) : String("null");  // unknown after a restart
      json += "}";
      n++;
    }
    if (f) f.close();
    json += "]}";
    String body;
    int code = serverRequest("POST", "/api/terminal/sync/", json, body, 5000);
    if (code != 200) {
      Serial.printf("Sync: failed (%d), kept for later. %s\n", code, body.substring(0, 120).c_str());
      return false;
    }
    dequeue(n);
    long trip = jsonNumber(body, "trip", 0);
    if (queuedCount() == 0 && trip > 0) {
      serverTrip = trip;   // the server now knows about every trip started here
      tripOffset = 0;
      saveTripState();
    }
    Serial.printf("Sync: %u sent, %u left\n", n, queuedCount());
  }
  cardsDue = true;
  return true;
}

// Download every card (balance, blocked, company pays, paid this trip):
//   TRIP 12 FARE 50 Campus shuttle
//   E5734107 450 P
// Only when nothing is waiting to be sent: otherwise the server's balances would
// not yet include the offline payments.
bool fetchCards() {
  if (WiFi.status() != WL_CONNECTED || queuedCount() > 0 || tripOffset > 0) return false;
  HTTPClient http;
  http.setConnectTimeout(3000);
  http.setTimeout(3000);
  http.setReuse(false);   // one request, then the connection closes
  if (!http.begin(String(SERVER_URL) + "/api/terminal/cards/")) return false;
  http.addHeader("Authorization", String("Terminal ") + TERMINAL_TOKEN);
  int code = http.GET();
  int size = http.getSize();   // bytes in the answer (-1 = not given)
  if (code != 200) {
    http.end();
    return false;
  }
  WiFiClient *stream = http.getStreamPtr();
  String header = stream->readStringUntil('\n');
  long got = header.length() + 1;
  unsigned trip = 0, fare = 0;
  int nameAt = 0;
  if (sscanf(header.c_str(), "TRIP %u FARE %u %n", &trip, &fare, &nameAt) < 2 || trip == 0) {
    http.end();
    Serial.println("Cards: unexpected answer from the server");
    return false;
  }
  uint16_t n = 0;
  bool complete = false;
  unsigned long start = millis();
  while (millis() - start < 10000) {
    if (size >= 0 && got >= size) { complete = true; break; }
    String line = stream->readStringUntil('\n');
    got += line.length() + 1;
    if (line.length() == 0) {
      if (size < 0 && !stream->connected() && !stream->available()) { complete = true; break; }
      continue;
    }
    char uid[21] = "", flags[8] = "";
    unsigned bal = 0;
    if (sscanf(line.c_str(), "%20s %u %7s", uid, &bal, flags) != 3) continue;
    if (n >= MAX_CARDS) {
      Serial.printf("Cards: more than %u cards; the rest are not kept for offline mode\n", MAX_CARDS);
      complete = true;
      break;
    }
    strncpy(cards[n].uid, uid, sizeof(cards[n].uid));
    cards[n].balance = bal > MAX_BALANCE ? MAX_BALANCE : bal;
    cards[n].flags = (strchr(flags, 'P') ? F_PAID : 0) | (strchr(flags, 'C') ? F_COMPANY : 0) |
                     (strchr(flags, 'X') ? F_OVER_LIMIT : 0) | (strchr(flags, 'B') ? F_BLOCKED : 0);
    n++;
  }
  http.end();
  if (!complete) {
    Serial.println("Cards: download cut off; keeping the old list");
    loadCards();
    return false;
  }
  cardCount = n;
  saveCards();
  serverTrip = trip;
  tripOffset = 0;
  if (fare > 0 && fare <= MAX_BALANCE) serverFare = fare;
  serverRouteName = header.substring(nameAt);
  serverRouteName.trim();
  saveTripState();
  lastCardsAt = millis();
  cardsDue = false;
  Serial.printf("Cards: %u cards for offline mode, trip %u, %s KSh %u\n", n, trip, routeName().c_str(), currentFare());
  if (!lcdShowingMessage) lcdIdle();
  return true;
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
  if (!wasOnline) {
    // Back online: first send what was taken offline, then refresh the card list
    if (!(syncQueue() && fetchCards())) fetchStatus();
  }
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
    if (strcmp(buf, "trip") == 0) newTripFromServer();   // the crew started a trip on the dashboard
    else handleLine(buf);
    pos = q2;
  }
}

// Show what the server decided, and copy it into our own memory so that offline
// mode carries on from the same balances if the server goes away.
void showServerResult(const char *uid, const String &result, long fare, long balance) {
  int p = findCard(uid);
  if (result == "UNKNOWN" || result == "BLOCKED") {
    // No real balance comes with these (0). Make offline mode refuse the card too.
    if (p >= 0) {
      if (result == "BLOCKED") cards[p].flags |= F_BLOCKED;
      else cards[p] = cards[--cardCount];   // deactivated: forget the card
      if (result == "BLOCKED") saveCard(p); else saveCards();
    }
  } else if (balance >= 0 && balance <= MAX_BALANCE) {
    if (p < 0 && cardCount < MAX_CARDS) {   // a card registered since the last card list
      p = cardCount++;
      strncpy(cards[p].uid, uid, sizeof(cards[p].uid));
      cards[p].flags = 0;
      cardsDue = true;   // learn whether its company pays
    }
    if (p >= 0) {
      cards[p].balance = balance;
      cards[p].flags &= ~F_BLOCKED;
      if (result == "PAID" || result == "REPEAT") cards[p].flags |= F_PAID;
      saveCards();
    }
  }
  Serial.printf("Server: %s  fare %ld  balance %ld\n", result.c_str(), fare, balance);
  if (result == "PAID") {
    lcdMessage(String("PAID KSh ") + fare, String("Bal: KSh ") + balance);
    flash(false, true, false, SND_PAID);
  } else if (result == "REPEAT") {
    lcdMessage("Already paid", String("Bal: KSh ") + balance);
    flash(true, true, false, SND_REPEAT);
  } else if (result == "LOW") {
    lcdMessage("Low balance", String("Has ") + balance + " need " + fare);
    flash(true, false, false, SND_LOW);
  } else if (result == "BLOCKED") {
    // The owner reported this card lost or stolen
    lcdMessage("Card blocked", "Reported lost");
    flash(true, false, false, SND_UNKNOWN);
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
  int p = findCard(uid);
  if (p < 0) {
    Serial.println("OFFLINE: unknown card");
    lcdMessage("Unknown card", "See conductor");
    flash(true, false, false, SND_UNKNOWN);
    return;
  }
  Card &c = cards[p];
  if (c.flags & F_BLOCKED) {
    Serial.println("OFFLINE: card blocked (reported lost)");
    lcdMessage("Card blocked", "Reported lost");
    flash(true, false, false, SND_UNKNOWN);
    return;
  }
  if (hasPaid(p)) {
    Serial.println("OFFLINE: already paid this trip");
    lcdMessage("Already paid", String("Bal: KSh ") + c.balance);
    flash(true, true, false, SND_REPEAT);
    return;
  }
  bool company = c.flags & F_COMPANY;
  if (company && (c.flags & F_OVER_LIMIT)) {
    Serial.println("OFFLINE: company over its credit limit");
    lcdMessage("Declined", "Company limit");
    flash(true, false, false, SND_LOW);
    return;
  }
  if (!company && c.balance < fare) {
    Serial.printf("OFFLINE: low balance: has %u, needs %u\n", c.balance, fare);
    lcdMessage("Low balance", String("Has ") + c.balance + " need " + fare);
    flash(true, false, false, SND_LOW);
    return;
  }
  if (!enqueue(uid, fare)) {   // never let anyone ride on a payment we cannot keep
    Serial.println("OFFLINE: cannot save the payment to flash; refused");
    lcdMessage("Terminal error", "Pay the crew");
    flash(true, false, false, SND_UNKNOWN);
    return;
  }
  if (!company) c.balance -= fare;
  c.flags |= F_PAID;
  saveCard(p);
  Serial.printf("OFFLINE: PAID KSh %u%s, balance KSh %u (%u waiting to send)\n", fare,
                company ? " by the company" : "", c.balance, queuedCount());
  lcdMessage(String("PAID KSh ") + fare, company ? String("Company account") : String("Bal: KSh ") + c.balance);
  flash(false, true, false, SND_PAID);
}

void handleTap(const char *uid) {
  Serial.println("----------------------------------------");
  Serial.printf("Card: %s\n", uid);
  if (serverOnline && serverTap(uid)) return;
  offlineTap(uid);
}

// ---------- Commands (Serial Monitor) and server lines ----------
void listCards() {
  const uint16_t SHOWN = 40;
  for (uint16_t i = 0; i < cardCount && i < SHOWN; i++) {
    const Card &c = cards[i];
    Serial.printf("%-20s KSh %5u%s%s%s%s\n", c.uid, c.balance, (c.flags & F_PAID) ? "  paid this trip" : "",
                  (c.flags & F_COMPANY) ? "  company pays" : "", (c.flags & F_OVER_LIMIT) ? " (over limit)" : "",
                  (c.flags & F_BLOCKED) ? "  BLOCKED" : "");
  }
  if (cardCount > SHOWN) Serial.printf("... and %u more\n", cardCount - SHOWN);
  Serial.printf("%u cards, %u offline payment(s) waiting to be sent\n", cardCount, queuedCount());
}

void printStatus() {
  Serial.printf("Wi-Fi: %s", WiFi.status() == WL_CONNECTED ? "connected" : "NOT connected");
  if (WiFi.status() == WL_CONNECTED) Serial.printf(" (%s, IP %s, %d dBm)", WIFI_SSID, WiFi.localIP().toString().c_str(), WiFi.RSSI());
  Serial.printf("\nServer: %s  %s\n", SERVER_URL, serverOnline ? "ONLINE" : "offline");
  Serial.printf("Route: %s  |  Fare: KSh %u\n", routeName().c_str(), currentFare());
  Serial.printf("Trip: server %u + %u started here  |  Cards: %u  |  Waiting to send: %u  |  Terminal %s\n",
                serverTrip, tripOffset, cardCount, queuedCount(), terminalId);
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
    if (strncasecmp(line + 4, "Top-up", 6) == 0) {
      playSound(SND_TOPUP);
      cardsDue = true;   // pick up the new balance for offline mode
    }
  } else if (strncasecmp(line, "fare ", 5) == 0) {
    long f = atol(line + 5);
    if (f > 0 && f <= MAX_BALANCE) {
      serverFare = f;
      Serial.printf("Fare is now KSh %ld\n", f);
      if (!lcdShowingMessage) lcdIdle();
    }
  } else if (strcasecmp(line, "trip") == 0) {
    newTrip();
  } else if (strcasecmp(line, "sync") == 0) {
    if (syncQueue()) fetchCards();
    listCards();
  } else if (strcasecmp(line, "help") == 0) {
    Serial.println("Commands:\n  <card id>     simulate a tap, e.g. E5734107\n  list          cards kept for offline mode\n  status        Wi-Fi, server, trip, payments waiting to be sent\n  route <n>     switch route (starts a new trip)\n  trip          new trip\n  sync          send offline payments now and refresh the cards\n  sound [name]  play a payment sound (sound all = every one)\n  reset         back to the demo cards (only when nothing is waiting to be sent)");
  } else if (strncasecmp(line, "sound", 5) == 0 && (line[5] == '\0' || line[5] == ' ')) {
    testSound(line + 5);
  } else if (strcasecmp(line, "list") == 0) {
    listCards();
  } else if (strcasecmp(line, "status") == 0) {
    printStatus();
  } else if (strncasecmp(line, "route ", 6) == 0) {
    int n = atoi(line + 6);
    if (n >= 1 && n <= ROUTE_COUNT) {
      currentRoute = n - 1;
      serverFare = 0;            // the crew chose a route here: use its fare
      serverRouteName = "";
      newTrip();
    } else {
      Serial.println("No such route.");
    }
  } else if (strcasecmp(line, "reset") == 0) {
    if (queuedCount() > 0 || tripOffset > 0) {
      Serial.println("Not reset: offline payments are waiting to be sent. Type: sync");
    } else {
      loadDemoCards();
      Serial.println("Back to the demo cards (the server's list returns when it is reached).");
      lcdMessage("Demo cards", "loaded");
      listCards();
    }
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
    if (serverOnline && (cardsDue || millis() - lastCardsAt >= CARDS_EVERY_MS)) {
      lastCardsAt = millis();   // also spaces out retries when a sync keeps failing
      if (syncQueue()) fetchCards();
    }
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
