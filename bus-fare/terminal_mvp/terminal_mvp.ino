// Bus fare terminal - DEMO / MVP firmware (plug and play)
//
// Plug in the USB and it works. Nothing has to be set up by hand:
//   * LCD address is found automatically; an LCD or reader that is plugged in
//     late (or comes loose and is pushed back) is picked up within 2 seconds.
//   * With no laptop program running it is a complete standalone fare terminal
//     (same logic as Stages 3-5, balances kept in the Uno's own memory).
//   * When the laptop "bridge" program is running, every tap is sent to the
//     server and the server's answer is shown. If the server stops answering,
//     the terminal quietly goes back to standalone mode. A '*' in the top right
//     corner of the LCD means "linked to the server".
//
// ---- Serial protocol (9600 baud, one line each, ends with newline) ----
//   Uno -> laptop:
//     READY                     terminal has started
//     TAP <card id>             a card was tapped, e.g.  TAP E5734107
//   laptop -> Uno:
//     LINK                      heartbeat: send every 2-3 s while the server is up
//     RES <result> <fare> <balance>
//                               answer to a TAP, within 2 s. <result> is one of
//                               PAID  REPEAT  LOW  UNKNOWN   e.g.  RES PAID 50 450
//     MSG <line 1>|<line 2>     show any text on the LCD, e.g.  MSG Top-up +100|Bal: KSh 130
//     FARE <KSh>                change the fare shown (and used) by the terminal
//     trip                      start a new trip (also clears the Uno's own record)
//   Every other line the Uno prints is for humans; the bridge should ignore
//   anything that does not start with "TAP " or "READY".
//
// LCD I2C backpack (4 pins) -> Uno:
//   GND -> GND   VCC -> 5V   SDA -> A4   SCL -> A5
//   The backpack's address (0x27, 0x3F, ...) is found automatically.
//   Contrast: turn the blue screw on the backpack. Backlight: keep the jumper on.
//   No extra library is needed (the small driver is in this file).
//
// --- Original Stage 3 notes ---
// Board: Arduino Uno. Works with NO soldering: Serial Monitor is the screen,
// the RGB LED module shows the result, and taps can be typed in.
// The RC522 is used automatically if it is connected and detected.
//
// Libraries: "MFRC522" by GithubCommunity, EEPROM (built in)
//
// RGB LED module: plugged straight into the ANALOG IN header, no wires:
//   R -> A0   G -> A1   B -> A2   GND -> A3 (A3 is driven LOW to act as ground)
//   (If colours look inverted, your module is common-anode: set COMMON_ANODE
//    to true; A3 is then driven HIGH instead.)
// RC522 (optional) -> Uno:  SDA->10 SCK->13 MOSI->11 MISO->12 RST->9 3.3V GND
//
// Serial Monitor: 9600 baud, line ending "Newline". Type "help" for commands.
//
// LED meaning:  GREEN = paid   RED = refused   YELLOW = already paid this trip
//
// Each card pays once per trip. Type "trip" (or change route) to start a new
// trip. Who has paid is saved, so a power cut does not let anyone pay twice.

#include <SPI.h>
#include <MFRC522.h>
#include <EEPROM.h>

// ---------- Pins ----------
const byte SS_PIN = 10;
const byte RST_PIN = 9;
const byte LED_R = A0;
const byte LED_G = A1;
const byte LED_B = A2;
const byte LED_COMMON = A3;  // LED module's GND pin sits here
const byte SPEAKER_PIN = 8;  // optional: pin 8 -> 220 ohm resistor -> speaker -> GND
const unsigned long LCD_MESSAGE_MS = 3000;  // result stays on screen this long
const bool COMMON_ANODE = false;

// ---------- Routes (example fares in KSh: change to the real ones) ----------
struct Route {
  const char *name;
  uint16_t fare;
};
const Route ROUTES[] = {
  {"Campus shuttle", 50},
  {"Marimanti-Chuka", 100},
  {"Marimanti-Meru", 250},
};
const byte ROUTE_COUNT = sizeof(ROUTES) / sizeof(ROUTES[0]);

