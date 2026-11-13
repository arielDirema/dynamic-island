"""Explicit registry of island tabs."""
from dynamic_island.ui.tabs import (
    agenda,
    clip,
    controls,
    dev,
    files,
    home,
    infos,
    launcher,
    phone,
    tasks,
    timers,
    wallet,
)
from dynamic_island.ui.tabs.agenda import AgendaTab
from dynamic_island.ui.tabs.clip import ClipTab
from dynamic_island.ui.tabs.controls import ControlsTab
from dynamic_island.ui.tabs.dev import DevTab
from dynamic_island.ui.tabs.files import FilesTab
from dynamic_island.ui.tabs.home import HomeTab
from dynamic_island.ui.tabs.infos import InfosTab
from dynamic_island.ui.tabs.launcher import LauncherTab
from dynamic_island.ui.tabs.phone import PhoneTab
from dynamic_island.ui.tabs.tasks import TasksTab
from dynamic_island.ui.tabs.timers import TimersTab
from dynamic_island.ui.tabs.wallet import WalletTab

# Tab-bar display order.
TABS = (HomeTab, AgendaTab, TimersTab, TasksTab, LauncherTab, FilesTab, PhoneTab, InfosTab, WalletTab,
        DevTab, ControlsTab, ClipTab)

# Views of each tab, used to pre-warm font rendering.
TAB_VIEWS = {
    cls.key: [key for key, _label in getattr(module, "VIEWS", [])]
    for module, cls in (
        (home, HomeTab), (agenda, AgendaTab), (timers, TimersTab), (tasks, TasksTab),
        (launcher, LauncherTab), (files, FilesTab), (phone, PhoneTab), (infos, InfosTab),
        (wallet, WalletTab), (dev, DevTab), (controls, ControlsTab), (clip, ClipTab),
    )
}
