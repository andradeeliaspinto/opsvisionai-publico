from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_source(config_path: str | Path = "config/project.yaml") -> Path:
    """Valida o XLSX local e registra os metadados da fonte, sem download."""
    config_path = Path(config_path)
    root = config_path.parent.parent
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    source = config["source"]
    destination = root / source["raw_file"]
    destination.parent.mkdir(parents=True, exist_ok=True)

    if not destination.exists():
        raise FileNotFoundError(
            f"Dataset oficial ausente: {destination}. "
            "Inclua o arquivo fornecido pela atividade em data/raw/LW-DATASET.xlsx."
        )

    observed = file_sha256(destination)
    expected = source["expected_sha256"]
    if observed != expected:
        raise RuntimeError(f"SHA-256 inesperado: {observed}; esperado: {expected}")

    metadata = {
        "dataset": source["name"],
        "publisher": source["publisher"],
        "provenance": source["provenance"],
        "format": source["format"],
        "sheet_name": source["sheet_name"],
        "license": source["license"],
        "local_file": destination.relative_to(root).as_posix(),
        "sha256": observed,
        "validated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "arquivo oficial empacotado e validado",
    }
    metadata_path = destination.parent / "source_metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination


if __name__ == "__main__":
    print(download_source())