// ---------- Passengers ----------
// UIDs are hex with no spaces (as printed by Stage 1 or check_rc522).
struct Passenger {
  const char *uid;
  const char *name;
  uint16_t startBalance;
};
const Passenger PASSENGERS[] = {
  {"A1B2C3D4", "Test: Kim",       200},
  {"11223344", "Test: low funds",  30},
  {"E5734107", "White card",      500},  // read 2026-11-11
  {"008DEC53", "Blue fob",        500},  // read 2026-11-11
};
const byte PASSENGER_COUNT = sizeof(PASSENGERS) / sizeof(PASSENGERS[0]);

// ---------- Settings ----------
const uint16_t MAX_BALANCE = 50000;
const unsigned long LED_MS = 1500;
const unsigned long SERVER_REPLY_MS = 2000;   // wait this long for RES, then go standalone
const unsigned long LINK_TIMEOUT_MS = 8000;   // no LINK heartbeat for this long = standalone
const byte LINE_MAX = 48;

// ---------- EEPROM layout (balances survive power loss) ----------
const int EE_MAGIC = 0;       // 1 byte
const int EE_COUNT = 1;       // 1 byte: passenger count when saved
const int EE_ROUTE = 2;       // 1 byte
const int EE_TRIP_PAID = 3;   // 1 byte: bit i set = passenger i paid this trip
const int EE_BALANCES = 4;    // uint16_t per passenger
const byte MAGIC = 0x42;

// ---------- State ----------
MFRC522 rfid(SS_PIN, RST_PIN);

// Minimal driver for a 16x2 LCD behind a PCF8574 I2C backpack.
// Backpack bits: P0=RS P1=RW P2=E P3=backlight P4-P7=D4-D7 (the usual layout).
class I2cLcd : public Print {
 public:
  byte address = 0;  // 0 = no LCD found

  bool busStuck = false;  // true = SDA or SCL is being held low (wiring fault)

  bool begin() {
    address = 0;
    release(SDA);
    release(SCL);
    delayMicroseconds(50);
    busStuck = !digitalRead(SDA) || !digitalRead(SCL);
    if (busStuck) return false;
    for (byte a = 0x20; a <= 0x3F && !address; a++) {
      if (a == 0x28) a = 0x38;  // PCF8574: 0x20-0x27, PCF8574A: 0x38-0x3F
      if (probe(a)) address = a;
    }
    if (!address) return false;
    init();
    return true;
  }

  // True if the LCD found earlier still answers
  bool present() {
    return address && probe(address);
  }

  // Safe to call at any time: brings the LCD back to a known state
  void init() {
    if (!address) return;
    delay(50);
    expander(0);
    nibble(0x30); delay(5);
    nibble(0x30); delay(5);
    nibble(0x30); delay(1);
    nibble(0x20);            // 4-bit mode
    command(0x28);           // 2 lines, 5x8 font
    command(0x0C);           // display on, no cursor
    command(0x01); delay(2); // clear
    command(0x06);           // left to right
  }

  void setCursor(byte col, byte row) { command(0x80 | (col + (row ? 0x40 : 0x00))); }

  virtual size_t write(uint8_t c) {
    send(c, 0x01);
    return 1;
  }

