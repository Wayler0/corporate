# Bus Fare Terminal: Wiring Manual

How to connect everything on the Arduino Uno, step by step. Everything here was
tested on the real kit (11–14 Nov 2026) unless marked **(not yet tested)**.
For the tidy boxed version, see **section 8: Final neat build**.
What has been done and tested so far, day by day: [`PROGRESS.md`](PROGRESS.md).
The wireless ESP32 version (the demo): **section 9**.

**Golden rules**

1. **Unplug the USB before changing any wire.**
2. The RC522 runs on **3.3V**. Never connect it to 5V.
3. Never put 9–12V into the 5V pin. Higher voltages only go into the round power jack.
4. After wiring, plug in the USB and check that the green **ON** light is on.
   If it is off, or the laptop disconnects the board, **unplug at once**: something is shorted.

---

## 1. Parts and where they go

| Part | Uno pins used |
|---|---|
| RGB LED module | A0, A1, A2, A3 (plugged straight in, no wires) |
| RC522 RFID reader | 10, 11, 12, 13, 9, 3.3V, GND |
| 16×2 LCD with I2C backpack | A4, A5, 5V, GND (4 wires) |
| Speaker (optional) | 8, GND |
| GSM module SIM800C (roadmap, not used by the fare firmware) | 2, 3, 5V, GND (pin 4 planned for power-on) |

No pin is used twice, so everything can be connected at the same time.
Pins 5–7 are free.

---

## 2. RGB LED module (no wires)

Push the module's 4 pins straight into the **ANALOG IN** header:

```
 Uno ANALOG IN:   A0   A1   A2   A3   A4   A5
                  R    G    B   GND
```

- The pin labelled **GND** must go into **A3**. The code drives A3 LOW, so it acts as ground.
- At start-up the LED flashes **red → green → blue** (self-test).
- Meaning: 🟢 green = paid · 🔴 red = refused · 🟡 yellow = already paid this trip.

| Problem | Fix |
|---|---|
| Nothing lights | Module not pushed in fully, or GND not in A3 |
| Colours in wrong order | R/G/B are in a different order on your module: tell Claude, it swaps them in code |
| Everything lights except the colour asked for | "Common anode" module: set `COMMON_ANODE = true` in the code |

---

## 3. RC522 RFID reader (7 male-to-female wires)

The 8-pin header is **soldered** (14 Nov, tested working). Push the **female** end
of each wire onto a pin; the **male** end goes into the Uno.

*Spare reader with no soldering:* push the straight pin strip through the holes,
tilt it so every pin presses against its hole, and hold it with a binder clip.
This works for testing but comes loose easily.

### Connections
Follow the labels printed on the RC522, not the positions:

| RC522 label | → Uno |
|---|---|
| SDA | 10 |
| SCK | 13 |
| MOSI | 11 |
| MISO | 12 |
| IRQ | *(leave empty)* |
| GND | GND (the one next to 5V, or next to pin 13) |
| RST | 9 |
| **3.3V** | **3.3V** ⚠️ not 5V |

```
 Uno POWER header:   IOREF  RESET  3.3V   5V   GND   GND   VIN
                                     ▲           ▲
                              RC522 3.3V    RC522 GND
```

### Checking it
- Upload `check_rc522`: the LED shows 🟢 when the reader answers, 🔴 when it doesn't.
- Your reader answers with version **0x82** (a compatible copy of the chip, works fine).
- Known cards: **white card `E5734107`**, **blue fob `008DEC53`**.

| Problem | Fix |
|---|---|
| Always red / "not detected" | Check SCK/MOSI/MISO aren't swapped (13/11/12) and 3.3V/GND are right |
| Green only while you press a pin | That contact is loose. **On 11 Nov the cause was a jumper with a bad tip at the Uno end; swapping the wire fixed it** |
| Connects then "LOST" | Re-clamp the pin strip; make sure nothing pulls on the wires |
| Connected but cards not read | Hold the card flat on the antenna for 2 seconds; don't press the board |

---

## 4. 16×2 LCD with I2C backpack (4 male-to-female wires)

The backpack is soldered to the LCD and hangs off the front edge like a flap
(checked from photos on 14 Nov: pin 1 meets pin 1, so it is electrically correct).
It is held only by its pins: **do not bend or lever it.** It cannot sit in the
breadboard, so wire it straight to the Uno.

**Follow the labels printed on the backpack, not the positions:**

| Backpack label | → Uno |
|---|---|
| GND | GND |
| VCC | **5V** |
| SDA | A4 |
| SCL | A5 |

