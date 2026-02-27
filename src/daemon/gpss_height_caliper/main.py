#!/usr/bin/env python3
import os
import sys
import time
import json
import shlex
import subprocess
from typing import Optional, List

import requests
from evdev import InputDevice, list_devices


############################################
# User-configurable settings (via env vars)
############################################
# If known, set a substring of the device name as shown by evdev (case-insensitive)
CALIPER_NAME_HINT = "Bluetooth Keyboard"
# Optional: known /dev/input/eventX path to force (skips discovery)
CALIPER_EVENT_PATH = os.getenv("CALIPER_EVENT_PATH")  # e.g., "/dev/input/event3"
# Optional: Bluetooth MAC to actively connect via bluetoothctl if not present
CALIPER_MAC = os.getenv("D2:E9:D1:70:F1:4B")  # e.g., "AA:BB:CC:DD:EE:FF"
# How long to try connecting each cycle before backing off (seconds)
CONNECT_TIMEOUT_S = float(os.getenv("CONNECT_TIMEOUT_S", "15"))
# Backoff between connect cycles (seconds)
RETRY_BACKOFF_S = float(os.getenv("RETRY_BACKOFF_S", "5"))
# Verify HTTPS cert on your local server? (set to "0" to disable verification)
VERIFY_TLS = 0

# API endpoint and timeout
API_URL = os.getenv(
    "API_URL",
    "https://192.168.1.89:8000/api/ionic-conductivity/sample-height/"
)
HTTP_TIMEOUT_S = float(os.getenv("HTTP_TIMEOUT_S", "5"))

############################################
# HTTP: update_height(height) - PATCH call
############################################
def update_height(height: float) -> None:
    """
    Sends PATCH { "sample_height": height } to API_URL.
    Adjust auth headers here if needed.
    """
    try:
        # If you need auth: headers = {"Authorization": "Bearer <token>"}
        headers = {"Content-Type": "application/json"}
        payload = {"sample_height": float(height)}
        resp = requests.patch(
            API_URL,
            data=json.dumps(payload),
            headers=headers,
            timeout=HTTP_TIMEOUT_S,
            verify=VERIFY_TLS,
        )
        resp.raise_for_status()
        print(f"[HTTP] PATCH OK: {payload}")
    except requests.exceptions.SSLError as e:
        print(f"[HTTP] SSL error (self-signed cert?). Set VERIFY_TLS=0 to bypass. {e}")
    except Exception as e:
        print(f"[HTTP] PATCH failed: {e}")

############################################
# Helpers for device discovery/connection
############################################
def _name_hints() -> List[str]:
    return [s.strip().lower() for s in CALIPER_NAME_HINT.split(",") if s.strip()]

def find_evdev_device() -> Optional[str]:
    """
    Return path to a suitable /dev/input/event* device or None if not found.
    Heuristics:
      - If CALIPER_EVENT_PATH is set and exists, use it.
      - Else look for a device whose name contains any hint.
    """
    if CALIPER_EVENT_PATH and os.path.exists(CALIPER_EVENT_PATH):
        return CALIPER_EVENT_PATH

    hints = _name_hints()
    for path in list_devices():
        try:
            dev = InputDevice(path)
            name = (dev.name or "").lower()
            if any(h in name for h in hints):
                return path
        except Exception:
            continue
    return None

def try_bt_connect_via_bluetoothctl(mac: str) -> None:
    """
    Best-effort attempt to connect using bluetoothctl (non-blocking).
    """
    try:
        cmd = f"bluetoothctl connect {shlex.quote(mac)}"
        subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=6)
    except Exception:
        pass

############################################
# Read loop: assemble floats from keystrokes
############################################
class DuplicateFloatDetector:
    def __init__(self):
        self.last = None

    def maybe_trigger(self, text: str):
        try:
            val = float(text)
        except ValueError:
            return
        if self.last is not None and val == self.last:
            print(f"[LOG] duplicate float detected: {val} → update_height()")
            update_height(val)
        self.last = val

def read_floats_from_device(dev_path: str):
    """
    Open evdev device, read characters via Keyboard.read_characters(),
    accumulate until Enter, parse float, trigger duplicate detector.
    Returns when device disconnects (OSError) so the caller can re-discover.
    """
    detector = DuplicateFloatDetector()
    buf: List[str] = []

    print(f"[IO] Opening {dev_path} ...")
    dev = InputDevice(dev_path)

    print(f"[IO] Listening on {dev.path} ({dev.name}) — press Ctrl+C to stop.")

    try:
        # Mapping from integer keycodes to characters, for digits, dot, minus, plus and keypad
        key_map = {
            # Digits 0-9
            2: '1', 3: '2', 4: '3', 5: '4', 6: '5', 7: '6', 8: '7', 9: '8', 10: '9', 11: '0',
            # Dot and Minus
            52: '.',       # KEY_DOT
            12: '-',       # KEY_MINUS
            83: '.',       # KEY_KPDOT
            74: '-',       # KEY_KPMINUS
            78: '+',       # KEY_KPPLUS
        }
        ENTER_KEYCODES = {28, 96}  # KEY_ENTER, KEY_KPENTER

        for event in dev.read_loop():
            if event.type == 1 and event.value == 1:  # EV_KEY and key down
                try:
                    key_code = event.code
                    print(f"[IO] key_code: {key_code}")
                    if key_code in ENTER_KEYCODES:
                        line = "".join(buf).strip()
                        buf.clear()
                        if line:
                            # print(f"[DATA] line: {line}")
                            detector.maybe_trigger(line)
                    else:
                        ch = key_map.get(key_code)
                        if ch is None and 2 <= key_code <= 11:
                            # Explicit digits (1-0) as fallback
                            digits = ['1','2','3','4','5','6','7','8','9','0']
                            ch = digits[key_code-2]
                        if ch is not None:
                            buf.append(ch)
                except Exception as e:
                    continue
    except OSError as e:
        # Happens on disconnect (e.g., Bluetooth drop)
        print(f"[IO] Device error/disconnected: {e}")
    finally:
        try:
            dev.close()
        except Exception:
            pass

############################################
# Main control loop
############################################
def main():
    print("[BOOT] Caliper listener starting...")
    print(f"[CFG] Hints={_name_hints()}, MAC={CALIPER_MAC or '-'}, URL={API_URL}, TLS verify={VERIFY_TLS}")

    while True:
        start = time.time()
        dev_path = None

        # Try to connect/find within timeout window
        while (time.time() - start) < CONNECT_TIMEOUT_S and not dev_path:
            if CALIPER_MAC:
                try_bt_connect_via_bluetoothctl(CALIPER_MAC)
            dev_path = find_evdev_device()
            if dev_path:
                break
            time.sleep(0.5)

        if not dev_path:
            print(f"[WAIT] No caliper detected after {CONNECT_TIMEOUT_S:.0f}s. Backing off {RETRY_BACKOFF_S:.0f}s...")
            time.sleep(RETRY_BACKOFF_S)
            continue

        print(f"[OK] Found device: {dev_path}. Entering read loop.")
        # This returns when the device errors/disconnects
        read_floats_from_device(dev_path)
        print("[RETRY] Device lost. Re-entering discovery loop...\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[EXIT] Stopped by user.")

