"""JSON storage and newest-wins synchronization."""
import json

import pytest

from dynamic_island.core.config.settings import settings
from dynamic_island.infrastructure.storage.collection import Collection


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Isolate collections in a temporary synchronization folder."""
    monkeypatch.setitem(settings, "sync_dir", str(tmp_path))
    monkeypatch.setattr(Collection, "_all", [])
    return tmp_path / "DynamicIsland"


def test_add_update_remove_round_trip(store):
    collection = Collection("unit-tasks")
    item = collection.add(title="Première", priority=1)
    assert collection.get(item["id"]) is item
    assert (store / "unit-tasks.json").is_file()

    collection.update(item, title="Modifiée")
    assert collection.get(item["id"])["title"] == "Modifiée"

    collection.remove(item)
    assert collection.get(item["id"]) is None
    assert item["id"] in collection.deleted

    payload = json.loads((store / "unit-tasks.json").read_text(encoding="utf-8"))
    assert item["id"] in payload["deleted"]
    assert payload["items"] == []


def test_reload_applies_tombstones(store):
    collection = Collection("unit-notes")
    item = collection.add(text="à supprimer")
    collection.remove(item)

    reloaded = Collection("unit-notes")
    assert reloaded.items == []
    assert item["id"] in reloaded.deleted


def test_check_sync_merges_newest_item_and_tombstone(store):
    collection = Collection("unit-sync")
    item = collection.add(title="ancienne version")

    remote = {"id": item["id"], "created": item["created"], "mtime": item["mtime"] + 10,
              "title": "version distante"}
    path = store / "unit-sync.json"
    path.write_text(json.dumps({"items": [remote], "deleted": []}), encoding="utf-8")
    collection._mtime = 0
    assert collection.check_sync() is True
    assert collection.get(item["id"])["title"] == "version distante"

    path.write_text(json.dumps({"items": [], "deleted": [item["id"]]}), encoding="utf-8")
    collection._mtime = 0
    assert Collection.sync_all() is True
    assert collection.get(item["id"]) is None


def test_older_remote_item_does_not_win(store):
    collection = Collection("unit-merge")
    item = collection.add(title="récente")
    remote = {"id": item["id"], "created": item["created"], "mtime": item["mtime"] - 10,
              "title": "ancienne"}
    (store / "unit-merge.json").write_text(
        json.dumps({"items": [remote], "deleted": []}), encoding="utf-8"
    )
    collection._mtime = 0
    collection.check_sync()
    assert collection.get(item["id"])["title"] == "récente"
