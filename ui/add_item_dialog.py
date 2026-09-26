"""Pick one catalogue item and a quantity to stage for addition."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from editor.catalog import ItemCatalog, ItemDefinition
from editor.i18n import tr

IconFor = Callable[[ItemDefinition], QIcon]


class AddItemDialog(QDialog):
    """Search the release catalogue; the caller still validates the choice."""

    def __init__(
        self,
        catalog: ItemCatalog,
        parent: QWidget | None = None,
        *,
        icon_for: IconFor | None = None,
        name_for: Callable[[ItemDefinition], str | None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("addItemDialog")
        self.setWindowTitle(tr("Добавить предмет"))
        self.resize(520, 560)
        label_of = name_for or (lambda definition: definition.display_name)
        self._labels = {definition.key: label_of(definition) for definition in catalog.items}
        self._definitions = sorted(
            catalog.items,
            key=lambda item: (
                self._labels[item.key] is None,
                (self._labels[item.key] or item.key).casefold(),
            ),
        )
        layout = QVBoxLayout(self)
        intro = QLabel(
            tr("Предмет будет добавлен в рюкзак при сохранении. Перед записью создаётся проверенная резервная копия."),
            self,
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText(tr("Поиск по названию или ключу…"))
        self.search_edit.textChanged.connect(self._filter)
        layout.addWidget(self.search_edit)
        self.item_list = QListWidget(self)
        self.item_list.setObjectName("addItemList")
        self.item_list.setIconSize(QSize(32, 32))
        self.item_list.currentItemChanged.connect(lambda *_args: self._sync_quantity())
        self.item_list.itemDoubleClicked.connect(lambda _item: self.accept())
        layout.addWidget(self.item_list, 1)
        form = QFormLayout()
        self.quantity_spin = QSpinBox(self)
        self.quantity_spin.setRange(1, 65535)
        form.addRow(tr("Количество"), self.quantity_spin)
        layout.addLayout(form)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText(tr("Добавить"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Отмена"))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        for definition in self._definitions:
            label = self._labels[definition.key] or definition.key
            entry = QListWidgetItem(label)
            entry.setData(Qt.ItemDataRole.UserRole, definition.key)
            entry.setToolTip(definition.key)
            if icon_for is not None:
                entry.setIcon(icon_for(definition))
            self.item_list.addItem(entry)
        if self.item_list.count():
            self.item_list.setCurrentRow(0)
        self._sync_quantity()
        self.search_edit.setFocus()

    def _filter(self, text: str) -> None:
        query = str(text).strip().casefold()
        first_visible = None
        for index in range(self.item_list.count()):
            entry = self.item_list.item(index)
            haystack = f"{entry.text()} {entry.data(Qt.ItemDataRole.UserRole)}".casefold()
            hidden = bool(query) and query not in haystack
            entry.setHidden(hidden)
            if not hidden and first_visible is None:
                first_visible = entry
        current = self.item_list.currentItem()
        if first_visible is not None and (current is None or current.isHidden()):
            self.item_list.setCurrentItem(first_visible)
        self._sync_quantity()

    def _selected_definition(self) -> ItemDefinition | None:
        entry = self.item_list.currentItem()
        if entry is None or entry.isHidden():
            return None
        key = entry.data(Qt.ItemDataRole.UserRole)
        return next((item for item in self._definitions if item.key == key), None)

    def _sync_quantity(self) -> None:
        definition = self._selected_definition()
        maximum = 65535
        if (
            definition is not None
            and definition.serialization_family == "ammo"
            and definition.max_stack
        ):
            maximum = int(definition.max_stack)
        self.quantity_spin.setMaximum(maximum)
        ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setEnabled(definition is not None)

    def selection(self) -> tuple[str, int] | None:
        definition = self._selected_definition()
        if definition is None:
            return None
        return definition.key, self.quantity_spin.value()


__all__ = ["AddItemDialog"]