 private:
  // --- I2C done by hand on A4 (SDA) and A5 (SCL) ---
  // The built-in Wire library can freeze the whole board when a wire is loose
  // or the LCD has no power. This version can never get stuck.
  void release(byte pin) { pinMode(pin, INPUT_PULLUP); }
  void pullLow(byte pin) {
    digitalWrite(pin, LOW);
    pinMode(pin, OUTPUT);
  }
  void i2cStart() {
    release(SDA);
    release(SCL);
    pullLow(SDA);
    pullLow(SCL);
  }
  void i2cStop() {
    pullLow(SDA);
    release(SCL);
    release(SDA);
  }
  // Sends one byte; returns true if the LCD acknowledged it
  bool i2cWrite(byte value) {
    for (byte bit = 0; bit < 8; bit++, value <<= 1) {
      if (value & 0x80) release(SDA); else pullLow(SDA);
      release(SCL);
      pullLow(SCL);
    }
    release(SDA);
    release(SCL);
    bool ack = !digitalRead(SDA);
    pullLow(SCL);
    return ack;
  }
  bool probe(byte a) {
    i2cStart();
    bool ack = i2cWrite(a << 1);
    i2cStop();
    return ack;
  }
  void expander(byte data) {
    if (!address) return;
    i2cStart();
    i2cWrite(address << 1);
    i2cWrite(data | 0x08);  // 0x08 keeps the backlight on
    i2cStop();
  }
  void nibble(byte data) {
    expander(data | 0x04);  // E high
    delayMicroseconds(1);
    expander(data);         // E low
    delayMicroseconds(50);
  }
  void send(byte value, byte rs) {
    nibble((value & 0xF0) | rs);
    nibble(((value << 4) & 0xF0) | rs);
  }
  void command(byte value) { send(value, 0x00); }
};

I2cLcd lcd;
unsigned long lcdMessageAt = 0;
bool lcdShowingMessage = false;
bool readerOk = false;
bool lcdOk = false;
bool linkOnline = false;          // true while the laptop bridge is sending LINK
unsigned long lastLinkAt = 0;
uint16_t serverFare = 0;          // set by "FARE n"; 0 = use the route's own fare
char rxBuf[LINE_MAX];
byte rxLen = 0;
uint16_t balances[PASSENGER_COUNT];
byte currentRoute = 0;
static_assert(PASSENGER_COUNT <= 8, "trip-paid flags fit in one byte: max 8 passengers");
byte tripPaid = 0;  // bit i set = passenger i already paid this trip

// ---------- LED ----------
void setColor(bool r, bool g, bool b) {
  digitalWrite(LED_R, r != COMMON_ANODE);
  digitalWrite(LED_G, g != COMMON_ANODE);
  digitalWrite(LED_B, b != COMMON_ANODE);
}
void flash(bool r, bool g, bool b) {
  // Sound to match the colour (harmless if no speaker is connected).
  // All around 2.7-3 kHz, where small speakers are loudest; told apart by pattern.
  setColor(r, g, b);
  unsigned long start = millis();
  if (g && !r) {                       // green: one beep
    tone(SPEAKER_PIN, 3000, 200);
  } else if (r && g) {                 // yellow: two short beeps
    tone(SPEAKER_PIN, 2700, 90); delay(160);
    tone(SPEAKER_PIN, 2700, 90);
  } else if (r) {                      // red: three beeps, then a long one
    for (byte i = 0; i < 3; i++) { tone(SPEAKER_PIN, 2700, 80); delay(140); }
    tone(SPEAKER_PIN, 2700, 400);
  }
  unsigned long used = millis() - start;
  if (used < LED_MS) delay(LED_MS - used);
  setColor(false, false, false);
}

void flashQuick() {
  setColor(true, false, false); delay(300);
  setColor(false, true, false); delay(300);
  setColor(false, false, true); delay(300);
  setColor(false, false, false);
}

// ---------- LCD ----------
// Prints text and pads with spaces so old characters are erased
void lcdLine(byte row, const String &text) {
  lcd.setCursor(0, row);
  String t = text.substring(0, 16);
  lcd.print(t);
  for (byte i = t.length(); i < 16; i++) lcd.print(' ');
}

void lcdIdle();  // defined after ROUTES helpers

void lcdMessage(const String &line1, const String &line2) {
  lcdLine(0, line1);
  lcdLine(1, line2);
  lcdMessageAt = millis();
  lcdShowingMessage = true;
}

// ---------- Storage ----------
void saveBalance(byte i) { EEPROM.put(EE_BALANCES + i * sizeof(uint16_t), balances[i]); }
void saveRoute() { EEPROM.update(EE_ROUTE, currentRoute); }

