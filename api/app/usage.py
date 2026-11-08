"""Traçage de l'usage par utilisateur.

Les écritures sont regroupées par un thread dédié (insertion en lot toutes
les secondes) pour ne pas ajouter une transaction SQL à chaque requête.
"""
from __future__ import annotations

import logging
import queue
import threading

from app.db import SessionLocal, UsageLog

log = logging.getLogger(__name__)


class UsageRecorder:
    def __init__(self, flush_interval: float = 1.0, max_batch: int = 500):
        self.q: queue.Queue = queue.Queue(maxsize=50_000)
        self.flush_interval, self.max_batch = flush_interval, max_batch
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="usage-recorder", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def record(self, **row) -> None:
        try:
            self.q.put_nowait(row)
        except queue.Full:
            log.warning("File d'usage pleine : événement ignoré")

    def flush(self) -> int:
        rows = []
        while len(rows) < self.max_batch:
            try:
                rows.append(self.q.get_nowait())
            except queue.Empty:
                break
        if rows:
            try:
                with SessionLocal() as db:
                    db.add_all([UsageLog(**r) for r in rows])
                    db.commit()
            except Exception as exc:
                log.error("Échec d'écriture de l'usage (%d lignes) : %s", len(rows), exc)
        return len(rows)

    def _run(self) -> None:
        while not self._stop.wait(self.flush_interval):
            while self.flush() == self.max_batch:
                pass

    def stop(self) -> None:
        self._stop.set()
        while self.flush():
            pass


recorder = UsageRecorder()
