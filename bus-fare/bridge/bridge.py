#!/usr/bin/env python3
"""Bridge: links the Uno's USB cable to the fare server.

    Uno  <--USB serial, 9600 baud-->  bridge.py  <--HTTP-->  Django server

Run (server must already be running). Each vehicle has its own terminal token
(Django admin -> Vehicles); it tells the server which bus this Uno is on:
    python3 bridge.py --token <token>                   /dev/ttyACM0, http://127.0.0.1:8000
    python3 bridge.py --token <token> --port COM3       Windows
    python3 bridge.py --token <token> --port /dev/ttyACM1 --server http://192.168.1.20:8000
The token can also come from the FARE_TERMINAL_TOKEN environment variable.
Demo data (manage.py seed_demo): demo-terminal-bus-1 and demo-terminal-bus-2.

What it does (protocol: bus-fare/WIRING.md, "Link to the server"):
  * waits for the Uno's READY, then sends it the server's fare
  * every 2 s asks the server for waiting lines (top-ups, fare changes, new
    trip), writes them to the Uno, then sends LINK. If the server does not
    answer, no LINK is sent, so the Uno goes back to standalone by itself.
  * on "TAP <card>" asks the server and answers "RES <result> <fare> <balance>"
  * if the USB cable is pulled out, keeps trying to reconnect
Stop with Ctrl+C.
"""
import argparse
import os
import threading
import time

import requests
import serial

BAUD = 9600
POLL_SECONDS = 2.0       # the Uno wants LINK every 2-3 s
HTTP_TIMEOUT = 1.5       # seconds to wait for the server
REPLY_DEADLINE = 1.8     # the Uno stops waiting for RES after 2 s
READY_WAIT = 10.0        # no READY after this long: assume the Uno was already running
RECONNECT_SECONDS = 2.0


def reason(error):
    """A short description of what went wrong, for the log."""
    if isinstance(error, requests.ConnectionError):
        return 'cannot connect'
    if isinstance(error, requests.Timeout):
        return 'server too slow'
    response = getattr(error, 'response', None)
    if response is not None and response.status_code == 403 and 'terminal_deactivated' in response.text:
        return 'this terminal was DEACTIVATED on the server (reported lost or stolen)'
    if response is not None and response.status_code in (401, 403):
        return 'server refused the terminal token (check --token)'
    return str(error)


