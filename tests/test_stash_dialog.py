"""Stash dialog: checked items become stash takes; nothing else is staged."""

from __future__ import annotations

from PySide6.QtCore import Qt

from save_format import StashInfo
from ui.stash_dialog import StashDialog


def test_checked_items_are_returned_and_already_taken_stay_checked(qtbot) -> None:
    stashes = (
        StashInfo("zat_stash", "Затон", ((0x10, "medkit", 1), (0x11, "ammo_9x18_fmj", 30))),
        StashInfo("level_prefix_inventory_box_0000", None, ((0x20, "bread", 1),)),
    )
    dialog = StashDialog(stashes, taken=(0x11,))
    qtbot.addWidget(dialog)
    assert dialog.selection() == (0x11,)
    zaton = dialog.tree.topLevelItem(0)
    assert zaton.text(0) == "Затон"
    zaton.child(0).child(0).setCheckState(0, Qt.CheckState.Checked)
    assert dialog.selection() == (0x10, 0x11)
