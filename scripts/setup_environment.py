"""Instala o mesmo ambiente local em Linux e Windows, sem ativação do venv."""

from __future__ import annotations

import os
import platform
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENT = ROOT / ".venv"


def main() -> int:
    if sys.version_info[:2] != (3, 12) or struct.calcsize("P") != 8:
        print("Use Python 3.12 de 64 bits para preservar compatibilidade com o modelo.", file=sys.stderr)
        return 1
    executable = ENVIRONMENT / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    environment = dict(os.environ, PYTHONUTF8="1", PYTHONUNBUFFERED="1")
    try:
        if not ENVIRONMENT.exists():
            print("[1/4] Criando .venv...", flush=True)
            subprocess.run([sys.executable, "-m", "venv", str(ENVIRONMENT)], check=True)
        elif not executable.is_file():
            raise RuntimeError("A pasta .venv existente pertence a outro sistema ou esta incompleta. Renomeie-a e repita a instalacao.")
        else:
            print("[1/4] Verificando .venv existente...", flush=True)
        subprocess.run(
            [str(executable), "-c", "import sys, struct; sys.exit(0 if sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8 else 1)"],
            check=True,
        )
        for number, description, arguments in [
            (2, "Atualizando pip", ["install", "--upgrade", "pip"]),
            (3, "Instalando dependencias", ["install", "--only-binary=:all:", "-r", str(ROOT / "requirements.txt")]),
            (4, "Verificando conflitos", ["check"]),
        ]:
            print(f"[{number}/4] {description}...", flush=True)
            subprocess.run([str(executable), "-X", "utf8", "-m", "pip", *arguments], cwd=ROOT, env=environment, check=True)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Instalacao interrompida: {exc}", file=sys.stderr)
        print("Confira Python 3.12/venv, conexao com o indice de pacotes e permissoes da pasta.", file=sys.stderr)
        return 1
    print(f"Ambiente pronto: {platform.system()}, Python 3.12, 64 bits.")
    print("Use o Python da pasta .venv para executar os comandos do README.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
