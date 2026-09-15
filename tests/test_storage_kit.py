"""
Tests for core/storage.py, core/jobs.py, core/ledger.py.

These only need the target project's existing core/config.py and
core/db.py (stdlib sqlite3 + python-dotenv) -- no fastapi/openai/webauthn
required, so this runs even in the offline sandbox that the rest of the
project's test suite is built to tolerate.

Run from the project root after copying this kit's core/*.py and this
file into place:

    python -m pytest tests/test_storage_kit.py -v
    # or, dependency-free:
    python -m unittest tests.test_storage_kit -v
"""
import os
import sys
import unittest
import uuid

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from core import jobs, ledger, storage  # noqa: E402


def _marker() -> str:
    return f"test-{uuid.uuid4().hex[:10]}"


class StorageDedupTests(unittest.TestCase):
    def setUp(self):
        self.category = _marker()
        self._hashes_to_clean: list[str] = []

    def tearDown(self):
        conn = storage.db()
        for h in self._hashes_to_clean:
            row = conn.execute("SELECT local_path FROM blobs WHERE hash=?", (h,)).fetchone()
            if row and row[0] and os.path.exists(row[0]):
                os.remove(row[0])
            conn.execute("DELETE FROM blobs WHERE hash=?", (h,))
        conn.commit()

    def test_identical_bytes_are_deduplicated(self):
        data = b"the quick brown fox jumps over the lazy dog"
        first = storage.store_blob(data, filename="a.txt", category=self.category)
        second = storage.store_blob(data, filename="a-again.txt", category=self.category)
        self._hashes_to_clean.append(first.hash)

        self.assertEqual(first.hash, second.hash)
        self.assertFalse(first.deduplicated)
        self.assertTrue(second.deduplicated)

        stats_by_category = {c["category"]: c for c in storage.stats()["by_category"]}
        self.assertIn(self.category, stats_by_category)
        self.assertEqual(stats_by_category[self.category]["count"], 1)  # not 2

    def test_different_bytes_are_not_deduplicated(self):
        a = storage.store_blob(b"content A", filename="a.txt", category=self.category)
        b = storage.store_blob(b"content B", filename="b.txt", category=self.category)
        self._hashes_to_clean += [a.hash, b.hash]
        self.assertNotEqual(a.hash, b.hash)

    def test_get_blob_bytes_roundtrip(self):
        data = b"roundtrip payload"
        rec = storage.store_blob(data, filename="r.bin", category=self.category)
        self._hashes_to_clean.append(rec.hash)
        self.assertEqual(storage.get_blob_bytes(rec.hash), data)

    def test_eviction_refuses_blobs_without_archive_pointer(self):
        rec = storage.store_blob(b"never archived", filename="n.bin", category=self.category)
        self._hashes_to_clean.append(rec.hash)
        # Force it to look old without an archive pointer.
        conn = storage.db()
        conn.execute("UPDATE blobs SET last_accessed_at=0 WHERE hash=?", (rec.hash,))
        conn.commit()
        results = storage.evict(max_age_days=0, dry_run=False)
        mine = [r for r in results if r["hash"] == rec.hash]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["action"], "skipped:no_archive_pointer")
        # File must still exist locally -- refusing to evict must not delete it.
        self.assertIsNotNone(storage.get_blob_bytes(rec.hash))

    def test_eviction_proceeds_once_archive_pointer_registered(self):
        rec = storage.store_blob(b"archived elsewhere", filename="e.bin", category=self.category)
        self._hashes_to_clean.append(rec.hash)
        ok = storage.register_archive_ref(rec.hash, provider="telegram", file_id="abc123")
        self.assertTrue(ok)
        conn = storage.db()
        conn.execute("UPDATE blobs SET last_accessed_at=0 WHERE hash=?", (rec.hash,))
        conn.commit()
        results = storage.evict(max_age_days=0, dry_run=False)
        mine = [r for r in results if r["hash"] == rec.hash]
        self.assertEqual(mine[0]["action"], "evicted")
        # Now the hot-tier read must come back empty -- it's cold now.
        self.assertIsNone(storage.get_blob_bytes(rec.hash))


class LedgerTests(unittest.TestCase):
    def test_stage_validation(self):
        with self.assertRaises(ValueError):
            ledger.record(actor="owner", stage="NOT_A_STAGE", action="x")

    def test_timeline_groups_by_correlation_id(self):
        cid = ledger.record(actor="owner", stage="KNOW", action="download_pdf")
        ledger.record(actor="owner", stage="ACT", action="download_pdf", correlation_id=cid)
        ledger.record(actor="owner", stage="VERIFY", action="download_pdf", correlation_id=cid, result="ok")
        entries = ledger.timeline(cid)
        self.assertEqual([e.stage for e in entries], ["KNOW", "ACT", "VERIFY"])


class JobQueueTests(unittest.TestCase):
    def test_enqueue_claim_done(self):
        job_id = jobs.enqueue("noop", payload={"x": 1})
        job = jobs.claim_next(kind="noop")
        self.assertIsNotNone(job)
        self.assertEqual(job.id, job_id)
        self.assertEqual(job.status, "running")
        jobs.mark_done(job_id, result={"ok": True})
        self.assertEqual(jobs.get(job_id).status, "done")

    def test_failed_job_retries_until_max_attempts(self):
        job_id = jobs.enqueue("flaky", payload={}, max_attempts=2)
        j = jobs.claim_next(kind="flaky")
        jobs.mark_failed(j.id, "boom 1")
        self.assertEqual(jobs.get(job_id).status, "queued")  # retried
        j2 = jobs.claim_next(kind="flaky")
        jobs.mark_failed(j2.id, "boom 2")
        self.assertEqual(jobs.get(job_id).status, "failed")  # out of attempts

    def test_run_pending_dispatches_to_handler(self):
        jobs.enqueue("echo", payload={"msg": "hi"})
        results = jobs.run_pending({"echo": lambda payload: {"echoed": payload["msg"]}}, max_jobs=5)
        self.assertTrue(any(r["kind"] == "echo" and r["status"] == "done" for r in results))


if __name__ == "__main__":
    unittest.main()

class ArchiveProviderTests(unittest.TestCase):
    def test_provider_registry_is_pluggable_and_honest(self):
        from core import archive
        names = {x["provider"] for x in archive.status()}
        self.assertIn("telegram", names)
        self.assertIn("gmail", names)
        self.assertFalse(any(x["configured"] for x in archive.status()))

    def test_multiple_archive_pointers_allow_eviction(self):
        rec = storage.store_blob(b"multi archive", filename="m.txt", category=_marker())
        try:
            storage.register_archive_object(rec.hash, "telegram", identifier="chat:1", message_id="1", file_id="f1")
            storage.register_archive_object(rec.hash, "gmail", identifier="msg-1", message_id="msg-1")
            self.assertTrue(storage.has_archive_pointer(rec.hash))
            self.assertEqual({x["provider"] for x in storage.archive_objects(rec.hash)}, {"telegram", "gmail"})
        finally:
            conn = storage.db()
            row = conn.execute("SELECT local_path FROM blobs WHERE hash=?", (rec.hash,)).fetchone()
            if row and row[0] and os.path.exists(row[0]): os.remove(row[0])
            conn.execute("DELETE FROM archive_objects WHERE blob_hash=?", (rec.hash,))
            conn.execute("DELETE FROM blobs WHERE hash=?", (rec.hash,))
            conn.commit()
