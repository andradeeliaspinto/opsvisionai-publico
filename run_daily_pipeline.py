import argparse
from pathlib import Path

from src.operations import run_daily


def main():
    parser = argparse.ArgumentParser(description="Pipeline diário sem retreino automático.")
    parser.add_argument(
        "--config", type=Path, default=Path(__file__).resolve().parent / "config/project.yaml"
    )
    run_daily(parser.parse_args().config)


if __name__ == "__main__":
    main()
