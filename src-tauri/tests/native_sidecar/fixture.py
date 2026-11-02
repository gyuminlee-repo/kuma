#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Executed by the native shell plugin; run via the native_sidecar Rust target."""

import json
import os
import sys
import time
from pathlib import Path


def main() -> None:
    root = Path(__file__).parent
    mutation = os.environ.get("RS03_MUTATION", "")
    (root / "fixture.pid").write_text(str(os.getpid()), encoding="ascii")
    if mutation != "no-ready":
        print('{"jsonrpc":"2.0","method":"ready","params":{}}', flush=True)
    for line in sys.stdin:
        request = json.loads(line)
        response = {"jsonrpc": "2.0", "id": request["id"]}
        match request["method"]:
            case "ping":
                response["result"] = "broken" if mutation == "wrong-pong" else "pong"
            case "exit":
                # Exit without answering, like a crash mid-request.
                return
            case "stall":
                # Stop reading stdin, like a handler that hangs. The host must
                # still meet its deadlines and be able to kill this process.
                time.sleep(3600)
            case "shutdown":
                if mutation == "ignore-shutdown":
                    continue
                (root / "shutdown.json").write_text(line, encoding="utf-8")
                response["result"] = "bye"
                print(json.dumps(response), flush=True)
                return
            case _:
                if mutation == "die-on-invalid":
                    return
                response["error"] = {"code": -32601, "message": "Method not found"}
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
