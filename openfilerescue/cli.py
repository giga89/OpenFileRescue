"""
OpenFileRescue - Command Line Interface (CLI).
Enables headless, terminal-based data recovery, interactive drive selection,
real-time ASCII progress bar, and automated batch carving without requiring a web browser.
"""
import sys
import os
import time
import argparse
from typing import Optional

from openfilerescue.core.reader import SafeDiskReader, detect_available_sources, format_size
from openfilerescue.core.carver import FileCarver
from openfilerescue.core.imager import SafeImager
from openfilerescue.core.exporter import FileExporter
from tests.make_test_disk import create_test_image


# ANSI Color Codes for beautiful terminal styling
class Term:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    RED = "\033[31m"
    BG_BLUE = "\033[44m"


def print_banner():
    banner = rf"""{Term.CYAN}{Term.BOLD}
   ____                    ______ _ _       _____                               
  / __ \                  |  ____(_) |     |  __ \                              
 | |  | |_ __   ___ _ __  | |__   _| | ___ | |__) |___  ___  ___ _   _  ___     
 | |  | | '_ \ / _ \ '_ \ |  __| | | |/ _ \|  _  // _ \/ __|/ __| | | |/ _ \    
 | |__| | |_) |  __/ | | || |    | | |  __/| | \ \  __/\__ \ (__| |_| |  __/    
  \____/| .__/ \___|_| |_||_|    |_|_|\___||_|  \_\___||___/\___|\__,_|\___|    
        | |                                                                     
        |_|   {Term.GREEN}Open-Source File & Data Recovery Engine (CLI Edition){Term.RESET}
    """
    print(banner)


def list_sources_cli():
    print(f"\n{Term.BOLD}Scanning for connected drives, storage devices, and disk images...{Term.RESET}\n")
    sources = detect_available_sources()
    if not sources:
        print(f"{Term.YELLOW}No physical drives or images automatically detected.{Term.RESET}")
        print("You can still specify any custom path or image file (e.g. sample.img, D:\\, /dev/sdb).\n")
        return []

    print(f"{Term.BOLD}{'#':<3} {'Type':<15} {'Name':<32} {'Size':<12} {'Path'}{Term.RESET}")
    print("-" * 78)
    for i, s in enumerate(sources, 1):
        print(f"[{i}] {s.source_type:<15} {s.name[:30]:<32} {s.size_formatted:<12} {Term.CYAN}{s.path}{Term.RESET}")
    print()
    return sources


