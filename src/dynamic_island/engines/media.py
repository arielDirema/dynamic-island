"""Windows media playback (Spotify, browser, player…) through the SMTC API."""
import asyncio

from PySide6.QtCore import QThread, Signal
from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
)
from winrt.windows.storage.streams import Buffer, InputStreamOptions

from dynamic_island.core.localization import translate as tr


def pretty_app_name(app_id: str) -> str:
    if not app_id:
        return ""
    name = app_id.split("!")[-1]
    name = name.rsplit("\\", 1)[-1]
    if name.lower().endswith(".exe"):
        name = name[:-4]
    known = {
        "msedge": "Edge", "chrome": "Chrome", "spotify": "Spotify",
        "308046b0af4a39cb": "Firefox", "firefox": "Firefox", "vlc": "VLC",
        "opera": "Opera", "brave": "Brave", "app": "",
    }
    low = name.lower()
    if len(name) >= 12 and all(ch in "0123456789abcdef" for ch in low):
        return ""  # opaque internal identifier
    for key, value in known.items():
        if key in low:
            return value
    if "zunemusic" in app_id.lower() or "media" in low:
        return tr("media.player")
    return name[:1].upper() + name[1:]


class MediaWorker(QThread):
    """Poll the current media session every 500 ms in a dedicated asyncio loop."""

    updated = Signal(object)  # dict | None

    def __init__(self):
        super().__init__()
        self.loop = None
        self.manager = None
        self._running = True
        self._key = None
        self._thumb = None
        self._thumb_tries = 0

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._main())

    def stop(self):
        self._running = False
        self.wait(2000)

    async def _main(self):
        while self._running:
            try:
                info = await self._poll()
            except Exception:
                self.manager = None
                info = None
            self.updated.emit(info)
            await asyncio.sleep(0.5)

    async def _read_thumb(self, props):
        if props.thumbnail is None:
            return None
        stream = await props.thumbnail.open_read_async()
        if not stream.size:
            return None
        buf = Buffer(stream.size)
        await stream.read_async(buf, buf.capacity, InputStreamOptions.READ_AHEAD)
        data = bytes(buf)
        return data or None

    async def _poll(self):
        if self.manager is None:
            self.manager = await MediaManager.request_async()
        s = self.manager.get_current_session()
        if s is None:
            self._key = None
            return None

        props = await s.try_get_media_properties_async()
        if not props.title:
            return None
        pb = s.get_playback_info()
        tl = s.get_timeline_properties()

        key = (props.title, props.artist, s.source_app_user_model_id)
        if key != self._key:
            self._key = key
            self._thumb = None
            self._thumb_tries = 0
        # Some apps (Spotify…) send artwork after the title: retry.
        if self._thumb is None and self._thumb_tries < 8:
            self._thumb_tries += 1
            try:
                self._thumb = await self._read_thumb(props)
            except Exception:
                self._thumb = None

        updated_at = None
        try:
            lu = tl.last_updated_time
            if lu is not None and lu.year > 2000:
                updated_at = lu.timestamp()
        except Exception:
            pass

        return {
            "title": props.title,
            "artist": props.artist or props.album_artist or "",
            "app": pretty_app_name(s.source_app_user_model_id),
            "aumid": s.source_app_user_model_id or "",
            "playing": pb.playback_status == PlaybackStatus.PLAYING,
            "position": tl.position.total_seconds(),
            "duration": (tl.end_time - tl.start_time).total_seconds(),
            "updated_at": updated_at,
            "thumb": self._thumb,
        }

    def command(self, name: str, arg=None):
        """name: 'play_pause' | 'next' | 'previous' | 'seek' (arg = secondes)"""
        if self.loop is None:
            return
        method = {
            "play_pause": "try_toggle_play_pause_async",
            "next": "try_skip_next_async",
            "previous": "try_skip_previous_async",
            "seek": "try_change_playback_position_async",
        }[name]

        async def do():
            try:
                if self.manager is None:
                    self.manager = await MediaManager.request_async()
                s = self.manager.get_current_session()
                if s is not None:
                    if name == "seek":
                        await getattr(s, method)(int(arg * 10_000_000))
                    else:
                        await getattr(s, method)()
            except Exception:
                pass

        asyncio.run_coroutine_threadsafe(do(), self.loop)
