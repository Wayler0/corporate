#!/usr/bin/env python3
"""Stand-in for the real backend + bridge, to test the terminal on its own.

It talks to the Uno exactly the way PK's bridge must:
  - sends LINK every 2 s so the terminal knows a server is there
  - answers every "TAP <card>" with "RES <result> <fare> <balance>"

Run:   python3 tools/fake_server.py            (uses /dev/ttyACM0)
       python3 tools/fake_server.py /dev/ttyACM1
While it runs, type:
       topup E5734107 100     add money (the LCD shows it)
       fare 70                change the fare
       trip                   new trip: everyone can pay again
       quit                   stop (the terminal goes back to standalone)
"""
import sys
import threading
import time

import serial

FARE = 50
WALLETS = {"E5734107": 500, "008DEC53": 500, "A1B2C3D4": 200, "11223344": 30}
paid = set()
lock = threading.Lock()


def decide(card):
    """Same four answers the real server gives."""
    if card not in WALLETS:
        return "UNKNOWN", FARE, 0
    if card in paid:
        return "REPEAT", FARE, WALLETS[card]
    if WALLETS[card] < FARE:
        return "LOW", FARE, WALLETS[card]
    WALLETS[card] -= FARE
    paid.add(card)
    return "PAID", FARE, WALLETS[card]


def send(port, text):
    with lock:
        port.write((text + "\n").encode())
    print(f"  -> {text}")


def heartbeat(port, stop):
    while not stop.is_set():
        with lock:
            port.write(b"LINK\n")
        stop.wait(2)


def reader(port, stop):
    while not stop.is_set():
        line = port.readline().decode(errors="replace").strip()
        if not line:
            continue
        print(f"Uno: {line}")
        if line.startswith("TAP "):
            result, fare, balance = decide(line[4:].strip())
            send(port, f"RES {result} {fare} {balance}")


def main():
    global FARE
    name = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM0"
    port = serial.Serial(name, 9600, timeout=0.5)
    print(f"Opened {name}. Opening the port restarts the Uno; waiting for it...")
    stop = threading.Event()
    threading.Thread(target=reader, args=(port, stop), daemon=True).start()
    time.sleep(2)  # the Uno's bootloader ignores anything sent earlier
    threading.Thread(target=heartbeat, args=(port, stop), daemon=True).start()
    print("Fake server running. Tap a card. Commands: topup <card> <KSh>, fare <KSh>, trip, quit")
    try:
        for raw in sys.stdin:
            words = raw.split()
            if not words:
                continue
            if words[0] == "quit":
                break
            if words[0] == "topup" and len(words) == 3 and words[1].upper() in WALLETS:
                card, amount = words[1].upper(), int(words[2])
                WALLETS[card] += amount
                send(port, f"MSG Top-up +{amount}|Bal: KSh {WALLETS[card]}")
            elif words[0] == "fare" and len(words) == 2:
                FARE = int(words[1])
                send(port, f"FARE {FARE}")
            elif words[0] == "trip":
                paid.clear()
                send(port, "trip")
            else:
                print("Commands: topup <card> <KSh>, fare <KSh>, trip, quit")
    except KeyboardInterrupt:
        pass
    stop.set()
    time.sleep(0.6)
    port.close()


if __name__ == "__main__":
    main()
