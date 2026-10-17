"""Fetch and register the DLSS 5 Visual Enhancer v16.5 runtime."""
import argparse
import hashlib
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import PACKAGE_ROOT, write_config

# v16.5 Release URL and SHA-256 hash
RELEASE_URL = "https://github.com/Merserk/dlss5-visual-enhancer/releases/download/v16.5/Visual.Enhancer.v16.5.zip"
RELEASE_SHA256 = "23539866bae168613e89f9bfa426f7a60489a199b23409061b6ae4179a793e37"
RUNTIME_TARGET = PACKAGE_ROOT / "runtime"

NOTICE = """
================================================================================
LICENSE AND REDISTRIBUTION NOTICE
================================================================================

This script will download the DLSS 5 Visual Enhancer v16.5 release (approx. 700 MB) 
and extract its runtime components into your ComfyUI custom_nodes folder.

The downloaded archive contains third-party binaries that are NOT owned by this 
node pack. They include:

  Visual Enhancer.exe / VE_CLI.exe   Merserk Source License
  nvngx_dlss.dll                     NVIDIA DLSS Super Resolution (Proprietary)
  nvngx_dlssg.dll                    NVIDIA DLSS Frame Generation (Proprietary)
  nvngx_dlssnr.dll                   NVIDIA DLSS Neural Rendering (Proprietary)
  nvngx_vsr.dll / nvngx_truehdr.dll  NVIDIA RTX Video (Proprietary)
  ffmpeg.exe / ffprobe.exe           FFmpeg (GPLv3)
  mpv.exe                            mpv media player (GPLv2+)
  yt-dlp.exe                         yt-dlp (Unlicense)

These files are neither owned nor redistributed by this node pack. By proceeding, 
you agree to install only components you are authorized to use, under the terms 
permitted by their respective licenses. 

This project is not affiliated with NVIDIA, Merserk, ReShade, RenoDX, or FFmpeg.
================================================================================
"""

def calculate_sha256(file_path: Path) -> str:
    """Calculate SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(block)
    return sha256_hash.hexdigest()

def download(url: str, target: Path) -> Path:
    print(f"Downloading {url} (This may take a while, ~700MB)...")
    with urllib.request.urlopen(url) as response, target.open("wb") as sink:
        total = int(response.headers.get("Content-Length") or 0)
        received = 0
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            sink.write(block)
            received += len(block)
            if total:
                percent = received * 100 // total
                print(f"\r{percent:3d}% {received/1e6:8.1f} / {total/1e6:.1f} MB", end="")
    print("\nDownload complete.")
    return target

def verify_hash(archive_path: Path, expected_hash: str) -> bool:
    """Verify SHA-256 hash of downloaded file."""
    if not expected_hash or expected_hash == "YOUR_SHA256_HASH_HERE":
        print("WARNING: No SHA-256 hash configured. Skipping verification.")
        return False
    print("Verifying file integrity...")
    actual_hash = calculate_sha256(archive_path)
    if actual_hash.lower() != expected_hash.lower():
        print(f"ERROR: SHA-256 mismatch!")
        print(f"  Expected: {expected_hash}")
        print(f"  Actual:   {actual_hash}")
        return False
    print("File integrity verified.")
    return True

def extract(archive_path: Path, target_dir: Path) -> None:
    print(f"Extracting to {target_dir}...")
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(target_dir)
    print("Extraction complete.")

def confirm(auto_yes: bool) -> None:
    if auto_yes:
        return
    if not sys.stdin.isatty():
        # Launched by ComfyUI Manager or another non-interactive tool
        print("\nNon-interactive environment detected (e.g. ComfyUI Manager).")
        print("Automatic download skipped so the license can be reviewed properly.")
        print("To accept the terms and install the runtime, run this script manually once:")
        print("  .\\python_embeded\\python.exe ComfyUI\\custom_nodes\\ComfyUI-DLSS5-Enhancer-v15\\install.py")
        sys.exit(0)
    answer = input("Do you accept the terms and wish to proceed? [y/N] ").strip().lower()
    if answer not in {"y", "yes"}:
        sys.exit("Installation aborted.")

def main() -> None:
    parser = argparse.ArgumentParser(description="Install DLSS 5 Visual Enhancer v16.5")
    parser.add_argument("--runtime-dir", type=Path, help="Use an existing installation directory.")
    parser.add_argument("--url", default=RELEASE_URL, help="Release archive URL.")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt.")
    args = parser.parse_args()

    if args.runtime_dir:
        cli_path = args.runtime_dir / "VE_CLI.exe"
        if not cli_path.is_file():
            print(f"Error: VE_CLI.exe not found in {args.runtime_dir}")
            sys.exit(1)
        write_config(args.runtime_dir)
        print(f"Registered runtime at {args.runtime_dir}")
        return

    # If the runtime is already installed, do nothing (fixes Manager update hangs)
    if (RUNTIME_TARGET / "VE_CLI.exe").is_file():
        print(f"[DLSS5] Runtime already installed at {RUNTIME_TARGET}. Nothing to do.")
        write_config(RUNTIME_TARGET)
        return

    print(NOTICE)
    confirm(args.yes)

    with tempfile.TemporaryDirectory(prefix="dlss5_v16-") as workspace:
        archive = download(args.url, Path(workspace) / "release.zip")

        if not verify_hash(archive, RELEASE_SHA256):
            print("ERROR: Downloaded file failed integrity check. Aborting installation.")
            sys.exit(1)

        extract(archive, RUNTIME_TARGET)

    cli_path = RUNTIME_TARGET / "VE_CLI.exe"
    if not cli_path.is_file():
        print("Error: Installation failed. VE_CLI.exe not found.")
        sys.exit(1)

    write_config(RUNTIME_TARGET)
    print(f"\nSuccess! Runtime installed at {RUNTIME_TARGET}")
    print("Please restart ComfyUI.")

if __name__ == "__main__":
    main()
