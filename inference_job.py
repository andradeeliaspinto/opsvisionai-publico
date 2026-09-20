from pathlib import Path

from src.operations import run_daily


def main() -> None:
    root = Path(__file__).resolve().parent
    config = root / "config/project.yaml"
    run_daily(config)


if __name__ == "__main__":
    main()
