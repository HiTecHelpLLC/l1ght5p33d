import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from l1ght5p33d.cache import CacheError, WorkflowCache
from l1ght5p33d.examples import browser_workflow


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def days(self, count):
        self.now += count * 86400


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def cache(tmp_path, clock):
    return WorkflowCache(tmp_path / "cache", clock=clock)


def store(
    cache, *, version="0.1.0", provenance=b'{"publisher":"fixture"}', review=None
):
    raw = json.dumps(browser_workflow("http://127.0.0.1:7332")).encode("ascii")
    return cache.store(
        "poster-demo",
        version,
        raw,
        hashlib.sha256(raw).hexdigest(),
        provenance=provenance,
        review=review,
        evidence=b'{"scope":"synthetic"}',
    )


def test_store_exact_pack_and_get_do_not_touch(cache, clock):
    raw_review = b'{ "review": "exact whitespace preserved" }\n'
    item = store(cache, review=raw_review)
    assert Path(item["files"]["review"]).read_bytes() == raw_review
    assert Path(item["files"]["workflow"]) == Path(item["workflow_path"])
    assert item["workflow_id"] == "poster-demo"
    assert item["version"] == "0.1.0"
    assert item["last_used_at"] is None
    clock.days(89)
    assert cache.get(item["key"])["last_used_at"] is None
    assert cache.status()["retention_days"] == 90
    assert cache.find("poster-demo", "0.1.0")[0]["key"] == item["key"]
    assert cache.get(item["key"])["downloaded_at"] == 1000


def test_exact_ninety_day_boundary_and_never_used(cache, clock):
    item = store(cache)
    clock.days(90)
    clock.now -= 0.1
    assert cache.cleanup()["removed"] == []
    clock.now += 0.1
    assert cache.cleanup()["removed"] == [item["key"]]
    assert not Path(item["directory"]).exists()
    assert cache.status()["entries"] == []


def test_actual_use_resets_inactivity_but_duplicate_download_does_not(cache, clock):
    item = store(cache)
    clock.days(85)
    assert store(cache)["downloaded_at"] == 1000
    cache.touch(item["key"])
    used = clock.now
    clock.days(89)
    assert cache.get(item["key"])["last_used_at"] == used
    assert cache.cleanup()["removed"] == []
    clock.days(1)
    assert cache.cleanup()["removed"] == [item["key"]]


@pytest.mark.parametrize("retention", [0, -1, 3651, True, "90"])
def test_retention_bounds(tmp_path, retention):
    with pytest.raises(CacheError, match="1 to 3650"):
        WorkflowCache(tmp_path / "cache", retention_days=retention)


def test_custom_retention(tmp_path, clock):
    cache = WorkflowCache(tmp_path / "cache", retention_days=3, clock=clock)
    item = store(cache)
    clock.days(3)
    assert cache.cleanup()["removed"] == [item["key"]]


def test_pin_and_unpin_protect(cache, clock):
    item = store(cache)
    cache.pin(item["key"])
    clock.days(100)
    assert cache.cleanup()["retained"] == [{"key": item["key"], "reason": "pinned"}]
    assert cache.unpin(item["key"])["pinned"] is False
    assert cache.cleanup()["removed"] == [item["key"]]


def test_active_lease_and_explicit_protection(cache, clock):
    item = store(cache)
    clock.days(100)
    lease = cache.acquire(item["key"])
    assert cache.get(item["key"])["last_used_at"] is None
    assert cache.cleanup()["removed"] == []
    assert cache.release(lease) is True
    assert cache.release(lease) is False
    assert cache.cleanup({item["key"]})["removed"] == []
    assert cache.cleanup()["removed"] == [item["key"]]


def test_edited_workflow_is_retained(cache, clock):
    item = store(cache)
    path = Path(item["workflow_path"])
    path.write_bytes(path.read_bytes() + b" ")
    edited = path.read_bytes()
    clock.days(100)
    result = cache.cleanup()
    assert result["removed"] == []
    assert path.read_bytes() == edited
    assert (
        cache.status()["entries"][0]["integrity"] == "protected_modified_or_unavailable"
    )
    with pytest.raises(CacheError, match="modified"):
        cache.get(item["key"])


def test_changed_metadata_same_size_is_retained(cache, clock):
    item = store(cache)
    path = Path(item["files"]["provenance"])
    path.write_bytes(path.read_bytes().replace(b"fixture", b"changed"))
    clock.days(100)
    assert cache.cleanup()["removed"] == []
    assert b"changed" in path.read_bytes()


