"""
OpenFileRescue - Package Runner & Universal Launcher.
Launches the Web UI dashboard or Command-Line Interface (CLI).
"""
import sys
import os
import subprocess
import webbrowser
import threading
import time


def launch_web(host: str = "127.0.0.1", port: int = 8765, auto_open: bool = True):
    from openfilerescue.server.server import run_server
    display_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    url = f"http://{display_host}:{port}"

    print(r"""
  ___                   _____ _ _        ____                                
 / _ \ _ __   ___ _ __ |  ___(_) | ___  |  _ \ ___  ___  ___ _   _  ___      
| | | | '_ \ / _ \ '_ \| |_  | | |/ _ \ | |_) / _ \/ __|/ __| | | |/ _ \     
| |_| | |_) |  __/ | | |  _| | | |  __/ |  _ <  __/\__ \ (__| |_| |  __/     
 \___/| .__/ \___|_| |_|_|   |_|_|\___| |_| \_\___||___/\___|\__,_|\___|     
      |_|                                                                    
            OpenFileRescue - Open-Source Data Recovery (100% Free & Unlimited)
    """)
    print(f" [WEB MODE] Starting embedded dashboard at http://{host}:{port}")
    if host in ("0.0.0.0", "::"):
        print(f" Access locally via: {url}")
    print(" Press Ctrl+C in terminal to stop server.\n")

    if auto_open:
        def _open_browser():
            time.sleep(1.0)
            try:
                # If running inside WSL, trigger Windows default browser
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
    args = sys.argv[1:]

    # Check for CLI flags that belong to openfilerescue.cli
    cli_action_flags = {"--cli", "-c", "--scan", "-s", "--list", "-l", "--demo", "--clone", "--dest", "--step", "--org", "--out"}
    has_cli_action = any(arg in cli_action_flags for arg in args)

    # If help requested without --web
    if ("-h" in args or "--help" in args) and not ("--web" in args or "-w" in args):
        from openfilerescue.cli import main as cli_main
        cli_main()
        return

    if has_cli_action and not ("--web" in args or "-w" in args):
        from openfilerescue.cli import main as cli_main
        cli_main()
        return

    # Web UI options from environment or CLI arguments
    host = os.environ.get("OPENFILERESCUE_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("OPENFILERESCUE_PORT", "8765"))
    except ValueError:
        port = 8765

    no_browser = os.environ.get("OPENFILERESCUE_NO_BROWSER", "0").lower() in ("1", "true", "yes")
    if os.path.exists("/.dockerenv"):
        no_browser = True

    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("--host", "-H") and i + 1 < len(args):
            host = args[i + 1]
            i += 2
        elif arg in ("--port", "-p") and i + 1 < len(args):
            try:
                port = int(args[i + 1])
            except ValueError:
                pass
            i += 2
        elif arg in ("--no-browser", "-n"):
            no_browser = True
            i += 1
        elif arg in ("--web", "-w"):
            i += 1
        else:
            i += 1

    launch_web(host=host, port=port, auto_open=not no_browser)


if __name__ == "__main__":
    main()
