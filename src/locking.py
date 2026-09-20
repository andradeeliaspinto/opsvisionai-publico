from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path


class PipelineAlreadyRunningError(RuntimeError):
    pass


@contextmanager
def exclusive_file_lock(lock_path, *, job_id, stale_after_seconds=None):
    """O SO libera o lock quando o processo termina.

    stale_after_seconds é aceito por compatibilidade, mas não remove locks ativos.
    """
    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    locked = False
    try:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b" ")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as exc:
            raise PipelineAlreadyRunningError(
                "Outra rotina já detém o lock de escrita do projeto."
            ) from exc
        handle.seek(1)
        handle.truncate()
        handle.write(json.dumps({"job_id": job_id, "pid": os.getpid()}).encode())
        handle.flush()
        yield {"job_id": job_id, "pid": os.getpid()}
    finally:
        if locked:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