class Bridge:
    def __init__(self, port, server, token='', log=print):
        self.port = port                      # an open serial port (or anything with readline/write)
        self.server = server.rstrip('/')
        self.headers = {'Authorization': f'Terminal {token}'} if token else {}
        self.log = log
        self.write_lock = threading.Lock()    # two threads write to the Uno
        self.ready = False                    # True once the Uno has said READY
        self.server_up = None                 # None = not known yet

    # ---------- talking to the Uno ----------
    def send(self, line, quiet=False):
        with self.write_lock:
            self.port.write((line + '\n').encode('ascii', errors='replace'))
        if not quiet:
            self.log(f'  -> Uno: {line}')

    # ---------- talking to the server ----------
    def api(self, method, path, body=None):
        response = requests.request(method, self.server + path, json=body, headers=self.headers,
                                    timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        return response.json()

    def set_server_up(self, up, error=None):
        if up != self.server_up:
            self.log('Server: reachable' if up else f'Server: NOT reachable ({reason(error)}). Uno will go standalone.')
        self.server_up = up

    # ---------- what happens on each line from the Uno ----------
    def on_line(self, line):
        if line == 'READY':
            self.log('Uno: READY')
            self.ready = True
            self.send_fare()
        elif line.startswith('TAP '):
            self.log(f'Uno: {line}')
            self.handle_tap(line[4:].strip())
        # every other line is for people: ignore it

    def send_fare(self):
        """Give the Uno the fare of the trip the server is running."""
        try:
            self.send(f"FARE {self.api('GET', '/api/status/')['fare']}")
        except (requests.RequestException, KeyError, ValueError) as error:
            self.log(f'Could not fetch the fare: {reason(error)}')

    def handle_tap(self, card_uid):
        started = time.monotonic()
        try:
            answer = self.api('POST', '/api/tap/', {'card_uid': card_uid})
            result, fare, balance = answer['result'], int(answer['fare']), int(answer['balance'])
        except (requests.RequestException, KeyError, ValueError) as error:
            # No RES: after 2 s the Uno decides by itself
            self.log(f'  tap not answered: {reason(error)}')
            return
        if time.monotonic() - started > REPLY_DEADLINE:
            # The Uno has already given up. A late RES could be mistaken for
            # the answer to the NEXT card, so it is better not to send it.
            self.log(f'  server answered too late ({result}); not sent')
            return
        if result == 'UNKNOWN':
            # No balance on purpose: the firmware would copy a 0 into its own
            # memory if it happens to know this card.
            self.send('RES UNKNOWN')
        else:
            self.send(f'RES {result} {fare} {balance}')

    # ---------- every 2 seconds ----------
    def poll_once(self):
        if not self.ready:
            return
        try:
            lines = self.api('POST', '/api/terminal/poll/')['lines']
        except (requests.RequestException, KeyError, ValueError) as error:
            self.set_server_up(False, error)
            return                      # no LINK: the Uno notices within 8 s
        self.set_server_up(True)
        for line in lines:
            self.send(line)
        self.send('LINK', quiet=True)

    def poll_loop(self, stop):
        while not stop.is_set():
            try:
                self.poll_once()
            except (serial.SerialException, OSError):
                return                  # cable pulled out: run() will notice too
            stop.wait(POLL_SECONDS)

    # ---------- main loop for one connection ----------
    def run(self, stop):
        opened = time.monotonic()
        poller = threading.Thread(target=self.poll_loop, args=(stop,), daemon=True)
        poller.start()
        while not stop.is_set():
            raw = self.port.readline()          # returns b'' after the port's timeout
            if not self.ready and time.monotonic() - opened > READY_WAIT:
                self.log('No READY seen: assuming the Uno is already running.')
                self.ready = True
                self.send_fare()
            line = raw.decode('ascii', errors='replace').strip()
            if line:
                self.on_line(line)


def main():
    parser = argparse.ArgumentParser(description='Link the Uno fare terminal to the server.')
    parser.add_argument('--port', default='/dev/ttyACM0', help='serial port of the Uno (Windows: COM3)')
    parser.add_argument('--server', default='http://127.0.0.1:8000', help='address of the Django server')
    parser.add_argument('--token', default=os.environ.get('FARE_TERMINAL_TOKEN', ''),
                        help="this vehicle's terminal token (Django admin -> Vehicles)")
    args = parser.parse_args()
    if not args.token:
        parser.error('give this vehicle\'s terminal token: --token <token> (or set FARE_TERMINAL_TOKEN)')

    stop = threading.Event()
    try:
        while True:
            try:
                port = serial.Serial(args.port, BAUD, timeout=0.2)
            except serial.SerialException as error:
                print(f'Cannot open {args.port}: {error}. Trying again...')
                time.sleep(RECONNECT_SECONDS)
                continue
            print(f'Opened {args.port}. Opening the port restarts the Uno; waiting for READY...')
            connection_stop = threading.Event()
            try:
                Bridge(port, args.server, args.token).run(connection_stop)
            except (serial.SerialException, OSError) as error:
                print(f'Lost the Uno: {error}. Trying again...')
            finally:
                connection_stop.set()
                try:
                    port.close()
                except Exception:
                    pass
            time.sleep(RECONNECT_SECONDS)
    except KeyboardInterrupt:
        stop.set()
        print('\nBridge stopped. The Uno goes back to standalone in a few seconds.')


if __name__ == '__main__':
    main()