void resetBalances() {
  for (byte i = 0; i < PASSENGER_COUNT; i++) {
    balances[i] = PASSENGERS[i].startBalance;
    saveBalance(i);
  }
  currentRoute = 0;
  saveRoute();
  tripPaid = 0;
  EEPROM.update(EE_TRIP_PAID, tripPaid);
  EEPROM.update(EE_COUNT, PASSENGER_COUNT);
  EEPROM.update(EE_MAGIC, MAGIC);
}

void loadState() {
  if (EEPROM.read(EE_MAGIC) != MAGIC || EEPROM.read(EE_COUNT) != PASSENGER_COUNT) {
    Serial.println(F("First run (or passenger list changed): loading start balances."));
    resetBalances();
    return;
  }
  for (byte i = 0; i < PASSENGER_COUNT; i++) {
    EEPROM.get(EE_BALANCES + i * sizeof(uint16_t), balances[i]);
  }
  currentRoute = EEPROM.read(EE_ROUTE);
  tripPaid = EEPROM.read(EE_TRIP_PAID);
  if (currentRoute >= ROUTE_COUNT) currentRoute = 0;
}

// ---------- Helpers ----------
bool hasPaidThisTrip(byte i) { return tripPaid & (1 << i); }

void markPaid(byte i) {
  tripPaid |= (1 << i);
  EEPROM.update(EE_TRIP_PAID, tripPaid);
}

void newTrip() {
  tripPaid = 0;
  EEPROM.update(EE_TRIP_PAID, tripPaid);
  Serial.println(F("New trip started: every card can pay once."));
  lcdMessage(F("New trip"), ROUTES[currentRoute].name);
}

// Keep only hex digits, uppercase: "a1 b2 c3 d4" -> "A1B2C3D4"
void normalizeUid(const char *in, char *out, byte outSize) {
  byte n = 0;
  for (; *in && n < outSize - 1; in++) {
    char c = toupper(*in);
    if ((c >= '0' && c <= '9') || (c >= 'A' && c <= 'F')) out[n++] = c;
  }
  out[n] = '\0';
}

int findPassenger(const char *uid) {
  for (byte i = 0; i < PASSENGER_COUNT; i++) {
    if (strcmp(uid, PASSENGERS[i].uid) == 0) return i;
  }
  return -1;
}

uint16_t currentFare() { return serverFare ? serverFare : ROUTES[currentRoute].fare; }

void lcdIdle() {
  lcd.init();  // self-heal: a display that lost power for a moment comes back
  String top = String(ROUTES[currentRoute].name).substring(0, 14);
  if (linkOnline) {
    while (top.length() < 15) top += ' ';
    top += '*';  // linked to the server
  }
  lcdLine(0, top);
  if (readerOk) {
    lcdLine(1, String(F("KSh ")) + currentFare() + F("  Tap card"));
  } else {
    lcdLine(1, F("Check reader!"));
  }
  lcdShowingMessage = false;
}

// Collects serial characters; returns true when a whole line has arrived
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
    if (rxLen < LINE_MAX - 1) rxBuf[rxLen++] = c;
  }
  return false;
}

void printRoute() {
  Serial.print(F("Route: "));
  Serial.print(ROUTES[currentRoute].name);
  Serial.print(F("  |  Fare: KSh "));
  Serial.println(currentFare());
}

// ---------- The fare logic ----------
// Standalone mode: decide here, using the balances in the Uno's own memory
void processTap(const char *uid, bool simulated) {
  uint16_t fare = currentFare();
  Serial.println(F("----------------------------------------"));
  Serial.print(simulated ? F("[SIM] Card: ") : F("Card: "));
  Serial.println(uid);

  int p = findPassenger(uid);
  if (p < 0) {
    Serial.println(F("REFUSED: unknown card. Register it first."));
    lcdMessage(F("Unknown card"), F("See conductor"));
    flash(true, false, false);
    return;
  }

  Serial.print(F("Passenger: "));
  Serial.println(PASSENGERS[p].name);

  if (hasPaidThisTrip(p)) {
    Serial.println(F("ALREADY PAID this trip: no charge."));
    lcdMessage(F("Already paid"), String(F("Bal: KSh ")) + balances[p]);
    flash(true, true, false);
    return;
  }

  if (balances[p] < fare) {
    Serial.print(F("REFUSED: insufficient balance. Has KSh "));
    Serial.print(balances[p]);
    Serial.print(F(", needs KSh "));
    Serial.println(fare);
    lcdMessage(F("Low balance"), String(F("Has ")) + balances[p] + F(" need ") + fare);
    flash(true, false, false);
    return;
  }

  balances[p] -= fare;
  saveBalance(p);
  markPaid(p);

  Serial.print(F("PAID KSh "));
  Serial.print(fare);
  Serial.print(F(" (" ));
  Serial.print(ROUTES[currentRoute].name);
  Serial.print(F(")  |  Balance: KSh "));
  Serial.println(balances[p]);
  lcdMessage(String(F("PAID KSh ")) + fare, String(F("Bal: KSh ")) + balances[p]);
  flash(false, true, false);
}

