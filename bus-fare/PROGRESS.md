# Bus Fare Terminal: Progress Log

A contactless fare terminal for Kenyan PSVs (matatus/buses), inspired by German
tap-to-pay ticketing. Built on an Arduino Uno for a competition demo.

Wiring and testing instructions: [`WIRING.md`](WIRING.md).

---

## Where we are (14 Nov 2026)

| Part | Status |
|---|---|
| Card reader (RC522) | ✅ Working, header soldered |
| LCD 16×2 with I2C backpack | ✅ Working |
| RGB LED (green/yellow/red) | ✅ Working |
| Speaker beeps | ✅ Working (quiet; louder in a box) |
| Fares, once-per-trip check, balances saved through power cuts | ✅ Tested on hardware |
| Link to laptop server over USB | ✅ Tested with `tools/fake_server.py` |
| Automatic fallback when the server goes away | ✅ Tested |
| GSM module (SIM800C) | ✅ Answers commands; no SIM, no antenna yet |
| Real backend server (PK) | ⏳ Not started on hardware |
| Live dashboard (Kim) | ⏳ Depends on the server |
| Neat build (box or flat board) | ⏳ Planned, see `WIRING.md` section 8 |

**The terminal firmware for the demo is `terminal_mvp`.** It runs on its own, and
links to the server automatically when the laptop bridge is running.

## Team

| Who | Part |
|---|---|
| Solomon | Hardware and terminal firmware |
| PK | Backend: server, database, USB serial bridge |
| Kim | Dashboard |
| (one more) | Pitch |

## Decisions

- **Arduino Uno only for the demo.** ESP32 (Wi-Fi) and GSM are roadmap items.
- **Fixed fare per route** (example routes in the code; real fares still to set).
- **Each card pays once per trip.** A new trip starts with the `trip` command or a
  route change. (Chosen over a time window.)
- **Server link over the laptop's USB cable**, so the demo does not depend on Wi-Fi
  or a SIM. In online mode the **server's balance is the real one**; the Uno copies
  it so offline mode carries on from the same number.
- **Serial protocol** (for PK): Uno sends `TAP <card>`; server answers
  `RES <PAID|REPEAT|LOW|UNKNOWN> <fare> <balance>` and sends `LINK` every 2 s.
  Full table in `WIRING.md` section 6.
- Security note: card-ID-only payment is fine for a demo, **not** for real money.

---

## Log

### 11 Nov: Stages 1–3
- Kit identified from photos: Uno R3 clone, RC522 reader (pins not soldered),
  white card + blue fob, 16×2 LCD (no backpack), RGB LED module, breadboard,
  ~10 male-to-female jumpers.
- **Stage 1** (`stage1_read_card`): read card IDs. A typed ID works as a
  "simulated tap", so work could continue without the reader.
- **Stage 2** (`stage2_lcd`): LCD sketch, blocked at first because the LCD pins
  were not soldered.
- **Stage 3** (`stage3_fare`): wallets in EEPROM, fixed fare, once-per-trip,
  RGB LED results. **Passed the full test on the real Uno.**
- Real card IDs read: white card `E5734107`, blue fob `008DEC53`.
- Reader dropouts traced to **a jumper with a bad tip at the Uno end**; swapping
  the wire fixed it. Added `check_rc522` (reader status on the LED).
- LED module plugged straight into A0–A3 (A3 used as GND) to save wires.

### 12 Nov: Stage 4 and the manual
- **Stage 4** (`stage4_lcd_fare`): Stage 3 plus the LCD wired in 4-bit mode
  (no backpack). **Working**: every LCD message and LED colour confirmed.
- Wrote `WIRING.md`.

### 13 Nov: I2C backpack, plan for the competition
- Got a PCF8574 I2C backpack: the LCD now needs 4 wires instead of 10+.
  **Stage 5** (`stage5_i2c_lcd_fare`) written.
- An ESP32 and a SIM800L-type GSM module were lent to the team.
- Agreed the competition plan: stay on the Uno, link to the server over USB,
  keep ESP32/GSM/M-Pesa as roadmap.
- Backpack soldered to the LCD (on the front, like a flap). Checked from photos:
  pin 1 meets pin 1, electrically correct.

### 14 Nov: Full terminal working on hardware
- Wrote `terminal_mvp` (demo firmware) and `tools/fake_server.py` (stand-in
  server), plus `check_lcd`.
- **LCD:** found at address 0x27 but blank. Fix: **turned the contrast screw
  about 90°**.
- **Reader** reconnected; both cards read. RC522 header then **soldered**.
- **Speaker** added on pin 8 through 220 Ω. Volume was low, so the beeps were moved
  to ~3 kHz (where small speakers are loudest), told apart by pattern:
  1 beep paid · 2 beeps already paid · 3 short + 1 long refused.
- ⚠️ **A stray speaker wire froze the Uno** (uploads failed: "programmer is not
  responding"). Fixed by rewiring and replugging. Across that freeze both cards
  lost one KSh 50 charge. Balances were then checked to survive both a reset and a
  re-upload, so the likely cause is the short.
- After replugging, the board's port changed from `ttyACM0` to `ttyACM1`.
  `fake_server.py` now finds the port by itself.
- **Standalone test passed:** new trip → PAID KSh 50, repeat → "Already paid",
  card and fob tracked separately.
- **Server link test passed:** `*` shown on the LCD when linked; taps answered
  PAID/REPEAT by the server; a top-up appeared on the LCD without a tap; stopping
  the server removed the `*` and the terminal carried on alone.
- **GSM module** identified as a **SIM800C GSM/GPRS board** (5V, level-shifted).
  It did not answer at first: the chip **needs a power-on pulse** (bridge **PWX** to
  GND for 2 s). After that: `AT` → OK, `SIM800 R14.18`, signal 8/31 without an
  antenna, supply 3867 mV. Added `check_sim800l`.
- No antenna came with the GSM module: **emailed Kim** to ask.
- Manual updated: soldered reader, tested speaker, server link, neat-build plan,
  GSM section.
- Pushing to GitHub needs a token (passwords are no longer accepted).

---

## Open items

| Item | Who | Notes |
|---|---|---|
| Real server speaking the serial protocol | PK | `tools/fake_server.py` is the working example |
| Dashboard on the server's live feed | Kim | |
| Neat build: flat board or box | Solomon | `WIRING.md` section 8; needs ~20 longer jumpers |
| Reset balances to round numbers before the demo | Solomon | `reset` command |
| Real route fares | Team | Example fares in `terminal_mvp` |
| GSM antenna (IPEX/u.FL) | Kim asked | |
| SIM card + separate 5V 2A supply for GSM | Later | Roadmap; SIM800 is 2G only |
| Pin in PWX → Uno pin 4 (auto power-on for GSM) | Later | |
| Competition date | Team | Not yet known |
