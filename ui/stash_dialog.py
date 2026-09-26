"""Level stashes of a save: pick items to take into the backpack."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from editor.i18n import tr
from save_format import StashInfo


class StashDialog(QDialog):
    """Stashes grouped by level; checked items are staged, nothing is written here."""

    def __init__(
        self,
        stashes: Iterable[StashInfo],
        parent: QWidget | None = None,
        *,
        name_for: Callable[[str], str] | None = None,
        taken: Iterable[int] = (),
    ) -> None:
        super().__init__(parent)
        self.setObjectName("stashDialog")
        self.setWindowTitle(tr("Тайники"))
        self.resize(560, 620)
        label_of = name_for or (lambda key: key)
        already = set(taken)
        layout = QVBoxLayout(self)
        intro = QLabel(
            tr("Отмеченные предметы переедут из тайника в рюкзак при сохранении. Перед записью создаётся проверенная резервная копия."),
            self,
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.tree = QTreeWidget(self)
        self.tree.setObjectName("stashTree")
        self.tree.setHeaderHidden(True)
        levels: dict[str, QTreeWidgetItem] = {}
        for stash in stashes:
            level_name = stash.level or tr("Другое")
            level = levels.get(level_name)
            if level is None:
                level = QTreeWidgetItem(self.tree, [level_name])
                levels[level_name] = level
            box = QTreeWidgetItem(level, [stash.name])
            for handle, key, count in stash.items:
                text = label_of(key) + (f" × {count}" if count > 1 else "")
                entry = QTreeWidgetItem(box, [text])
                entry.setToolTip(0, key)
                entry.setData(0, Qt.ItemDataRole.UserRole, handle)
                entry.setCheckState(0, Qt.CheckState.Checked if handle in already else Qt.CheckState.Unchecked)
        self.tree.expandAll()
        layout.addWidget(self.tree, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("В рюкзак"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Отмена"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selection(self) -> tuple[int, ...]:
        chosen: list[int] = []
        iterator = [self.tree.topLevelItem(index) for index in range(self.tree.topLevelItemCount())]
        while iterator:
            node = iterator.pop()
            if node is None:
                continue
            handle = node.data(0, Qt.ItemDataRole.UserRole)
            if handle is not None and node.checkState(0) == Qt.CheckState.Checked:
                chosen.append(int(handle))
            iterator.extend(node.child(index) for index in range(node.childCount()))
        return tuple(sorted(chosen))


__all__ = ["StashDialog"]
