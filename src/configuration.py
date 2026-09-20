from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_PROJECT_CONFIG = Path("config/project.yaml")


def load_yaml(path: str | Path) -> dict[str, Any]:
    resolved = Path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"Configuração não encontrada: {resolved}")
    data = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Configuração inválida: {resolved}")
    return data


def project_root(config_path: str | Path = DEFAULT_PROJECT_CONFIG) -> Path:
    path = Path(config_path).resolve()
    return path.parent.parent


def project_config(config_path: str | Path = DEFAULT_PROJECT_CONFIG) -> dict[str, Any]:
    return load_yaml(Path(config_path).resolve())


def project_file(
    relative_path: str | Path,
    config_path: str | Path = DEFAULT_PROJECT_CONFIG,
) -> Path:
    return project_root(config_path) / Path(relative_path)


def database_path(config_path: str | Path = DEFAULT_PROJECT_CONFIG) -> Path:
    config = project_config(config_path)
    return project_file(config["serving"]["database_file"], config_path)


def operations_config(config_path: str | Path = DEFAULT_PROJECT_CONFIG) -> dict[str, Any]:
    return load_yaml(project_file("config/operations.yaml", config_path))


def model_policy(config_path: str | Path = DEFAULT_PROJECT_CONFIG) -> dict[str, Any]:
    return load_yaml(project_file("config/model_policy.yaml", config_path))


def alert_policy(config_path: str | Path = DEFAULT_PROJECT_CONFIG) -> dict[str, Any]:
    return load_yaml(project_file("config/alert_thresholds.yaml", config_path))
