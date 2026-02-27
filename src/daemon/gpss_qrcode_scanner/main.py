#!/usr/bin/env python3
import os
import time
import json
import re
from traceback import print_exc
from typing import Optional, List, Dict, Any

import requests
from evdev import InputDevice, list_devices

############################################
# User-configurable settings (via env vars)
############################################
# Device name to look for (case-insensitive)
SCANNER_NAME = os.getenv("SCANNER_NAME", "NT USB Keyboard")
# Optional: known /dev/input/eventX path to force (skips discovery)
SCANNER_EVENT_PATH = os.getenv("SCANNER_EVENT_PATH")  # e.g., "/dev/input/event3"
# Maximum startup time to wait for device detection (seconds)
STARTUP_TIMEOUT_S = float(os.getenv("STARTUP_TIMEOUT_S", "10"))
# Verify HTTPS cert on your local server? (set to "0" to disable verification)
VERIFY_TLS = bool(int(os.getenv("VERIFY_TLS", "0")))

# API base and timeout
# Final endpoints used:
#   GET  {API_BASE_URL}/defaults/
#   POST {API_BASE_URL}/measure/
API_BASE_URL = os.getenv(
    "API_BASE_URL",
    "https://192.168.1.89:8000/api/ionic-conductivity"
).rstrip("/")
HTTP_TIMEOUT_S = float(os.getenv("HTTP_TIMEOUT_S", "10"))

DEFAULTS_URL = f"{API_BASE_URL}/defaults/"
MEASURE_URL = f"{API_BASE_URL}/measure/"

############################################
# HTTP helpers
############################################
_session = requests.Session()

def _http_headers() -> Dict[str, str]:
    return {"Content-Type": "application/json"}

def fetch_default_peis_params(force: bool = True) -> Optional[Dict[str, Any]]:
    """
    Fetch peis_params from GET /defaults/.
    Always hits the server (force=True by default) to keep parameters fresh.
    """
    try:
        resp = _session.get(DEFAULTS_URL, headers=_http_headers(),
                            timeout=HTTP_TIMEOUT_S, verify=VERIFY_TLS)
        resp.raise_for_status()
        data = resp.json()
        pp = data.get("peis_params") or {}
        needed = {"initial_frequency", "final_frequency", "frequency_number", "repeat"}
        if not needed.issubset(pp.keys()):
            print(f"[HTTP] /defaults/ missing fields: got {list(pp.keys())}")
            return None
        peis = {
            "initial_frequency": float(pp["initial_frequency"]),
            "final_frequency": float(pp["final_frequency"]),
            "frequency_number": int(pp["frequency_number"]),
            "repeat": int(pp["repeat"]),
        }
        print(f"[HTTP] Fresh peis_params: {peis}")
        return peis
    except requests.exceptions.SSLError as e:
        print(f"[HTTP] SSL error on /defaults/: {e}")
    except Exception as e:
        print(f"[HTTP] Failed to fetch /defaults/: {e}")
    return None

def send_measure(sample_id: str) -> None:
    """
    POST to /measure/ with {"sample_id": sample_id, "peis_params": {...}}
    Fetches peis_params fresh on EVERY submission.
    """
    peis_params = fetch_default_peis_params(force=True)
    if peis_params is None:
        print("[HTTP] Abort: cannot obtain peis_params.")
        return

    payload = {"sample_id": sample_id, "peis_params": peis_params}
    try:
        resp = _session.post(MEASURE_URL, data=json.dumps(payload),
                             headers=_http_headers(), timeout=HTTP_TIMEOUT_S, verify=VERIFY_TLS)
        resp.raise_for_status()
        print(f"[HTTP] POST /measure/ OK: {payload}")
    except requests.exceptions.SSLError as e:
        print(f"[HTTP] SSL error on /measure/: {e}")
    except Exception as e:
        print(f"[HTTP] POST /measure/ failed: {e}")

############################################
# Helpers for device discovery
############################################
def find_evdev_device() -> Optional[str]:
    """
    Return path to a suitable /dev/input/event* device or None if not found.
    Looks for the USB scanner device by name.
    """
    if SCANNER_EVENT_PATH and os.path.exists(SCANNER_EVENT_PATH):
        return SCANNER_EVENT_PATH

    scanner_name_lower = SCANNER_NAME.lower()
    for path in list_devices():
        try:
            dev = InputDevice(path)
            name = (dev.name or "").lower()
            if scanner_name_lower in name:
                return path
        except Exception:
            continue
    return None