def run_cli_scan(
    source_path: str,
    output_dir: str = "recovered_files",
    organization: str = "by_type",
    sector_step: int = 512,
    max_scan_gb: Optional[float] = None
):
    print(f"\n{Term.BOLD}=== INITIATING SAFE READ-ONLY SCAN ==={Term.RESET}")
    print(f" Source:       {Term.CYAN}{source_path}{Term.RESET}")
    print(f" Output Dir:   {Term.GREEN}{output_dir}{Term.RESET}")
    print(f" Organization: {organization}")
    print(f" Sector Step:  {sector_step} bytes")
    print(f" Safety Mode:  {Term.GREEN}100% STRICT READ-ONLY{Term.RESET}")
    print("=" * 60 + "\n")

    os.makedirs(output_dir, exist_ok=True)

    try:
        reader = SafeDiskReader(source_path, sector_size=sector_step)
    except Exception as e:
        print(f"{Term.RED}[ERROR] Failed to open source: {e}{Term.RESET}")
        return

    exporter = FileExporter(output_dir)
    carver = FileCarver(reader, sector_step=sector_step)

    total_size = reader.size
    if max_scan_gb:
        total_size = min(total_size, int(max_scan_gb * 1024 * 1024 * 1024))

    found_count = 0

    def on_file_found(carved):
        nonlocal found_count
        found_count += 1
        try:
            saved_path = exporter.export_file(carved, reader._file, organization=organization)
            meta = []
            if carved.metadata.get("camera_make"):
                meta.append(f"{carved.metadata['camera_make']} {carved.metadata.get('camera_model','')}".strip())
            if carved.metadata.get("width"):
                meta.append(f"{carved.metadata['width']}x{carved.metadata['height']}")
            if carved.metadata.get("date_taken"):
                meta.append(f"Date: {carved.metadata['date_taken']}")

            meta_str = f" [{', '.join(meta)}]" if meta else ""
            print(f"\n{Term.GREEN}{Term.BOLD}[+] RECOVERED #{found_count:04d}:{Term.RESET} "
                  f"{carved.file_id}{carved.extension} ({format_size(carved.size)}) "
                  f"at LBA 0x{carved.offset:X}{Term.CYAN}{meta_str}{Term.RESET}")
        except Exception as err:
            print(f"\n{Term.RED}[!] Export error: {err}{Term.RESET}")

    def on_progress(stats):
        pct = stats.percent
        mb_scanned = stats.scanned_bytes / (1024 * 1024)
        total_mb = stats.total_bytes / (1024 * 1024)
        speed = stats.bytes_per_second / (1024 * 1024)
        eta_m = int(stats.eta_seconds // 60)
        eta_s = int(stats.eta_seconds % 60)

        # Progress bar (24 chars)
        bar_len = 24
        filled = int((pct / 100.0) * bar_len)
        bar_str = f"{Term.CYAN}{'█' * filled}{Term.DIM}{'░' * (bar_len - filled)}{Term.RESET}"

        sys.stdout.write(
            f"\r{Term.BOLD}[SCAN]{Term.RESET} {pct:5.1f}% |{bar_str}| "
            f"{mb_scanned:7.1f}/{total_mb:.0f} MB | {speed:5.1f} MB/s | "
            f"ETA: {eta_m:02d}m {eta_s:02d}s | {Term.GREEN}Found: {stats.files_found}{Term.RESET} "
        )
        sys.stdout.flush()

    carver.set_callbacks(on_file_found=on_file_found, on_progress=on_progress)

    try:
        carver._scan_loop()
    except KeyboardInterrupt:
        print(f"\n\n{Term.YELLOW}[!] Scan interrupted by user.{Term.RESET}")
        carver.stop()

    print(f"\n\n{Term.BOLD}{'=' * 60}")
    print(f" {Term.GREEN}RECOVERY FINISHED!{Term.RESET}")
    print(f" Total files recovered: {Term.BOLD}{len(carver.discovered_files)}{Term.RESET}")
    print(f" Files saved in:        {Term.CYAN}{os.path.abspath(output_dir)}{Term.RESET}")
    print(f"{Term.BOLD}{'=' * 60}{Term.RESET}\n")

    reader.close()


def run_interactive_wizard():
    print_banner()
    print(f"{Term.BOLD}--- Interactive Recovery Wizard ---{Term.RESET}\n")

    sources = list_sources_cli()

    print("Options:")
    if sources:
        print(" [1..N] Select one of the detected drives above")
    print(" [c]    Enter custom drive letter, device path, or .img file")
    print(" [d]    Create and scan a Demo Test SD Image (No hardware required)")
    print(" [w]    Launch Web Interface (http://127.0.0.1:8765)")
    print(" [q]    Quit\n")

    choice = input("Enter selection: ").strip().lower()

    if choice == "q":
        print("Exiting.")
        sys.exit(0)
    elif choice == "w":
        from openfilerescue.server.server import run_server
        run_server()
        return
    elif choice == "d":
        print(f"\n{Term.CYAN}Generating 15 MB sample microSD test image...{Term.RESET}")
        sample_path = os.path.join(os.getcwd(), "sample_microsd_card.img")
        create_test_image(sample_path, size_mb=15)
        print(f"{Term.GREEN}Demo disk image created: {sample_path}{Term.RESET}")
        target = sample_path
    elif choice == "c":
        target = input("Enter target path (e.g. D:\\, sample.img, /dev/sdb): ").strip()
        if not target:
            print("No path entered. Aborting.")
            return
    else:
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(sources):
                target = sources[idx].path
            else:
                print("Invalid index.")
                return
        except ValueError:
            print("Invalid selection.")
            return

    out_dir = input(f"Output directory [default: recovered_files]: ").strip() or "recovered_files"
    print("\nOrganization mode:")
    print(" [1] By File Type (JPG / PNG / RAW / Video / Docs / Audio)")
    print(" [2] By Camera Model (from EXIF)")
    print(" [3] By Date Taken (Year/Month)")
    print(" [4] Flat (all in one folder)")
    org_choice = input("Choose [1-4, default 1]: ").strip()
    org_map = {"1": "by_type", "2": "by_camera", "3": "by_date", "4": "flat"}
    organization = org_map.get(org_choice, "by_type")

    run_cli_scan(target, output_dir=out_dir, organization=organization)


def main():
    parser = argparse.ArgumentParser(
        description="OpenFileRescue - Open-Source File, Photo & Data Recovery CLI"
    )
    parser.add_argument("--cli", "-c", action="store_true", help="Launch interactive CLI wizard")
    parser.add_argument("--scan", "-s", type=str, help="Path to drive, device, or disk image to scan")
    parser.add_argument("--list", "-l", action="store_true", help="List available drives and disk images")
    parser.add_argument("--out", "-o", type=str, default="recovered_files", help="Output directory for recovered files")
    parser.add_argument("--org", choices=["by_type", "by_camera", "by_date", "flat"], default="by_type", help="File organization mode")
    parser.add_argument("--step", type=int, default=512, help="Sector scanning step in bytes (default: 512)")
    parser.add_argument("--demo", action="store_true", help="Create and scan demo test SD image")
    parser.add_argument("--clone", type=str, help="Source drive to clone into a raw .img file")
    parser.add_argument("--dest", type=str, default="disk_backup.img", help="Destination file for --clone")
    parser.add_argument("--web", "-w", action="store_true", help="Launch Web UI in browser")

    args = parser.parse_args()

    if args.list:
        print_banner()
        list_sources_cli()
        return

    if args.demo:
        print_banner()
        sample_path = os.path.join(os.getcwd(), "sample_microsd_card.img")
        create_test_image(sample_path, size_mb=15)
        run_cli_scan(sample_path, output_dir=args.out, organization=args.org, sector_step=args.step)
        return

    if args.clone:
        print_banner()
        print(f"Cloning {args.clone} -> {args.dest} in strict read-only mode...")
        imager = SafeImager(args.clone, args.dest)
        imager.start(on_progress=lambda pct, b, bad: sys.stdout.write(f"\rCloning: {pct:.1f}% ({format_size(b)}) | Bad: {bad}"))
        if imager._thread:
            imager._thread.join()
        print(f"\nClone completed: {args.dest}")
        return

    if args.scan:
        print_banner()
        run_cli_scan(args.scan, output_dir=args.out, organization=args.org, sector_step=args.step)
        return

    if args.cli:
        run_interactive_wizard()
        return

    # If no arguments provided, launch Web UI or offer wizard
    if args.web or len(sys.argv) == 1:
        # Launch Web UI
        from run import main as run_main
        run_main()
    else:
        run_interactive_wizard()


if __name__ == "__main__":
    main()
