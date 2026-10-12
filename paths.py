"""Discovery and validation of the DLSS 5 Visual Enhancer v15.0 runtime."""
import os
import json
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
CONFIG_FILE = PACKAGE_ROOT / "config.json"
RUNTIME_ENV = "DLSS5_V15_RUNTIME_DIR"

# In v15.0, VE_CLI.exe is in the root of the extracted folder
CLI_NAME = "VE_CLI.exe"

def _read_config() -> dict:
    if not CONFIG_FILE.is_file():
        return {}
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def write_config(runtime_dir: Path) -> Path:
    payload = {"runtime_dir": str(Path(runtime_dir).resolve())}
    CONFIG_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return CONFIG_FILE

def find_cli(override: str = None) -> Path:
    """Locate VE_CLI.exe."""
    config = _read_config()
    candidates = []
    
    if override:
        candidates.append(Path(override))
    
    env_value = os.environ.get(RUNTIME_ENV)
    if env_value:
        candidates.append(Path(env_value))
        
    configured = config.get("runtime_dir")
    if configured:
        candidates.append(Path(configured))
        
    # Default location next to this script
    candidates.append(PACKAGE_ROOT / "runtime")

    for candidate in candidates:
        candidate = candidate.expanduser()
        # Check if it's the folder containing VE_CLI.exe
        cli_path = candidate / CLI_NAME
        if cli_path.is_file():
            return cli_path
        # Or if the candidate IS the exe itself
        if candidate.is_file() and candidate.name == CLI_NAME:
            return candidate

    raise FileNotFoundError(
        f"Could not find {CLI_NAME}. Searched: {candidates}. "
        f"Run install_runtime.py or set {RUNTIME_ENV}."
    )