def test_untracked_authored_files_prevent_pack_deletion(cache, clock):
    item = store(cache)
    authored = Path(item["directory"]) / "my-authored-workflow.json"
    authored.write_text("personal draft")
    clock.days(100)
    assert cache.cleanup()["removed"] == []
    assert authored.read_text() == "personal draft"
    assert Path(item["workflow_path"]).exists()


def test_unknown_directory_and_run_receipts_are_never_removed(cache, clock, tmp_path):
    item = store(cache)
    unknown = cache.root / "objects" / ("f" * 64)
    unknown.mkdir()
    (unknown / "authored.txt").write_text("keep")
    run_store = tmp_path / "runs" / "interrupted"
    run_store.mkdir(parents=True)
    frozen = run_store / "workflow.json"
    frozen.write_bytes(Path(item["workflow_path"]).read_bytes())
    (run_store / "receipt.json").write_text('{"status":"interrupted"}')
    clock.days(100)
    assert cache.cleanup()["removed"] == [item["key"]]
    assert frozen.exists()
    assert (run_store / "receipt.json").exists()
    assert (unknown / "authored.txt").read_text() == "keep"
    assert cache.status()["untracked_objects_retained"] == ["f" * 64]


def test_refuses_authored_root_and_invalid_keys(tmp_path, cache):
    authored = tmp_path / "authored"
    authored.mkdir()
    (authored / "my.json").write_text("draft")
    with pytest.raises(CacheError, match="empty directory"):
        WorkflowCache(authored)
    with pytest.raises(CacheError, match="cache key"):
        cache.cleanup({"../authored"})
    assert (authored / "my.json").read_text() == "draft"


def test_hard_link_protects_external_file(cache, clock, tmp_path):
    item = store(cache)
    workflow = Path(item["workflow_path"])
    linked = tmp_path / "external.json"
    try:
        os.link(workflow, linked)
    except OSError:
        pytest.skip("Filesystem does not support hard links")
    clock.days(100)
    assert cache.cleanup()["removed"] == []
    assert workflow.exists() and linked.exists()


def test_symlink_pack_is_never_followed(cache, clock, tmp_path):
    item = store(cache)
    workflow = Path(item["workflow_path"])
    outside = tmp_path / "outside.json"
    outside.write_bytes(workflow.read_bytes())
    workflow.unlink()
    try:
        workflow.symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks requires local developer privileges")
    clock.days(100)
    assert cache.cleanup()["removed"] == []
    assert outside.exists()


def test_distinct_reviews_and_versions_get_distinct_exact_keys(cache, clock):
    old = store(cache, review=b'{"review":1}')
    clock.days(1)
    new = store(cache, review=b'{"review":2}')
    other_version = store(cache, version="0.2.0")
    assert len({old["key"], new["key"], other_version["key"]}) == 3
    assert [item["key"] for item in cache.find("poster-demo", "0.1.0")] == [
        new["key"],
        old["key"],
    ]


def test_bad_hash_or_metadata_does_not_create_pack(cache):
    with pytest.raises(CacheError, match="hash"):
        cache.store("poster-demo", "0.1.0", b"{}", "0" * 64, provenance=b"{}")
    with pytest.raises(ValueError):
        store(cache, provenance=b"not-json")
    assert cache.status()["entries"] == []
    assert not list((cache.root / "objects").iterdir())


def test_restart_preserves_usage_and_pin(cache, clock):
    item = store(cache)
    clock.days(5)
    cache.touch(item["key"])
    cache.pin(item["key"])
    restarted = WorkflowCache(cache.root, clock=clock)
    assert restarted.get(item["key"])["last_used_at"] == clock.now
    assert restarted.get(item["key"])["pinned"] is True


def test_live_other_process_lease_blocks_cleanup(cache, clock):
    item = store(cache)
    script = """
import sys
from pathlib import Path
from l1ght5p33d.cache import WorkflowCache
cache = WorkflowCache(Path(sys.argv[1]))
lease = cache.acquire(sys.argv[2])
print('ready', flush=True)
sys.stdin.readline()
cache.release(lease)
"""
    child = subprocess.Popen(
        [sys.executable, "-c", script, str(cache.root), item["key"]],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout.readline().strip() == "ready"
        clock.days(100)
        assert cache.cleanup()["removed"] == []
        child.communicate("release\n", timeout=10)
        assert child.returncode == 0
        assert cache.cleanup()["removed"] == [item["key"]]
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)


def test_dead_process_lease_can_be_reaped(cache, clock, monkeypatch):
    item = store(cache)
    cache.acquire(item["key"])
    monkeypatch.setattr(cache, "_lease_alive", lambda pid, started: False)
    clock.days(100)
    assert cache.cleanup()["removed"] == [item["key"]]
