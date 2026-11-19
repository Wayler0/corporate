#!/usr/bin/env python3
"""Change the ESP32 terminal's Wi-Fi (and optionally server/token) over the USB cable.

No upload, no network needed: like adb, it talks straight to the device.
The settings are saved in the terminal's flash and survive power cuts.

    python3 tools/set_wifi.py "VenueWiFi" "their-password"
    python3 tools/set_wifi.py "VenueWiFi" "pw" --server http://192.168.1.20:8000
    python3 tools/set_wifi.py --server http://192.168.1.20:8000      (server only)
    python3 tools/set_wifi.py --token demo-terminal-bus-2            (token only)
    python3 tools/set_wifi.py --show                                 (just show settings)

The port is found by itself (/dev/ttyUSB* or /dev/ttyACM*); use --port to choose.
Opening the port restarts the ESP32; the script waits for it to be READY.
"""
import argparse
import glob
import sys
import time

import serial


def find_port():
    ports = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
    if not ports:
        sys.exit("No terminal found. Is the USB cable plugged in?")
    return ports[0]


def read_until(port, words, timeout):
    """Print the terminal's lines until one contains any of `words`. Returns that line."""
    end = time.time() + timeout
    while time.time() < end:
        line = port.readline().decode(errors="replace").strip()
        if not line:
            continue
        print(f"  terminal: {line}")
        if any(w in line for w in words):
            return line
    return None


def send(port, command, show=None):
    print(f"> {show or command}")
    port.write((command + "\n").encode())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ssid", nargs="?", help="Wi-Fi network name")
    ap.add_argument("password", nargs="?", help="Wi-Fi password")
    ap.add_argument("--server", help="server address, e.g. http://192.168.1.20:8000")
    ap.add_argument("--token", help="this vehicle's terminal token")
    ap.add_argument("--show", action="store_true", help="only show the current settings")
    ap.add_argument("--port", help="serial port (default: found automatically)")
    args = ap.parse_args()

    if args.ssid is not None and args.password is None:
        sys.exit("Give both the network name and the password.")
    if "|" in (args.ssid or ""):
        sys.exit("The network name cannot contain '|'.")
    if not (args.ssid or args.server or args.token or args.show):
        ap.print_help()
        return

    name = args.port or find_port()
    # Open without touching DTR/RTS (that can hold the ESP32 in reset), then
    # pulse RTS once: a clean restart into the normal program.
    port = serial.Serial()
    port.port, port.baudrate, port.timeout = name, 115200, 0.5
    port.dtr = False
    port.rts = False
    port.open()
    port.rts = True
    time.sleep(0.2)
    port.rts = False
    port.reset_input_buffer()
    print(f"Opened {name}. The terminal restarts; waiting for it...")
    if not read_until(port, ["READY"], 30):
        sys.exit("The terminal did not say READY. Is terminal_esp32 uploaded on it?")

    ok = True
    if args.server:
        send(port, f"server {args.server}")
        ok &= (read_until(port, ["SAVED server", "ERROR"], 5) or "").startswith("SAVED")
    if args.token:
        send(port, f"token {args.token}")
        ok &= (read_until(port, ["SAVED token", "ERROR"], 5) or "").startswith("SAVED")
    if args.ssid:
        send(port, f"wifi {args.ssid}|{args.password}", show=f"wifi {args.ssid}|{'*' * len(args.password)}")
        result = read_until(port, ["WIFI OK", "WIFI FAILED", "ERROR"], 25) or ""
        ok &= result.startswith("WIFI OK")
    send(port, "config")
    read_until(port, ["CONFIG"], 5)
    port.close()
    print("Done." if ok else "Saved, but something did not work: see the lines above.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
