"""Entry point for the installed application (DynamicIsland.exe).

- No argument: start the watchdog, which launches the island and restarts it after a crash.
- --island: the island itself (started by the watchdog).
- --selftest: verify every component and write a report to %TEMP%\\DynamicIsland-selftest.txt.
From source, `pythonw src\\main.py` (or start.bat) remains supported."""
import sys


def selftest():
    import os
    import tempfile
    import traceback
    results = []

    def check(name, fn):
        try:
            info = fn()
            results.append(f"OK    {name}" + (f" — {info}" if info else ""))
        except Exception as exc:
            results.append(f"FAIL  {name} — {type(exc).__name__}: {exc}")
            results.append("      " + traceback.format_exc().strip().splitlines()[-1])

    def media():
        import asyncio
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as M

        async def get():
            return await M.request_async()
        manager = asyncio.run(get())
        session = manager.get_current_session()
        return f"session: {session.source_app_user_model_id if session else 'none'}"

    def audio():
        from pycaw.pycaw import AudioUtilities
        speakers = AudioUtilities.GetSpeakers()
        return f"{speakers.FriendlyName} · volume {speakers.EndpointVolume.GetMasterVolumeLevelScalar():.2f}"

    def uia():
        import comtypes.client
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient  # noqa: F401
        return "UI Automation module generated"

    def radios():
        import asyncio
        from winrt.windows.devices.radios import Radio

        async def get():
            return await Radio.get_radios_async()
        return ", ".join(f"{radio.name}={int(radio.state)}" for radio in asyncio.run(get()))

    def bluetooth():
        import asyncio
        from winrt.windows.devices.bluetooth import BluetoothDevice
        from winrt.windows.devices.enumeration import DeviceInformation

        async def count():
            return len(await DeviceInformation.find_all_async_aqs_filter(
                BluetoothDevice.get_device_selector_from_pairing_state(True)))
        return f"{asyncio.run(count())} paired device(s)"

    def notifications():
        from winrt.windows.ui.notifications.management import UserNotificationListener
        return f"access {int(UserNotificationListener.current.get_access_status())}"

    def hotspot():
        from winrt.windows.networking.connectivity import NetworkInformation
        from winrt.windows.networking.networkoperators import NetworkOperatorTetheringManager as Manager
        manager = Manager.create_from_connection_profile(NetworkInformation.get_internet_connection_profile())
        return (f"state {int(manager.tethering_operational_state)}, "
                f"SSID {manager.get_current_access_point_configuration().ssid}")

    def crypto():
        from dynamic_island.services import phone
        directory = tempfile.mkdtemp()
        previous = phone.APPDATA
        phone.APPDATA = directory
        try:
            phone.settings.pop("phone_cert_ip", None)
            certificate, _key = phone.ensure_cert("127.0.0.1")
            return f"certificate {os.path.getsize(certificate)} bytes"
        finally:
            phone.APPDATA = previous

    def misc():
        import qrcode
        import zoneinfo

        import icalendar  # noqa: F401
        import recurring_ical_events  # noqa: F401
        qrcode.QRCode().add_data("test")
        zoneinfo.ZoneInfo("Africa/Lome")
        return "qrcode, icalendar, time zones"

    def qt():
        from PySide6.QtGui import QImageReader
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication(sys.argv)
        formats = {bytes(fmt).decode() for fmt in QImageReader.supportedImageFormats()}
        return "image formats: " + ", ".join(
            sorted(fmt for fmt in formats if fmt in ("png", "jpg", "ico", "webp", "svg"))
        )

    def files_():
        from dynamic_island.core.config.paths import resource
        for path in (os.path.join("resources", "phone_page.html"), os.path.join("assets", "island.ico")):
            if not os.path.exists(resource(path)):
                raise FileNotFoundError(path)
        return "resources/phone_page.html, assets/island.ico"

    def brightness():
        import screen_brightness_control as sbc
        return f"{sbc.get_brightness(display=0)}"

    checks = (
        ("Application files", files_),
        ("Qt / images", qt),
        ("Media (Windows)", media),
        ("Audio", audio),
        ("UI Automation (Do Not Disturb)", uia),
        ("Wi-Fi / Bluetooth radios", radios),
        ("Bluetooth", bluetooth),
        ("Notifications", notifications),
        ("Hotspot", hotspot),
        ("Brightness", brightness),
        ("Phone HTTPS certificate", crypto),
        ("Miscellaneous", misc),
    )
    for name, fn in checks:
        check(name, fn)
    output = os.path.join(tempfile.gettempdir(), "DynamicIsland-selftest.txt")
    with open(output, "w", encoding="utf-8") as handle:
        handle.write("\n".join(results) + "\n")


def main():
    if "--selftest" in sys.argv:
        selftest()
    elif "--island" in sys.argv:
        from dynamic_island.app import main as run
        run()
    else:
        from dynamic_island.core.application.watchdog import main as watchdog_main
        watchdog_main()


if __name__ == "__main__":
    main()
