"""Settings persistence, backup recovery and concurrent saves."""
import json
import threading

from dynamic_island.core.config.settings import Settings


def test_settings_persist_across_instances(tmp_path):
    path = tmp_path / "settings.json"
    first = Settings(path)
    first.set("binance", {"key": "K", "secret": "S"})
    second = Settings(path)
    assert second["binance"] == {"key": "K", "secret": "S"}
    assert json.loads(path.read_text(encoding="utf-8"))["binance"] == {"key": "K", "secret": "S"}


def test_corrupt_settings_recovers_backup(tmp_path):
    path = tmp_path / "settings.json"
    original = Settings(path)
    original.set("github_token", "ghp_test")
    path.write_text("{not json", encoding="utf-8")
    recovered = Settings(path)
    assert recovered["github_token"] == "ghp_test"
    assert (tmp_path / "settings.json.corrupt").read_text(encoding="utf-8") == "{not json"


def test_corrupt_settings_without_backup_is_preserved(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    settings = Settings(path)
    assert dict(settings) == {}
    settings.set("phone_token", "token")
    assert (tmp_path / "settings.json.corrupt").read_text(encoding="utf-8") == "{not json"
    assert json.loads(path.read_text(encoding="utf-8"))["phone_token"] == "token"


def test_concurrent_saves_are_serialized(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings(path)
    errors = []
    barrier = threading.Barrier(4)

    def worker(index):
        barrier.wait()
        for item in range(15):
            try:
                settings.set(f"k{index}_{item}", item)
            except Exception as exc:
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert len(saved) == 60
    assert len(Settings(path)) == 60
