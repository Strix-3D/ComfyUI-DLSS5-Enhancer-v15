"""Fetch and register the DLSS 5 Visual Enhancer v15.0 runtime."""
import argparse
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import PACKAGE_ROOT, write_config

# v15.0 Release URL
RELEASE_URL = "https://github.com/Merserk/dlss5-visual-enhancer/releases/download/v15.0/Visual.Enhancer.v15.0.zip"
RUNTIME_TARGET = PACKAGE_ROOT / "runtime"

NOTICE = """
================================================================================
LICENSE AND REDISTRIBUTION NOTICE
================================================================================

This script will download the DLSS 5 Visual Enhancer v15.0 release (about 693 MB) 
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

def download(url: str, target: Path) -> Path:
    print(f"Downloading {url} (This may take a while, ~693MB)...")
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

def extract(archive_path: Path, target_dir: Path) -> None:
    print(f"Extracting to {target_dir}...")
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        # v15.0 has files at the root of the zip
        archive.extractall(target_dir)
    print("Extraction complete.")

def confirm(auto_yes: bool) -> None:
    if auto_yes:
        return
    answer = input("Do you accept the terms and wish to proceed? [y/N] ").strip().lower()
    if answer not in {"y", "yes"}:
        sys.exit("Installation aborted.")

def main() -> None:
    parser = argparse.ArgumentParser(description="Install DLSS 5 Visual Enhancer v15.0")
    parser.add_argument("--runtime-dir", type=Path, help="Use an existing installation directory.")
    parser.add_argument("--url", default=RELEASE_URL, help="Release archive URL.")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt (for ComfyUI Manager).")
    args = parser.parse_args()

    print(NOTICE)

    if args.runtime_dir:
        cli_path = args.runtime_dir / "VE_CLI.exe"
        if not cli_path.is_file():
            print(f"Error: VE_CLI.exe not found in {args.runtime_dir}")
            sys.exit(1)
        write_config(args.runtime_dir)
        print(f"Registered runtime at {args.runtime_dir}")
        return

    confirm(args.yes)

    with tempfile.TemporaryDirectory(prefix="dlss5_v15-") as workspace:
        archive = download(args.url, Path(workspace) / "release.zip")
        extract(archive, RUNTIME_TARGET)

    # Verify installation
    cli_path = RUNTIME_TARGET / "VE_CLI.exe"
    if not cli_path.is_file():
        print("Error: Installation failed. VE_CLI.exe not found.")
        sys.exit(1)

    write_config(RUNTIME_TARGET)
    print(f"\nSuccess! Runtime installed at {RUNTIME_TARGET}")
    print("Please restart ComfyUI.")

if __name__ == "__main__":
    main()