// ---------- Server mode ----------
// Show what the server decided. Also copies it into the Uno's own memory so
// that standalone mode carries on from the same balances if the link drops.
void showServerResult(const char *uid, char *args) {
  char *result = strtok(args, " ");
  char *fareText = strtok(NULL, " ");
  char *balanceText = strtok(NULL, " ");
  if (!result) result = (char *)"";
  uint16_t fare = fareText ? (uint16_t)atol(fareText) : currentFare();
  long balance = balanceText ? atol(balanceText) : 0;
  int p = findPassenger(uid);
  if (p >= 0 && balanceText && balance >= 0 && balance <= MAX_BALANCE) {
    balances[p] = (uint16_t)balance;
    saveBalance(p);
  }
  Serial.print(F("Server: "));
  Serial.println(result);

  if (strcmp(result, "PAID") == 0) {
    if (p >= 0) markPaid(p);
    lcdMessage(String(F("PAID KSh ")) + fare, String(F("Bal: KSh ")) + balance);
    flash(false, true, false);
  } else if (strcmp(result, "REPEAT") == 0) {
    if (p >= 0) markPaid(p);
    lcdMessage(F("Already paid"), String(F("Bal: KSh ")) + balance);
    flash(true, true, false);
  } else if (strcmp(result, "LOW") == 0) {
    lcdMessage(F("Low balance"), String(F("Has ")) + balance + F(" need ") + fare);
    flash(true, false, false);
  } else {
    lcdMessage(F("Unknown card"), F("See conductor"));
    flash(true, false, false);
  }
}

// Ask the server. Returns false if it did not answer in time.
bool serverTap(const char *uid) {
  Serial.print(F("TAP "));
  Serial.println(uid);
  lcdLine(0, F("Checking..."));
  lcdLine(1, uid);
  setColor(false, false, true);  // blue = waiting for the server
  unsigned long start = millis();
  char line[LINE_MAX];
  while (millis() - start < SERVER_REPLY_MS) {
    if (!readLine(line)) continue;
    if (strncmp(line, "RES ", 4) == 0) {
      lastLinkAt = millis();
      setColor(false, false, false);
      showServerResult(uid, line + 4);
      return true;
    }
    if (strcmp(line, "LINK") == 0) lastLinkAt = millis();
  }
  setColor(false, false, false);
  linkOnline = false;
  Serial.println(F("No server reply: standalone mode"));
  return false;
}

// Every tap (real or typed) comes through here
void handleTap(const char *uid, bool simulated) {
  if (linkOnline && serverTap(uid)) return;
  processTap(uid, simulated);
}

// ---------- Commands ----------
void printHelp() {
  Serial.println(F("Commands:"));
  Serial.println(F("  <card id>            simulate a tap, e.g.  A1 B2 C3 D4"));
  Serial.println(F("  list                 show passengers and balances"));
  Serial.println(F("  route                show routes and the current one"));
  Serial.println(F("  route <n>            switch route (starts a new trip), e.g.  route 2"));
  Serial.println(F("  trip                 start a new trip: every card can pay again"));
  Serial.println(F("  topup <card id> <KSh>  add money, e.g.  topup A1B2C3D4 100"));
  Serial.println(F("  reset                restore all start balances"));
}

