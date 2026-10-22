"""Checkpoint durability when Windows readers temporarily hold the old file."""
import json
import os
import threading

import pytest

from nde import jobs


@pytest.mark.skipif(os.name != "nt", reason="Windows open handles deny replacement")
def test_checkpoint_waits_for_active_reader(tmp_path, monkeypatch):
    path = tmp_path / "relay-plan.json"
    jobs.save_json(path, {"state": "old"})
    locked = threading.Event()
    replace = os.replace
    errors = []

    def observed_replace(src, dst):
        try:
            return replace(src, dst)
        except PermissionError:
            locked.set()
            raise

    monkeypatch.setattr(jobs.os, "replace", observed_replace)

    def save():
        try:
            jobs.save_json(path, {"state": "new"})
        except Exception as error:
            errors.append(error)

    with path.open("rb") as reader:
        worker = threading.Thread(target=save)
        worker.start()
        assert locked.wait(5), "The real Windows file lock must be observed"
        assert json.load(reader) == {"state": "old"}
    worker.join(5)
    assert not worker.is_alive()
    assert not errors
    assert json.loads(path.read_text(encoding="utf-8")) == {"state": "new"}
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.skipif(os.name != "nt", reason="Windows replacement retry policy")
def test_checkpoint_permanent_denial_preserves_previous_record(tmp_path, monkeypatch):
    path = tmp_path / "relay-plan.json"
    jobs.save_json(path, {"state": "old"})
    attempts = []

    def denied(src, dst):
        attempts.append(src)
        raise PermissionError("locked")

    monkeypatch.setattr(jobs.os, "replace", denied)
    monkeypatch.setattr(jobs.time, "sleep", lambda delay: None)
    with pytest.raises(PermissionError):
        jobs.save_json(path, {"state": "new"})
    assert len(attempts) == 6
    assert len(set(attempts)) == 1
    assert json.loads(path.read_text(encoding="utf-8")) == {"state": "old"}
    assert list(tmp_path.iterdir()) == [path]
