"""
Standalone Bitstream Disk Imager for OpenFileRescue.
Dumps raw sectors from \\\\.\\D: into microsd_backup.img.
"""
import sys
import os
import time

def main():
    src_drive = sys.argv[1] if len(sys.argv) > 1 else r"\\.\D:"
    dst_file = sys.argv[2] if len(sys.argv) > 2 else r"\\wsl.localhost\Ubuntu\home\ubuntu\recupero_foto\microsd_backup.img"
    chunk_size = 4 * 1024 * 1024  # 4 MB
    total_size = 31258738688  # 29.11 GB

    print(f"=== OPENFILERESCUE BITSTREAM IMAGER ===")
    print(f" Source:      {src_drive}")
    print(f" Destination: {dst_file}")
    print(f" Total size:  {total_size / (1024*1024*1024):.2f} GB")
    print(f" Chunk size:  {chunk_size // (1024*1024)} MB")
    print(f" Mode:        READ-ONLY")
    print(f"=======================================")

    start_time = time.time()
    last_print = start_time
    copied = 0
    bad_blocks = 0

    try:
        with open(src_drive, "rb") as src, open(dst_file, "wb") as dst:
            while copied < total_size:
                to_read = min(chunk_size, total_size - copied)
                try:
                    data = src.read(to_read)
                    if not data:
                        break
                except Exception as err:
                    print(f"\n[!] Read error at offset {copied}: {err}. Zero-filling chunk...")
                    data = b"\x00" * to_read
                    bad_blocks += 1

                dst.write(data)
                copied += len(data)

                now = time.time()
                if now - last_print >= 2.0 or copied >= total_size:
                    elapsed = max(0.001, now - start_time)
                    pct = (copied / total_size) * 100.0
                    mb_copied = copied / (1024 * 1024)
                    speed = mb_copied / elapsed
                    rem_mb = (total_size - copied) / (1024 * 1024)
                    eta_sec = rem_mb / max(0.01, speed)
                    eta_m = int(eta_sec // 60)
                    eta_s = int(eta_sec % 60)

                    sys.stdout.write(
                        f"\r[DUMP] {pct:5.1f}% | {mb_copied:7.1f} MB / {total_size/(1024*1024):.0f} MB "
                        f"| {speed:5.1f} MB/s | ETA: {eta_m:02d}m {eta_s:02d}s | Bad: {bad_blocks}"
                    )
                    sys.stdout.flush()
                    last_print = now

        print(f"\n\n[SUCCESS] Clone completed! {copied / (1024*1024*1024):.2f} GB written to {dst_file}")
    except Exception as e:
        print(f"\n[ERROR] Dump failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