```
 Uno POWER header:   IOREF  RESET  3.3V   5V   GND   GND   VIN
                                           ▲     ▲
                                     LCD VCC   LCD GND
 Uno ANALOG IN:   A0   A1   A2   A3   A4    A5
                  └─ RGB LED module ─┘ SDA   SCL
```

⚠️ **GND and VCC must not be swapped.** On 14 Nov the LCD did not answer and the
data lines measured about 4.5V and could not be pulled low: the signature of
reversed power. Reversed power can destroy the backpack's chip. Check these two
wires twice before plugging in the USB.

- The two-pin jumper marked **LED** must stay on, or the backlight is off.
- The **blue screw** is the contrast: if the backlight is on but there is no text,
  turn it slowly with a small screwdriver.
- The LCD's address is found automatically; nothing to set.

### Checking it
Upload `check_lcd` and open the Serial Monitor (9600). Once a second it reports:

| It says | Meaning |
|---|---|
| `device at 0x27` (or another number) | Working. The screen shows `LCD OK` |
| `nothing connected` on SDA or SCL | That wire is loose, or the backpack has no power |
| `connected` on both, but `no device answers` | Power is wrong (GND/VCC swapped or on the wrong Uno pin), or the chip is damaged |
| `STUCK LOW` | That data wire is touching GND |
| `SDA and SCL wires are CROSSED` | Swap the A4 and A5 wires |

| Problem | Fix |
|---|---|
| Backlight off | GND or VCC wire, or the LED jumper is missing |
| Backlight on, no text | Turn the blue screw; then run `check_lcd` |
| Top row of solid blocks | Chip answers but the LCD got no data: a bad solder joint between backpack and LCD |
| Strange symbols | A bad solder joint on one of the 16 pins |

### What the LCD shows

| When | Line 1 | Line 2 |
|---|---|---|
| Waiting | `Campus shuttle` | `KSh 50  Tap card` |
| Linked to the server | `Campus shuttle *` | `KSh 50  Tap card` |
| Asking the server | `Checking...` | card ID |
| Paid | `PAID KSh 50` | `Bal: KSh 450` |
| Already paid | `Already paid` | `Bal: KSh 450` |
| Not enough money | `Low balance` | `Has 30 need 50` |
| Unknown card | `Unknown card` | `See conductor` |
| Reader not connected | `Campus shuttle` | `Check reader!` |

*(The old 16-wire connection without a backpack is described at the top of
`stage4_lcd_fare.ino`, if it is ever needed again.)*

---

## 4b. Using the breadboard (for the RC522)

- Each numbered **column of 5 holes** (a–e, or f–j) is one connection.
  Neighbouring columns are separate. The gap in the middle separates e from f.
- The long **+** and **−** lines along the edges are *rails*: one connection along
  the whole edge.

