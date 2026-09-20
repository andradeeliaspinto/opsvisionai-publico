import argparse
from pathlib import Path

from src.operations import tracked_operation
from src.retraining import run_retraining


def action(config, logger, details):
    result = run_retraining(config)
    logger.info("Decisão %s: %s", result["decision"], result["reason"])
    return result


def main():
    parser = argparse.ArgumentParser(description="Avalia Challenger; política controla promoção.")
    parser.add_argument(
        "--config", type=Path, default=Path(__file__).resolve().parent / "config/project.yaml"
    )
    tracked_operation(parser.parse_args().config, "RETRAIN", action)


if __name__ == "__main__":
    main()
