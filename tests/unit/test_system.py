"""Night Light registry handling for legacy and short Windows payloads."""
from dynamic_island.services import system


class _FakeKey:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_short_night_light_payload_is_not_written(monkeypatch):
    written = []
    monkeypatch.setattr(system.winreg, "OpenKey", lambda *_args, **_kwargs: _FakeKey())
    monkeypatch.setattr(
        system.winreg, "QueryValueEx",
        lambda *_args, **_kwargs: (b"\x43\x42\x01\x00\x0a\x02\x01\x00\x2a\x2a\x00\x00\x00", 3),
    )
    monkeypatch.setattr(system.winreg, "SetValueEx", lambda *args: written.append(args))
    assert system.set_night_light(True) is False
    assert written == []


def test_legacy_night_light_payload_is_toggled(monkeypatch):
    payload = bytearray(43)
    payload[10:15] = b"\x01\x00\x00\x00\x00"
    payload[18] = 0x13
    written = []
    monkeypatch.setattr(system.winreg, "OpenKey", lambda *_args, **_kwargs: _FakeKey())
    monkeypatch.setattr(system.winreg, "QueryValueEx", lambda *_args, **_kwargs: (bytes(payload), 3))
    monkeypatch.setattr(system.winreg, "SetValueEx",
                        lambda _key, _name, _reserved, _type, value: written.append(value))

    assert system.set_night_light(True) is True
    assert written
    updated = written[0]
    assert updated[18] == 0x15
    assert updated[23:25] == b"\x10\x00"
