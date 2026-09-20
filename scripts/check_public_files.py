"""Verifica os bytes que serao publicados. Nao envia arquivos ao GitHub."""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {
    'README.md', 'PRIVACY.md', '.gitignore', '.gitattributes',
    'requirements.txt', 'requirements-validated.txt', 'requirements-lock.txt',
    'app.py', 'run_daily_pipeline.py', 'run_pipeline.py', 'inference_job.py',
    'retrain_model.py', 'train_pipeline.py', 'manage_operations.py', 'validate_project.py',
}
ASSET_HASHES = {'assets/opsvisionai_logo_transparent.png': 'fe2c76de08229639ef26fe41ec21cba14f55fdedd7eec258eaa8816016a636c8', 'assets/opsvisionai_streamlit_icon_512.png': '8f3d6a983d488177cd03650bd56505e37961ab7b4907c44a718e7d97211ed86a', 'assets/opsvisionai_symbol_watermark_16pct.png': 'e049ae665a583a0e067fca3470764de84e56630ffcf056e4ac18dd2dd1bcaa50'}
ALLOWED_EXTENSIONS = {
    'src': {'.py', '.md'}, 'scripts': {'.py', '.sh', '.bat'},
    'tests': {'.py', '.md'}, 'config': {'.yaml', '.example'},
    'docs': {'.md', '.sql'},
}
SKIP_DIRECTORIES = {'.git', '.venv', 'venv', 'env', '__pycache__', '.pytest_cache', '.ruff_cache'}
SENSITIVE_PATTERNS = [
    ('chave privada', re.compile(rb'-----BEGIN [A-Z ]*PRIVATE KEY-----')),
    ('token GitHub', re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b')),
    ('credencial em URL', re.compile(rb'https?://[^/\s:]+:[^/@\s]+@')),
    ('identificador de incidente', re.compile(rb'\bINC[0-9]{5,}\b')),
]


def allowed_path(name: str) -> bool:
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name:
        return False
    if len(path.parts) == 1:
        return name in ROOT_FILES
    if name in {'.streamlit/config.toml', 'assets/README.md', 'data/README.md', 'models/README.md', 'evidence/README.md'}:
        return True
    if name in ASSET_HASHES:
        return True
    return path.parts[0] in ALLOWED_EXTENSIONS and path.suffix in ALLOWED_EXTENSIONS[path.parts[0]]


def check_blob(name: str, content: bytes, *, symlink: bool = False) -> list[str]:
    if symlink:
        return ['links simbolicos/submodulos nao sao permitidos nesta entrega']
    if not allowed_path(name):
        return ['arquivo fora da lista publica permitida']
    if name in ASSET_HASHES:
        return [] if hashlib.sha256(content).hexdigest() == ASSET_HASHES[name] else ['asset alterado; exige revisao manual']
    if b'\0' in content:
        return ['conteudo binario em arquivo textual']
    if len(content) > 2_000_000:
        return ['arquivo textual maior que o limite de revisao']
    try:
        content.decode('utf-8')
    except UnicodeDecodeError:
        return ['conteudo binario ou texto sem UTF-8']
    return [label for label, pattern in SENSITIVE_PATTERNS if pattern.search(content)]


def staged_files():
    result = subprocess.run(['git', 'ls-files', '--stage', '-z'], cwd=ROOT, check=True, capture_output=True)
    for record in result.stdout.split(b'\0'):
        if not record:
            continue
        metadata, raw_name = record.split(b'\t', 1)
        mode, object_id, stage = metadata.decode('ascii').split()
        if stage != '0':
            raise RuntimeError('Existem conflitos no indice Git; resolva antes de publicar.')
        name = raw_name.decode('utf-8')
        # Le o blob do INDEX, nao uma versao diferente presente no diretorio.
        content = subprocess.run(['git', 'cat-file', 'blob', object_id], cwd=ROOT, check=True, capture_output=True).stdout
        yield name, content, mode not in {'100644', '100755'}


def worktree_files():
    for folder, directories, names in os.walk(ROOT):
        for name in list(directories):
            path = Path(folder) / name
            if name in SKIP_DIRECTORIES:
                directories.remove(name)
            elif path.is_symlink():
                directories.remove(name)
                yield path.relative_to(ROOT).as_posix(), b'', True
        for name in names:
            path = Path(folder) / name
            yield path.relative_to(ROOT).as_posix(), b'' if path.is_symlink() else path.read_bytes(), path.is_symlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--staged', action='store_true', help='Verifica todos os arquivos do indice Git (padrao).')
    group.add_argument('--worktree', action='store_true', help='Verifica a pasta extraida, antes de git init.')
    args = parser.parse_args()
    count, failures = 0, []
    try:
        for name, content, symlink in (worktree_files() if args.worktree else staged_files()):
            count += 1
            failures.extend(f'{name}: {reason}' for reason in check_blob(name, content, symlink=symlink))
    except (OSError, RuntimeError, UnicodeError, subprocess.CalledProcessError) as exc:
        print(f'Verificacao interrompida: {exc}', file=sys.stderr)
        return 2
    if not count:
        failures.append('Nenhum arquivo encontrado. Execute git add . antes da verificacao --staged.')
    if failures:
        print('BLOQUEADO:\n' + '\n'.join(failures), file=sys.stderr)
        return 1
    print(f'APROVADO: {count} arquivos verificados. Revise tambem git diff --cached antes do commit.')
    print('Limite: esta verificacao nao examina historico Git nem garante anonimato de texto livre.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
