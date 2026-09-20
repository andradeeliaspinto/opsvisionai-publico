"""Grava arquivos sem apagar a versão anterior antes de terminar a escrita."""

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def atomic_output(destination):
    """O temporário fica na mesma pasta para permitir a troca atômica."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(name)
    try:
        yield temporary
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
