#!/usr/bin/env python3
"""Pretend Uno, to test the bridge with no hardware (Linux and macOS only).

    python3 fake_uno.py
It prints a port name such as /dev/pts/5. In another terminal run:
    python3 bridge.py --port /dev/pts/5
Then type a card ID here (e.g. E5734107) to tap it. Lines the bridge sends
are printed; LINK is shown once only. Ctrl+C to stop.
"""
import os
import pty
import sys
import threading
import tty


def main():
    master, slave = pty.openpty()
    tty.setraw(slave)
    print(f'Fake Uno is on: {os.ttyname(slave)}')
    print('Start the bridge on that port, then type a card ID to tap it.')
    linked = False
    heard = threading.Event()   # set once the bridge has sent anything

    def from_bridge():
        nonlocal linked
        buffer = b''
        while True:
            buffer += os.read(master, 256)
            heard.set()
            while b'\n' in buffer:
                raw, buffer = buffer.split(b'\n', 1)
                line = raw.decode(errors='replace').strip()
                if line == 'LINK':
                    if not linked:
                        print('<- LINK (server linked; further LINKs hidden)')
                    linked = True
                elif line:
                    print(f'<- {line}')

    def announce():
        # A real Uno restarts and says READY when the bridge opens the port.
        # Here we cannot see the port being opened, so repeat READY until the
        # bridge answers.
        while not heard.wait(1):
            os.write(master, b'READY\n')

    threading.Thread(target=from_bridge, daemon=True).start()
    threading.Thread(target=announce, daemon=True).start()
    try:
        for typed in sys.stdin:
            card = ''.join(c for c in typed.upper() if c in '0123456789ABCDEF')
            if len(card) >= 8:
                os.write(master, f'TAP {card}\n'.encode())
                print(f'-> TAP {card}')
            elif typed.strip():
                print('Type a card ID of at least 8 hex characters, e.g. E5734107')
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