Setup (needs the RC522's **straight** pin strip soldered, and 8 male-to-male wires):

1. Push the RC522's 8 pins into **row e**, one per column, with the reader's body
   lying over the gap. Holes a–d of each column stay free for wires.
2. One wire: Uno **GND** → **−** rail.
3. A wire from each pin's column (rows a–d) to the Uno, as in the table in section 3.
   GND goes to the − rail; **3.3V goes straight to the Uno's 3.3V pin**.
4. **Leave the + rail empty**, so 5V can never reach the reader.

---

## 4c. Speaker (tested 14 Nov)

A small speaker must never be wired straight to an Uno pin: it draws far too much
current. Put a resistor in series.

```
 Uno pin 8 ──[ 220Ω ]── speaker (+)
 Uno GND   ───────────── speaker (−)
```

- 220Ω = red, red, brown (150–330Ω also fine). It is quiet with no amplifier;
  a box with holes in front of the speaker makes it noticeably louder.
- Sounds (all near 3 kHz, where small speakers are loudest):
  **1 beep** = paid · **2 short beeps** = already paid · **3 short + 1 long** = refused.
- Speaker wires are very thin: solder them, or twist and fold the bare ends so they
  grip in the breadboard. ⚠️ On 14 Nov a stray speaker wire froze the Uno (uploads
  failed with `programmer is not responding`). If that happens: unplug, check no bare
  strand touches another pin, plug back in.
- If the "speaker" is a module with 3 pins or its own amplifier board, the wiring
  is different: ask before connecting.

---

## 4d. GSM module: SIM800C board (tested 14 Nov, without SIM)

**Not needed for the demo**: the terminal reaches the server over the laptop's USB
cable. This is for the roadmap (SMS receipts, a terminal that works inside a bus
without a laptop). The fare firmware does not use it yet; it can stay connected.

The board is a blue **"SIM800C GSM/GPRS BOARD"** (lent, often called "SIM800L").
It takes 5V and has its own level shifting, so it is safe on the Uno.

### Connections (soldered 8-pin header)

| Module label | → Uno | Notes |
|---|---|---|
| **5V** | 5V (breadboard + rail is fine) | power |
| **V_TTL** | 5V | sets its signals to 5V, to match the Uno |
| **GND** | GND | must be shared with the Uno |
| **TXD** | **pin 2** | module talks, Uno listens |
| **RXD** | **pin 3** | Uno talks, module listens |
| DTR, SPKP, SPKN | *(empty)* | |

The other row of holes (no pins) reads, starting at the **square** hole beside the
antenna socket:

```
 [VBAT]  GND   PWX   GND   VRTC   RI   MICP   MICN
   □      ○     ○     ○     ○      ○     ○      ○
```

### Switching it on: PWX (important)
The chip does **not** start by itself. Only the blue **POWER** light comes on and the
module answers nothing. To start it:

1. With the board powered, bridge **PWX** (3rd hole from the square one) to the
   **GND** hole beside it for **2 seconds**, using a jumper tip or a resistor leg.
2. The **status LED** next to POWER starts **blinking**: the chip is on.

⚠️ Count from the **square** hole: that is **VBAT**. Never bridge VBAT to GND.

Resetting or re-uploading the Uno does not switch the module off. Unplugging the
power does, and then PWX is needed again. *(Planned: a pin in PWX wired to Uno pin 4
so the Uno switches it on at start-up.)*

### Antenna
The gold **GSM_ANT** socket needs an antenna with a small snap-on **IPEX (u.FL)**
plug, 900/1800 MHz. None came with the board (Kim asked, 14 Nov). Without it the
signal is weak but the module still works for testing.

### Checking it
Upload `check_sim800l`, switch the chip on with PWX, open the Serial Monitor (9600,
**Both NL & CR**). Results on 14 Nov, no SIM, no antenna:

| Command | Answer | Meaning |
|---|---|---|
| `AT` | `OK` | wiring and power OK |
| `ATI` | `SIM800 R14.18` | model and firmware |
| `AT+CPIN?` | `ERROR` | no SIM card (expected) |
| `AT+CSQ` | `+CSQ: 8,0` | signal 8 of 31: weak but present |
| `AT+CBC` | `+CBC: 0,58,3867` | supply 3867 mV: healthy |

The LED module shows 🟢 if the module answers, 🔴 if not.

| Problem | Fix |
|---|---|
| Only the blue POWER light, `NO ANSWER` | Chip is off: do the PWX step |
| Status LED blinks but `NO ANSWER` | Swap the TXD/RXD wires; check V_TTL is on 5V |
| Lights flicker, or the Uno restarts | Not enough current: separate 5V 2A supply (GND joined to the Uno's) |

### With a SIM card (not yet tested)
- It then **needs its own 5V 2A supply** (phone charger or power bank), GND joined
  to the Uno's. USB from the laptop is not enough when it transmits.
- SIM holder is on the back of the board. SIM800 is **2G only**: check the network
  still offers 2G in your area.

---

## 5. Power

| Source | Plug into |
|---|---|
| Laptop (now) | USB cable → Uno's square USB port |
| Power bank / phone charger | Same USB cable |
| 9V battery (short demos only) | 9V clip with barrel plug → round black jack |
| Bus 12V | 12V→5V car USB adapter + USB cable (needs a fuse for a real install) |

Use one power source at a time.

**Phone battery (3.7V lithium cell):** it cannot run the Uno by itself; the Uno
needs 5V. It is only usable through a board that boosts it to 5V and has a USB
socket (that is what a power bank is). Never connect a bare lithium cell to the
Uno's 5V or VIN pin, never short its terminals, and never charge it without a
proper charging board. *(Your battery system has not been identified yet.)*

For the demo linked to the dashboard, the Uno is powered by the laptop's USB cable
anyway, because that cable also carries the data.

**No SIM card is needed for the demo.** The terminal talks to the server through
the laptop's USB cable. The borrowed GSM module (section 4d) and the ESP32 (Wi-Fi)
are roadmap items for a terminal that works inside a real bus. The GSM module is
wired and answers commands; with a SIM it needs its own 5V 2A supply. The ESP32 has
not been tried.

---

## 6. Uploading and testing

**Sketches** (each folder has one `.ino` file):

| Folder | What it does |
|---|---|
| `terminal_mvp` | **The demo firmware (use this one).** Standalone fare terminal that links to the server when the laptop bridge is running |
| `check_lcd` | Live LCD wiring check |
| `check_rc522` | Live reader check on the LED |
| `check_sim800l` | GSM module check (section 4d); works without a SIM |
| `stage1_read_card` … `stage5_i2c_lcd_fare` | Earlier steps, kept for reference |

**Plug and play:** with `terminal_mvp` loaded, just plug in the USB. An LCD or
reader connected late, or pushed back after coming loose, is picked up within
2 seconds. Nothing needs to be configured.

**Upload from the IDE:** open the `.ino` → Tools → Board → Arduino Uno →
Port `/dev/ttyACM0` → Upload (→ button).
After unplugging and replugging, the port can come back as `/dev/ttyACM1`: pick
whichever one is listed (`ls /dev/ttyACM*`).

**Upload from the terminal:**
```
arduino --upload --board arduino:avr:uno --port /dev/ttyACM0 bus-fare/terminal_mvp/terminal_mvp.ino
```

**Serial Monitor:** 9600 baud, line ending **Newline**. Commands:

| Type | Does |
|---|---|
| `E5734107` | Simulated tap of the white card (any card ID works) |
| `list` | Passengers and balances |
| `route` / `route 2` | Show routes / switch route (starts a new trip) |
| `trip` | New trip: every card can pay once again |
| `topup E5734107 100` | Add KSh 100 |
| `reset` | Restore start balances |
| `help` | All commands |

**Full test (expected results):**

| # | Do | LED | LCD |
|---|---|---|---|
| 1 | `reset` | — | `Balances reset` |
| 2 | Tap white card | 🟢 | `PAID KSh 50` / `Bal: KSh 450` |
| 3 | Tap blue fob | 🟢 | `PAID KSh 50` / `Bal: KSh 450` |
| 4 | Tap white card again | 🟡 | `Already paid` |
| 5 | `11223344` | 🔴 | `Low balance` |
| 6 | `99999999` | 🔴 | `Unknown card` |
| 7 | Unplug, plug back in, tap white card | 🟡 | `Already paid` (remembered) |
| 8 | `trip`, tap white card | 🟢 | `PAID KSh 50` / `Bal: KSh 400` |

**Library needs** (Tools → Manage Libraries): `MFRC522` by GithubCommunity.

### Link to the server (for the backend developer)

9600 baud, one line each. The laptop "bridge" program sits between the Uno and the server.

| Direction | Line | Meaning |
|---|---|---|
| Uno → laptop | `READY` | Terminal has started (opening the port restarts the Uno; wait for this) |
| Uno → laptop | `TAP E5734107` | A card was tapped |
| laptop → Uno | `LINK` | Heartbeat: send every 2–3 s while the server is up |
| laptop → Uno | `RES PAID 50 450` | Answer to a tap within 2 s: result, fare, new balance. Result is `PAID`, `REPEAT`, `LOW` or `UNKNOWN` |
| laptop → Uno | `MSG Top-up +100\|Bal: KSh 130` | Show two lines of text on the LCD |
| laptop → Uno | `FARE 70` | Change the fare |
| laptop → Uno | `trip` | Start a new trip |

Ignore every other line the Uno prints; those are for people. If no `RES` arrives
in 2 seconds, or no `LINK` for 8 seconds, the terminal carries on by itself.

To test the terminal without the real backend: `python3 tools/fake_server.py`
(add the port if it is not `/dev/ttyACM0`, e.g. `python3 tools/fake_server.py /dev/ttyACM1`).

**Tested on the real Uno, 14 Nov:** `LINK` → `*` on the LCD; taps answered `RES PAID`
and `RES REPEAT`; a `MSG` top-up appeared on the LCD; stopping the server removed
the `*` and the terminal carried on alone. In online mode the **server's balance is
the real one**; the Uno copies it so offline mode continues from the same number.

---

## 7. Shopping list

| Item | Approx. KSh | For |
|---|---|---|
| Male-to-female jumpers, 20 cm (20+) | 100–200 | Reaching the lid in the neat build |
| Male-to-male jumpers (10+) | 100–200 | Breadboard power rails |
| Active buzzer module (optional) | 50–150 | Louder than the bare speaker |
| Project box or plastic food container | — | Enclosure (**not metal**) |
| Hot glue, double-sided tape, cable ties | — | Mounting and tidying |
| Power bank (or one you own) | — | Running away from the laptop |

*Prices are rough estimates, not quotes.*

---

## 8. Final neat build (planned, not built yet)

Nothing in this section has been bought or built yet (no box as of 14 Nov).
The rails and the "flat board" option below need no new parts except jumpers.

### Power through the breadboard rails
Instead of one wire per module on the Uno's few GND pins, feed the rails once:

```
 Uno 5V   ── red ────► top    +  rail   → LCD VCC
 Uno GND  ── black ──► top    −  rail   → LCD GND, speaker (−)
 Uno 3.3V ── orange ─► bottom +  rail   → RC522 3.3V ONLY
 Uno GND  ── black ──► bottom −  rail   → RC522 GND
```

⚠️ Keep **3.3V and 5V on opposite sides** of the breadboard and mark the 3.3V rail
with tape. 5V on the reader destroys it.

Colours: **red = 5V, orange = 3.3V, black = GND**, anything else = signals.
Signal wires (SDA/SCL, SPI pins 9–13, pin 8) still go straight to the Uno as in
sections 3, 4 and 4c.

### Without a box: flat board (free)
Stick everything onto one stiff piece of cardboard, plywood or a file cover:
Uno and breadboard at the back, LCD standing up behind the reader (propped or taped
to a folded card), reader lying flat at the front with "TAP CARD" written beside it,
LED and speaker next to the LCD. Tape wire bundles down so nothing hangs. It looks
tidy, can be carried in one piece, and everything stays visible for the judges.

### Enclosure (if a box is bought later)
Plastic or wood only: the reader works through about 3 mm of it, not through metal.

```
        LID (passenger side)
  ┌───────────────────────────────────┐
  │   ┌───────────────────────┐   ●   │  ● RGB LED in a small hole
  │   │ PAID KSh 50        *  │       │
  │   │ Bal: KSh 550          │  ::: │  ::: speaker holes
  │   └───────────────────────┘       │
  │        ┌───────────────┐          │
  │        │  TAP CARD ))) │          │  RC522 fixed flat under the lid
  │        └───────────────┘          │
  └───────────────────────────────────┘
          USB cable out of the side
```

- **LCD:** cut a window; hold it from behind with hot glue or tape. Don't stress the
  backpack flap.
- **RC522:** face-up, directly under a "TAP CARD" label.
- **RGB LED:** move it off A0–A3 onto 4 M-F wires (same pins, R→A0 G→A1 B→A2
  GND→A3) so it shows through the lid. No code change.
- **Speaker:** face-down behind small holes; glue the edge.
- **Uno and breadboard:** stuck to the floor (the breadboard has a sticky back).
- Bundle each module's wires with tape or cable ties, and leave slack so opening the
  lid doesn't pull anything out.

Wires needed: LCD 4 + reader 7 + LED 4 + speaker 2 + rails 4 ≈ **21**.

### Before closing the box
1. ON light on, LED self-test red → green → blue, LCD shows the route.
2. Run the **Full test** in section 6.
3. Shake the box gently and tap again: if anything drops out, a joint is loose.

---

## 9. ESP32 wireless terminal (the demo version, tested 14 Nov)

Board: **ESP32-WROOM-32 DevKit**, 38 pins, USB-C. Firmware: `terminal_esp32`.
It is too wide for one breadboard (one free hole per pin), so either use the edge
holes (columns A and J), take it off and push female jumper ends onto its pins,
or put two breadboards side by side.

### Connections

| Part | Wire | ESP32 pin |
|---|---|---|
| RC522 | SDA / SCK / MOSI / MISO / RST | **G5 / G18 / G23 / G19 / G4** |
| | 3.3V | **3V3** ⚠️ never V5 |
| | GND | − rail |
| LCD backpack | SDA / SCL | **G21 / G22** |
| | VCC | **V5** |
| | GND | − rail |
| RGB LED | R / G / B | **G25 / G26 / G27**, GND → − rail |
| Piezo | + / − | **G13** / − rail |

```
 ESP32 3V3 ─► + rail (side 1) ─► RC522 3.3V only
 ESP32 V5  ─► + rail (side 2) ─► LCD VCC
 ESP32 GND ─► − rails (join both sides) ─► every GND
```

### Wi-Fi and server: `secrets.h`
Copy `terminal_esp32/secrets.example.h` to `secrets.h` and fill in:

| Setting | Example | Notes |
|---|---|---|
| `WIFI_SSID` / `WIFI_PASS` | `test` / … | 2.4 GHz only. If the router filters MACs, allow `30:76:F5:91:5A:5C` |
| `SERVER_URL` | `http://192.168.100.33:8000` | the laptop running the server, same network |
| `TERMINAL_TOKEN` | `demo-terminal-bus-1` | this vehicle's token from the server (`seed_demo`) |

`secrets.h` is never committed. The server must accept the network address:
the laptop's IP in `ALLOWED_HOSTS`, started with `runserver 0.0.0.0:8000`.

### Uploading
Arduino IDE: Tools → Board → **ESP32 Dev Module**, Port `/dev/ttyUSB0`, Upload.
From the terminal the board options must be spelled out:
```
arduino --upload --port /dev/ttyUSB0 --board esp32:esp32:esp32:UploadSpeed=921600,CPUFreq=240,FlashFreq=80,FlashMode=qio,FlashSize=4M,PartitionScheme=default,DebugLevel=none,PSRAM=disabled,LoopCore=1,EventsCore=1,EraseFlash=none bus-fare/terminal_esp32/terminal_esp32.ino
```
With `arduino-cli` (needs the MFRC522 library: `arduino-cli lib install MFRC522`):
```
arduino-cli compile --fqbn esp32:esp32:esp32 bus-fare/terminal_esp32
arduino-cli upload --fqbn esp32:esp32:esp32:UploadSpeed=115200 -p /dev/ttyUSB0 bus-fare/terminal_esp32
```
On this laptop 921600 baud fails half way ("chip stopped responding"); 115200 works.
If it still fails, run the upload again.

Serial Monitor: **115200** baud. Commands: `status`, `list`, `trip`, `sync`, a card
ID to simulate a tap, `help`.

### Payment sounds
Each result plays its own tune on the piezo. The tunes sit in one table near the
top of `terminal_esp32.ino` (section **Sounds**), as `{frequency Hz, length ms}`
notes, with `0` meaning a pause. Edit them, upload, and try each one from the Serial
Monitor with `sound paid`, `sound low` or `sound all` (no card needed).

| Sound | When | Default tune |
|---|---|---|
| `paid` | payment went through | rising chime C-E-G |
| `repeat` | already paid this trip | two beeps |
| `low` | failed: balance too low | falling "uh-oh" + long low tone |
| `unknown` | failed: card not registered or deactivated | triple low buzz |
| `topup` | a top-up message arrives from the server | quick rising run |
| `startup` | terminal ready after switch-on | two-note chirp |

`SOUND_ON = false` mutes the terminal (LED and LCD still work).

### What it does
| Situation | LCD | Behaviour |
|---|---|---|
| Server reachable | route + `*` | taps decided by the server |
| Server or Wi-Fi gone | "Server offline", no `*` | decides alone from its saved copy |
| Server back | "Server linked" | reconnects by itself within ~5 s |
| Asking the server | "Checking..." + 🔵 | answer within 2 s, else offline decision |
| Lost card (blocked by its owner) | "Card blocked / Reported lost" | refused, online and offline |

### Offline mode
While online the terminal downloads **every active card** every 30 s
(`GET /api/terminal/cards/`): balance, blocked, company pays, already paid this trip.
The list is kept in flash, so offline mode works for every employee, also after a
power cut. Up to 1000 cards.

A payment taken offline goes into a **queue in flash**. When the server answers
again the terminal **first sends the queue** (`POST /api/terminal/sync/`), then
downloads a fresh card list. Each tap carries its own number, so sending it twice
never charges twice. A trip started offline (`trip`, `route <n>`) is sent too and
becomes the bus's running trip on the server, unless the crew started a newer one
on the dashboard meanwhile. `status` shows how many payments are waiting; `sync`
sends them at once.

On the server an offline payment is dated when the card was tapped. The passenger
has already ridden, so the terminal's decision stands: if the card was spent on
another bus meanwhile, only what is left is taken (the amount is then less than the
fare), and a card blocked **before** the tap is recorded as BLOCKED with no fare.

Before the terminal has ever reached the server it uses the four demo cards; `reset`
brings them back (refused while payments are waiting to be sent).

### Checks
`check_esp32_parts` (every part, every 5 s) and `check_esp32_wifi` (joins the
network, tests the internet; uses its own `secrets.h`).

### Power
USB-C from a phone charger or power bank works. The LiPo battery on its TP4056
board needs a **5 V boost board (MT3608)** before it can run the terminal; set it
to 5.0 V with a multimeter **before** connecting. Never put the battery on 3V3.
