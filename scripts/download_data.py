import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.acquire_data import download_source

if __name__ == "__main__":
    print(download_source(ROOT / "config/project.yaml"))
