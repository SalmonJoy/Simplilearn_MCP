"""Run all five local apps; Ctrl+C shuts down the children."""

import subprocess
import sys
import time
from settings import ROOT

APPS = [
    ("HRMS", 8001),
    ("Inventory_management", 8002),
    ("MCP_server", 8003),
    ("AI_chat_assistant", 8004),
    ("AI_dashboard_generation", 8005),
]


def main():
    processes = []
    try:
        for package, port in APPS:
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        f"{package}.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(port),
                    ],
                    cwd=ROOT,
                )
            )
        print(
            "Chat: http://127.0.0.1:8004 | Dashboard: http://127.0.0.1:8005", flush=True
        )
        while True:
            if any(process.poll() is not None for process in processes):
                raise SystemExit(
                    "An application exited. Check the startup error above."
                )
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
