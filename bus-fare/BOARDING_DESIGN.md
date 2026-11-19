# Reserved-seat boarding (proposal)

**Status: proposed, not built.** This is the design for how corporate card holders
board at a stage during rush hour. None of it is implemented yet. The current
system only taps and charges a fare per trip (see `PROGRESS.md`).

## Problem

In the morning and evening rush, commuters queue at the stage before they can
board. The wait eats into time staff need at home before the next workday.

## Idea: reserve seats, don't skip the queue

Corporates do not jump the line. Each bus keeps a few seats for card holders,
like business class. Nobody is removed, and a reserved seat nobody claims goes
to the normal queue so the bus still leaves full and fast.

### How it works at the stage

1. **Two lines:** a normal line and a corporate line.
2. **Bookings per route.** Enrolled corporate staff book a route for an evening
   window, so the system knows the expected number, e.g. *Nairobi–Makongeni: 73*.
3. **Per-bus reserved quota.** When a bus is at the stage (e.g. KDA 999F), it is
   given a reserved-seat quota, either:
   - **auto:** `min(SACCO cap, corporates still waiting on this route)`, or
   - **manual:** the SACCO sets it for that bus.
4. **Boarding.** A corporate taps and takes a reserved seat:
   - the route's remaining count drops (73 -> 72),
   - that bus's reserved seats drop (e.g. 15 -> 14).
5. **Fast departure.** When the corporate line is empty or the bus is otherwise
   full, remaining reserved seats are released to the normal line so the bus
   departs full. **The bus never waits for a corporate who is not there.**
6. **SACCO view.** The SACCO sees expected riders per route and per time window,
   so it can dedicate seats by hand and plan how many buses to send.

### The counter the crew sees (example)

```
Route: Nairobi-Makongeni     Expected tonight: 73
This bus: KDA 999F           Reserved: 15   Boarded: 3   Left: 12
```

Each corporate tap decrements "Left" and the route "Expected".

## Why this is fair (the defence)

Not "corporates matter more". The honest line is: **nobody loses a seat.**

- Reserved seats are **added** capacity the operator chooses to sell, like
  business class.
- An unclaimed reserved seat **goes to the normal queue** the moment the bus
  would otherwise leave, so the normal line never waits longer because of it.
- The bus leaves **faster and fuller**, which helps the whole stage move.
- The **operator earns more** per trip.

Do **not** argue that corporate jobs are more important than others; it offends
the queue and the judges.

## Decisions still open

1. **What is the expected count?** Proposed: corporates who *booked* that route
   for this window (not a guess, not a physical count).
2. **What sets the per-bus quota?** Proposed: SACCO cap, system assigns
   `min(cap, waiting)`.
3. **Does an unused booking still pay?** Proposed for the demo: no.
4. **When exactly is a reserved seat released to the normal line?** Proposed:
   when the bus is otherwise full, or the crew presses "release seats".

## What this touches (build estimate)

The terminal firmware barely changes: a corporate card already taps and the
server already knows it is a corporate card. The new logic is mostly **server +
dashboard**:

- **Server:** a booking/expected-count per route and window; a reserved-seat
  quota per trip/vehicle; count corporate taps against it; decrement and release.
- **Crew dashboard:** the counter above, and a "release seats" action.
- **SACCO dashboard:** expected riders per route and window; set a quota per bus.
- **Firmware (optional):** show "Reserved seat" or "Seats full" on the LCD;
  without it, the server still counts and the crew screen still shows it.

## Not in scope yet

- Telling a rider which specific bus to take (needs bus location data).
- Door-to-door pickup at company gates (needs a licensed contract-hire operator;
  a route bus may not leave its route or stop off-stage).