############################################
# ObjectId validation
############################################
_OID_RE = re.compile(r"^[A-Fa-f0-9]{24}$")

def is_valid_object_id(text: str) -> bool:
    return bool(_OID_RE.fullmatch(text.strip()))

############################################
# Read loop
############################################
def read_ids_from_device(dev_path: str):
    """
    Open evdev device, accumulate until Enter, validate ObjectId,
    then send POST /measure/.
    """
    buf: List[str] = []
    print(f"[IO] Opening {dev_path} ...")
    dev = InputDevice(dev_path)
    print(f"[IO] Listening on {dev.path} ({dev.name}) — press Ctrl+C to stop.")

    try:
        key_map = {
            2: '1', 3: '2', 4: '3', 5: '4', 6: '5', 7: '6',
            8: '7', 9: '8', 10: '9', 11: '0',
            30: 'a', 31: 's', 32: 'd', 33: 'f', 34: 'g',
            35: 'h', 36: 'j', 37: 'k', 38: 'l', 44: 'z',
            45: 'x', 46: 'c', 47: 'v', 48: 'b', 49: 'n',
            50: 'm', 16: 'q', 17: 'w', 18: 'e', 19: 'r',
            20: 't', 21: 'y', 22: 'u', 23: 'i', 24: 'o', 25: 'p',

        }
        kp_digits = {
            79: '1', 80: '2', 81: '3', 75: '4', 76: '5', 77: '6',
            71: '7', 72: '8', 73: '9', 82: '0'
        }
        key_map.update(kp_digits)

        ENTER_KEYCODES = {28, 96}

        for event in dev.read_loop():
            if event.type == 1 and event.value == 1:  # EV_KEY + key down
                try:
                    key_code = event.code
                    if key_code in ENTER_KEYCODES:
                        raw = "".join(buf).strip()
                        buf.clear()
                        if raw:
                            text = raw.lower()
                            if is_valid_object_id(text):
                                print(f"[DATA] sample_id: {text} → POST /measure/")
                                send_measure(text)  # fetches fresh defaults each time
                            else:
                                print(f"[WARN] Invalid ObjectId: {raw!r}")
                    else:
                        ch = key_map.get(key_code)
                        if ch is None and 2 <= key_code <= 11:
                            digits = ['1','2','3','4','5','6','7','8','9','0']
                            ch = digits[key_code-2]
                        if ch is not None:
                            buf.append(ch)
                except Exception:
                    print_exc()
                    continue
    except OSError as e:
        print(f"[IO] Device error/disconnected: {e}")
    finally:
        try:
            dev.close()
        except Exception:
            pass

############################################
# Main function
############################################
def main():
    print("[BOOT] Scanner listener starting...")
    print(f"[CFG] Scanner={SCANNER_NAME}, BASE={API_BASE_URL}, TLS verify={VERIFY_TLS}")

    # Find the USB scanner device at startup
    print(f"[INIT] Looking for '{SCANNER_NAME}' device...")
    start_time = time.time()
    dev_path = None
    
    while (time.time() - start_time) < STARTUP_TIMEOUT_S and not dev_path:
        dev_path = find_evdev_device()
        if dev_path:
            break
        time.sleep(0.5)
    
    if not dev_path:
        print(f"[ERROR] Could not find '{SCANNER_NAME}' device after {STARTUP_TIMEOUT_S:.0f}s")
        print("[ERROR] Please ensure the USB dongle is connected and try again.")
        return 1

    print(f"[OK] Found device: {dev_path}")
    print("[INFO] Starting continuous listening mode...")
    print("[INFO] Press Ctrl+C to stop.")
    
    # Continuously listen on the device (assume it stays connected)
    read_ids_from_device(dev_path)

if __name__ == "__main__":
    try:
        exit_code = main()
        if exit_code:
            exit(exit_code)
    except KeyboardInterrupt:
        print("\n[EXIT] Stopped by user.")
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        from traceback import print_exc
        print_exc()
        exit(1)
