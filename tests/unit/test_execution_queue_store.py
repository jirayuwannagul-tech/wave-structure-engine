import os
import tempfile

from storage.execution_queue_store import ExecutionQueueStore


def test_execution_queue_store_enqueue_dedupe_fetch_mark():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        q = ExecutionQueueStore(db_path=path)
        tid1 = q.enqueue("OPEN_FROM_SIGNAL", {"signal_id": 1}, dedupe_key="open:1")
        assert tid1 is not None
        tid2 = q.enqueue("OPEN_FROM_SIGNAL", {"signal_id": 1}, dedupe_key="open:1")
        assert tid2 is None  # deduped

        ready = q.fetch_ready(limit=10)
        assert len(ready) == 1
        assert int(ready[0]["id"]) == int(tid1)

        q.mark_running(int(tid1))
        q.mark_retry(int(tid1), error="x", backoff_seconds=1.0)
        assert q.count_pending() >= 1
        q.mark_done(int(tid1))
        assert q.count_pending() == 0
    finally:
        os.unlink(path)

