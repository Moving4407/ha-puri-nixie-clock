#!/usr/bin/env python3
"""Read-only probe of a Puri Nixie Clock Local API (SPEC.md phase 0).

Usage: python scripts/probe_clock.py HOST [--port 88] [--delay 0.3]

Only issues HTTP GET requests, one at a time. Never writes. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

# Readable parameters from SPEC.md section 3 (used in 0.1.0).
USED = [
    "brightnessday",
    "brightnessnight",
    "format",
    "leadingzero",
    "dst",
    "timezone",
    "datedisplay",
    "transition",
    "slotmachineperiod",
    "photonled",
    "colonmode",
    "customdatatimeout",
    "firmware",
    "rssi",
    "watchdogevents",
    "currentdisplayedvalue",
    "productid",
    "macaddr",
    "freememory",
    "lastntpsyncmillis",
]

# Readable parameters listed as "not used in 0.1.0".
NOT_USED = [
    "connectivitymode",
    "time",
    "otaenabled",
    "hkconnectionsnumber",
    "largestfreeblockheap",
    "systemfirmware",
    "slotmachinemode",
]

TIMEOUT = 5.0


def get(base: str, param: str) -> dict:
    """GET one parameter and return status, elapsed time and parsed body."""
    url = f"{base}/v1/{param}"
    request = urllib.request.Request(url, method="GET")
    started = time.monotonic()
    result: dict = {"param": param}
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read().decode("utf-8", errors="replace")
            result["http_status"] = response.status
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", errors="replace")
        result["http_status"] = err.code
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        result["error"] = f"{type(err).__name__}: {err}"
        result["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        return result
    result["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    result["raw"] = raw
    try:
        result["body"] = json.loads(raw)
    except json.JSONDecodeError:
        result["body"] = None
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host")
    parser.add_argument("--port", type=int, default=88)
    parser.add_argument("--delay", type=float, default=0.3, help="seconds between requests")
    args = parser.parse_args()

    base = f"http://{args.host}:{args.port}"
    report = {"used": [], "not_used": []}
    for group, names in (("used", USED), ("not_used", NOT_USED)):
        for name in names:
            report[group].append(get(base, name))
            time.sleep(args.delay)

    times = [
        r["elapsed_ms"]
        for g in report.values()
        for r in g
        if "error" not in r and "elapsed_ms" in r
    ]
    report["summary"] = {
        "requests": len(times),
        "avg_ms": round(sum(times) / len(times)) if times else None,
        "max_ms": max(times) if times else None,
    }
    json.dump(report, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
