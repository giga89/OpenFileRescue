#!/usr/bin/env python3
"""
OpenFileRescue - Universal Launcher.
Launches the Web UI dashboard or Command-Line Interface (CLI).
"""
import sys
import os
import subprocess
import webbrowser
import threading
import time


def launch_web(host: str = "127.0.0.1", port: int = 8765):
    from openfilerescue.server.server import run_server
    url = f"http://{host}:{port}"

    print(r"""
  ___                   _____ _ _        ____                                
 / _ \ _ __   ___ _ __ |  ___(_) | ___  |  _ \ ___  ___  ___ _   _  ___      
| | | | '_ \ / _ \ '_ \| |_  | | |/ _ \ | |_) / _ \/ __|/ __| | | |/ _ \     
| |_| | |_) |  __/ | | |  _| | | |  __/ |  _ <  __/\__ \ (__| |_| |  __/     
 \___/| .__/ \___|_| |_|_|   |_|_|\___| |_| \_\___||___/\___|\__,_|\___|     
      |_|                                                                    
            OpenFileRescue - Open-Source Data Recovery (100% Free & Unlimited)
    """)
    print(f" [WEB MODE] Starting embedded dashboard at {url}")
    print(" Press Ctrl+C in terminal to stop server.\n")

    # Delayed browser auto-launch
    def _open_browser():
        time.sleep(1.0)
        try:
            # If running inside WSL or Windows, trigger Windows default browser
            subprocess.run(["powershell.exe", "-NoProfile", "-Command", f'Start-Process "{url}"'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            try:
                webbrowser.open(url)
            except Exception:
                pass

    threading.Thread(target=_open_browser, daemon=True).start()
    run_server(host=host, port=port)


def main():
    cli_flags = {"--cli", "-c", "--scan", "-s", "--list", "-l", "--demo", "--clone", "--help", "-h", "--org", "--out"}
    has_cli_flag = any(arg in cli_flags for arg in sys.argv[1:])

    if has_cli_flag:
        from openfilerescue.cli import main as cli_main
        cli_main()
    else:
        # Default: Web UI mode
        launch_web()


if __name__ == "__main__":
    main()
