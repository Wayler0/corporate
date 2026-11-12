# Bus Fare Terminal: Wiring Manual

How to connect everything on the Arduino Uno, step by step. Everything here was
tested on the real kit (11–12 Nov 2026) unless marked **(not yet tested)**.

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
| 16×2 LCD | 7, 6, 5, 4, 3, 2, 5V, GND (+ A5 for the backlight) |
| Buzzer (later) | 8 |

No pin is used twice, so everything can be connected at the same time.

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

### Fitting the pins without soldering
1. Push the **straight 8-pin strip** through the RC522's 8 holes, from the chip side.
2. **Tilt it slightly** so every pin presses against the side of its hole.
3. Hold it with a **clothes peg or binder clip** (stronger than tape).
4. Push the **female** end of each wire onto a pin; the **male** end goes into the Uno.

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

## 4. 16×2 LCD

Your LCD's labels, in order: **GND VDD VO RS RW E D0 D1 D2 D3 D4 D5 D6 D7 BLA BLK**
(pin 1 = GND at one end, pin 16 = BLK at the other).

### 4a. Temporary setup: 10 male-to-female wires, no backlight (what works now)

Used while the RC522's wires are borrowed. Push the 16-pin strip through the LCD's
holes, tilt it and clamp it, then put the female ends on the pins:

| LCD | → Uno |
|---|---|
| GND | GND |
| VDD | **5V** |
| VO | GND |
| RS | 7 |
| RW | GND |
| E | 6 |
| D0, D1, D2, D3 | *(leave empty)* |
| D4 | 5 |
| D5 | 4 |
| D6 | 3 |
| D7 | 2 |
| BLA, BLK | *(leave empty)* |

The Uno has 3 GND pins (two next to 5V, one next to pin 13): GND, VO and RW use one each.
Without the backlight, tilt the screen towards the light to read it.

### 4b. Final setup: through the breadboard with male-to-male wires (not yet tested)

This frees the male-to-female wires for the RC522 and adds the backlight.

**Breadboard basics:** the long lines along the edges marked **+** (red) and **−** (blue)
are *rails*: every hole in one line is connected. In the middle, each numbered *column*
of 5 holes (a–e) is connected; the gap in the middle separates a–e from f–j.

**Step 1: power rails (2 male-to-male wires)**
- Uno **5V** → breadboard **+ rail**
- Uno **GND** → breadboard **− rail**

**Step 2: seat the LCD**
- Push the 16-pin strip into row **a** of 16 neighbouring columns, so each LCD pin has its own column.
- Put the LCD on the strip, tilt it slightly and clamp it (like the RC522).
- Write down which column each LCD pin is in (e.g. GND = column 10 … BLK = column 25).

**Step 3: connect each LCD column (male-to-male wires into the same column, rows b–e)**

| LCD pin's column | → |
|---|---|
| GND | − rail |
| VDD | + rail |
| VO | − rail through a **1k resistor** (or a 10k potentiometer's middle leg: outer legs to + and −) |
| RS | Uno 7 |
| RW | − rail |
| E | Uno 6 |
| D0–D3 | *(nothing)* |
| D4 | Uno 5 |
| D5 | Uno 4 |
| D6 | Uno 3 |
| D7 | Uno 2 |
| BLA | **220Ω resistor** → a free column → wire to Uno **A5** |
| BLK | − rail |

**Resistor colours** (read from the end with the bands closest together):
- 220Ω = red, red, brown (or red, red, black, black on 5-band resistors)
- 1kΩ = brown, black, red (or brown, black, black, brown)

**Contrast:** with VO straight to GND the text is darkest. If you see dark blocks
instead of letters, put a resistor between VO and GND (try 1k, then 2.2k), or use
a 10k potentiometer and turn it until the text is clear.

**Step 4: put the RC522 back** on 7 male-to-female wires (section 3).

### What the LCD shows (Stage 4)

| When | Line 1 | Line 2 |
|---|---|---|
| Waiting | `Campus shuttle` | `KSh 50  Tap card` |
| Paid | `PAID KSh 50` | `Bal: KSh 450` |
| Already paid | `Already paid` | `Bal: KSh 450` |
| Not enough money | `Low balance` | `Has 30 need 50` |
| Unknown card | `Unknown card` | `See conductor` |

| Problem | Fix |
|---|---|
| Top row of solid blocks | Has power, no data: check RS, E, D4–D7 |
| Nothing at all | Check GND and VDD; check contrast (VO) |
| Strange symbols | Two of D4–D7 are swapped |
| Text very faint | No backlight: wire BLA/BLK (4b), or more light |

---

## 5. Power

| Source | Plug into |
|---|---|
| Laptop (now) | USB cable → Uno's square USB port |
| Power bank / phone charger | Same USB cable |
| 9V battery (short demos only) | 9V clip with barrel plug → round black jack |
| Bus 12V | 12V→5V car USB adapter + USB cable (needs a fuse for a real install) |

Use one power source at a time.

---

## 6. Uploading and testing

**Sketches** (each folder has one `.ino` file):

| Folder | What it does |
|---|---|
| `stage1_read_card` | Prints the ID of any card tapped |
| `stage2_lcd` | Shows the tapped card's ID on the LCD |
| `stage3_fare` | Fare system, Serial Monitor + LED |
| `stage4_lcd_fare` | Fare system + LCD (**the current version**) |
| `check_rc522` | Live reader check on the LED |

**Upload from the IDE:** open the `.ino` → Tools → Board → Arduino Uno →
Port `/dev/ttyACM0` → Upload (→ button).

**Upload from the terminal:**
```
arduino --upload --board arduino:avr:uno --port /dev/ttyACM0 bus-fare/stage4_lcd_fare/stage4_lcd_fare.ino
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

**Library needs** (Tools → Manage Libraries): `MFRC522` by GithubCommunity,
`LiquidCrystal` by Arduino.

---

## 7. Shopping list

| Item | Approx. KSh | For |
|---|---|---|
| Male-to-male jumper wires (40-pack) | 100–200 | LCD through the breadboard |
| 10k potentiometer | 30–100 | LCD contrast (optional) |
| Active buzzer | 50–150 | Beep on paid/refused |
| Soldering at a repair shop | 50–100 | Makes the RC522 and LCD connections permanent |
| Power bank (or one you own) | — | Running away from the laptop |

*Prices are rough estimates, not quotes.*