void listPassengers() {
  for (byte i = 0; i < PASSENGER_COUNT; i++) {
    Serial.print(PASSENGERS[i].uid);
    Serial.print(F("  "));
    Serial.print(PASSENGERS[i].name);
    Serial.print(F("  KSh "));
    Serial.println(balances[i]);
  }
}

void listRoutes() {
  for (byte i = 0; i < ROUTE_COUNT; i++) {
    Serial.print(i == currentRoute ? F("* ") : F("  "));
    Serial.print(i + 1);
    Serial.print(F(". "));
    Serial.print(ROUTES[i].name);
    Serial.print(F("  KSh "));
    Serial.println(ROUTES[i].fare);
  }
}

void topUp(char *args) {
  // Amount is the last word; everything before it is the card ID
  char *space = strrchr(args, ' ');
  if (!space) {
    Serial.println(F("Usage: topup <card id> <KSh>"));
    return;
  }
  long amount = atol(space + 1);
  *space = '\0';
  char uid[21];
  normalizeUid(args, uid, sizeof(uid));
  int p = findPassenger(uid);
  if (p < 0) {
    Serial.println(F("Unknown card."));
    return;
  }
  if (amount <= 0 || (long)balances[p] + amount > MAX_BALANCE) {
    Serial.print(F("Amount must be 1 to "));
    Serial.println(MAX_BALANCE - balances[p]);
    return;
  }
  balances[p] += amount;
  saveBalance(p);
  Serial.print(F("Topped up "));
  Serial.print(PASSENGERS[p].name);
  Serial.print(F(" by KSh "));
  Serial.print(amount);
  Serial.print(F(". New balance: KSh "));
  Serial.println(balances[p]);
  lcdMessage(String(F("Top-up +")) + amount, String(F("Bal: KSh ")) + balances[p]);
}

void handleLine(char *line) {
  while (*line == ' ') line++;
  if (*line == '\0') return;

  if (strcmp(line, "LINK") == 0) {
    lastLinkAt = millis();
    if (!linkOnline) {
      linkOnline = true;
      Serial.println(F("Server: linked"));
      lcdMessage(F("Server linked"), F("Online mode"));
    }
  } else if (strncmp(line, "RES ", 4) == 0) {
    // a late answer to a tap we already handled ourselves: ignore
  } else if (strncmp(line, "MSG ", 4) == 0) {
    char *second = strchr(line + 4, '|');
    if (second) *second++ = '\0';
    lcdMessage(line + 4, second ? second : "");
  } else if (strncasecmp(line, "fare ", 5) == 0) {
    long f = atol(line + 5);
    if (f > 0 && f <= MAX_BALANCE) {
      serverFare = (uint16_t)f;
      printRoute();
      lcdIdle();
    }
  } else if (strcasecmp(line, "help") == 0) {
    printHelp();
  } else if (strcasecmp(line, "list") == 0) {
    listPassengers();
  } else if (strcasecmp(line, "route") == 0) {
    listRoutes();
  } else if (strncasecmp(line, "route ", 6) == 0) {
    int n = atoi(line + 6);
    if (n < 1 || n > ROUTE_COUNT) {
      Serial.println(F("No such route. Type: route"));
    } else {
      currentRoute = n - 1;
      saveRoute();
      printRoute();
      newTrip();
      lcdIdle();
    }
  } else if (strcasecmp(line, "trip") == 0) {
    newTrip();
  } else if (strncasecmp(line, "topup ", 6) == 0) {
    topUp(line + 6);
  } else if (strcasecmp(line, "reset") == 0) {
    resetBalances();
    Serial.println(F("Balances reset."));
    lcdMessage(F("Balances reset"), F("New trip"));
    listPassengers();
  } else {
    char uid[21];
    normalizeUid(line, uid, sizeof(uid));
    if (strlen(uid) < 8) {
      Serial.println(F("Not a command or card ID. Type: help"));
    } else {
      handleTap(uid, true);
    }
  }
}

