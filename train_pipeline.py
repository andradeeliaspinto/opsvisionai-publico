from pathlib import Path

from retrain_model import action
from src.operations import tracked_operation


def main() -> None:
    root = Path(__file__).resolve().parent
    config = root / "config/project.yaml"
    tracked_operation(config, "RETRAIN", action)


if __name__ == "__main__":
    main()
