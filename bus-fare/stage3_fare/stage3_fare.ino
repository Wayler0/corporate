// Bus fare terminal - Stage 3: wallets + fixed fare per route
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

// ---------- EEPROM layout (balances survive power loss) ----------
const int EE_MAGIC = 0;       // 1 byte
const int EE_COUNT = 1;       // 1 byte: passenger count when saved
const int EE_ROUTE = 2;       // 1 byte
const int EE_TRIP_PAID = 3;   // 1 byte: bit i set = passenger i paid this trip
const int EE_BALANCES = 4;    // uint16_t per passenger
const byte MAGIC = 0x42;

// ---------- State ----------
MFRC522 rfid(SS_PIN, RST_PIN);
bool readerOk = false;
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
  setColor(r, g, b);
  delay(LED_MS);
  setColor(false, false, false);
}

void flashQuick() {
  setColor(true, false, false); delay(300);
  setColor(false, true, false); delay(300);
  setColor(false, false, true); delay(300);
  setColor(false, false, false);
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

void printRoute() {
  Serial.print(F("Route: "));
  Serial.print(ROUTES[currentRoute].name);
  Serial.print(F("  |  Fare: KSh "));
  Serial.println(ROUTES[currentRoute].fare);
}

// ---------- The fare logic ----------
void processTap(const char *uid, bool simulated) {
  uint16_t fare = ROUTES[currentRoute].fare;
  Serial.println(F("----------------------------------------"));
  Serial.print(simulated ? F("[SIM] Tap: ") : F("Tap: "));
  Serial.println(uid);

  int p = findPassenger(uid);
  if (p < 0) {
    Serial.println(F("REFUSED: unknown card. Register it first."));
    flash(true, false, false);
    return;
  }

  Serial.print(F("Passenger: "));
  Serial.println(PASSENGERS[p].name);

  if (hasPaidThisTrip(p)) {
    Serial.println(F("ALREADY PAID this trip: no charge."));
    flash(true, true, false);
    return;
  }

  if (balances[p] < fare) {
    Serial.print(F("REFUSED: insufficient balance. Has KSh "));
    Serial.print(balances[p]);
    Serial.print(F(", needs KSh "));
    Serial.println(fare);
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
  flash(false, true, false);
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
}

void handleLine(char *line) {
  while (*line == ' ') line++;
  if (*line == '\0') return;

  if (strcasecmp(line, "help") == 0) {
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
    }
  } else if (strcasecmp(line, "trip") == 0) {
    newTrip();
  } else if (strncasecmp(line, "topup ", 6) == 0) {
    topUp(line + 6);
  } else if (strcasecmp(line, "reset") == 0) {
    resetBalances();
    Serial.println(F("Balances reset."));
    listPassengers();
  } else {
    char uid[21];
    normalizeUid(line, uid, sizeof(uid));
    if (strlen(uid) < 8) {
      Serial.println(F("Not a command or card ID. Type: help"));
    } else {
      processTap(uid, true);
    }
  }
}

// ---------- Setup / loop ----------
void setup() {
  Serial.begin(9600);
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
  Serial.println(F(" Bus fare terminal - Stage 3"));
  Serial.println(F("========================================"));
  Serial.println(readerOk ? F("RC522 reader: found") : F("RC522 reader: not detected (simulation only)"));
  loadState();
  printRoute();
  Serial.println(F("Type 'help' for commands. Waiting for taps..."));

  // LED self-test: red, green, blue
  flashQuick();
}

// Re-check the reader every 2 s so a loose wire that reconnects is picked up
unsigned long lastReaderCheck = 0;
void checkReader() {
  if (millis() - lastReaderCheck < 2000) return;
  lastReaderCheck = millis();
  byte version = rfid.PCD_ReadRegister(MFRC522::VersionReg);
  bool ok = !(version == 0x00 || version == 0xFF);
  if (ok && !readerOk) {
    rfid.PCD_Init();
    Serial.println(F("RC522 reader: connected"));
  } else if (!ok && readerOk) {
    Serial.println(F("RC522 reader: LOST - check the wires"));
  }
  readerOk = ok;
}

void loop() {
  checkReader();

  if (Serial.available()) {
    char line[48];
    byte len = Serial.readBytesUntil('\n', line, sizeof(line) - 1);
    line[len] = '\0';
    if (len > 0 && line[len - 1] == '\r') line[len - 1] = '\0';
    handleLine(line);
  }

  if (readerOk && rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    char uid[21];
    byte n = 0;
    for (byte i = 0; i < rfid.uid.size && n < sizeof(uid) - 2; i++) {
      const char hex[] = "0123456789ABCDEF";
      uid[n++] = hex[rfid.uid.uidByte[i] >> 4];
      uid[n++] = hex[rfid.uid.uidByte[i] & 0x0F];
    }
    uid[n] = '\0';
    processTap(uid, false);
    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
  }
}