// ---------- Setup / loop ----------
void setup() {
  Serial.begin(9600);
  lcdOk = lcd.begin();
  lcdLine(0, F("Bus Fare System"));
  lcdLine(1, F("Starting..."));
  pinMode(LED_R, OUTPUT);
  pinMode(LED_G, OUTPUT);
  pinMode(LED_B, OUTPUT);
  pinMode(LED_COMMON, OUTPUT);
  digitalWrite(LED_COMMON, COMMON_ANODE ? HIGH : LOW);
  setColor(false, false, false);

  SPI.begin();
  rfid.PCD_Init();
  delay(50);
  byte version = rfid.PCD_ReadRegister(MFRC522::VersionReg);
  readerOk = !(version == 0x00 || version == 0xFF);

  Serial.println(F("========================================"));
  Serial.println(F(" Bus fare terminal - demo firmware"));
  Serial.println(F("========================================"));
  if (lcdOk) {
    Serial.print(F("LCD: found at address 0x"));
    Serial.println(lcd.address, HEX);
  } else {
    Serial.println(lcd.busStuck
      ? F("LCD: WIRING FAULT - A4 or A5 is held low. Check the LCD's GND and VCC wires, and that SDA/SCL are not swapped with power.")
      : F("LCD: not detected - check GND, VCC, SDA->A4, SCL->A5 (it will be picked up when connected)"));
  }
  Serial.println(readerOk ? F("RC522 reader: found") : F("RC522 reader: not detected (simulation only)"));
  loadState();
  printRoute();
  Serial.println(F("Type 'help' for commands. Waiting for taps..."));

  // LED self-test: red, green, blue
  flashQuick();
  lcdLine(1, readerOk ? F("Reader OK") : F("No reader!"));
  delay(1000);
  lcdIdle();
  Serial.println(F("READY"));
}

// Every 2 s: re-check the reader and the LCD, so anything plugged in late or
// pushed back after coming loose starts working by itself.
unsigned long lastReaderCheck = 0;
void checkHardware() {
  if (millis() - lastReaderCheck < 2000) return;
  lastReaderCheck = millis();

  bool lcdNow = lcd.address ? lcd.present() : lcd.begin();
  if (!lcdNow) lcd.address = 0;
  if (lcdNow && !lcdOk) {
    Serial.print(F("LCD: connected at address 0x"));
    Serial.println(lcd.address, HEX);
    lcdOk = true;
    lcdIdle();
  } else if (!lcdNow && lcdOk) {
    Serial.println(F("LCD: LOST - check the 4 wires"));
  }
  lcdOk = lcdNow;

  byte version = rfid.PCD_ReadRegister(MFRC522::VersionReg);
  bool ok = !(version == 0x00 || version == 0xFF);
  if (ok && !readerOk) {
    rfid.PCD_Init();
    Serial.println(F("RC522 reader: connected"));
  } else if (!ok && readerOk) {
    Serial.println(F("RC522 reader: LOST - check the wires"));
  }
  bool changed = (ok != readerOk);
  readerOk = ok;
  if (changed && !lcdShowingMessage) lcdIdle();
}

void loop() {
  checkHardware();
  if (linkOnline && millis() - lastLinkAt > LINK_TIMEOUT_MS) {
    linkOnline = false;
    Serial.println(F("Server: link lost, standalone mode"));
    lcdMessage(F("Server offline"), F("Standalone mode"));
  }
  if (lcdShowingMessage && millis() - lcdMessageAt > LCD_MESSAGE_MS) lcdIdle();

  char line[LINE_MAX];
  if (readLine(line)) handleLine(line);

  if (readerOk && rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    char uid[21];
    byte n = 0;
    for (byte i = 0; i < rfid.uid.size && n < sizeof(uid) - 2; i++) {
      const char hex[] = "0123456789ABCDEF";
      uid[n++] = hex[rfid.uid.uidByte[i] >> 4];
      uid[n++] = hex[rfid.uid.uidByte[i] & 0x0F];
    }
    uid[n] = '\0';
    handleTap(uid, false);
    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
  }
}
