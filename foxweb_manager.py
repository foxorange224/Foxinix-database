#!/usr/bin/env python3
"""PyQt5 GUI manager for FoxWeb database."""

import sys
import logging
from typing import Optional

from PIL import Image
from PyQt6 import QtWidgets, QtCore, QtGui

from data_manager import DataManager

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
logger = logging.getLogger('foxweb_manager')


class FoxWebManager(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.dm = DataManager()
        self.current_cat: Optional[str] = None
        self.current_idx: Optional[int] = None

        self._build_ui()
        self._setup_shortcuts()

        if not self.dm.load():
            QtWidgets.QMessageBox.critical(self, 'Error', f'No se encuentra o no se puede leer {DataManager.DATA_FILE}')
            sys.exit(1)
        self._refresh_tree()
        self._update_title()
        self.status_bar.showMessage(
            f'Cargado: {sum(len(v) for v in self.dm.data.values())} elementos', 5000
        )

    def _build_ui(self):
        self.setWindowTitle('FoxWeb Database Manager')
        self.setGeometry(100, 100, 1150, 720)

        mw = QtWidgets.QWidget()
        self.setCentralWidget(mw)
        ml = QtWidgets.QHBoxLayout(mw)

        left = QtWidgets.QWidget()
        left.setMaximumWidth(350)
        ll = QtWidgets.QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(['Nombre', 'ID'])
        self.tree.setColumnWidth(0, 200)
        self.tree.currentItemChanged.connect(self._on_tree_current_changed)
        ll.addWidget(self.tree, 1)

        right = QtWidgets.QWidget()
        rl = QtWidgets.QVBoxLayout(right)

        tabs = QtWidgets.QTabWidget()
        self.form_widget = QtWidgets.QWidget()
        fl = QtWidgets.QFormLayout(self.form_widget)

        self.name_input = QtWidgets.QLineEdit()
        self.name_input.textChanged.connect(self._mark_modified)
        self.info_input = QtWidgets.QTextEdit()
        self.info_input.setMaximumHeight(80)
        self.info_input.textChanged.connect(self._mark_modified)
        self.enlace_input = QtWidgets.QLineEdit()
        self.enlace_input.textChanged.connect(self._mark_modified)
        self.id_input = QtWidgets.QLineEdit()
        self.id_input.setReadOnly(True)
        self.badges_input = QtWidgets.QLineEdit()
        self.badges_input.setPlaceholderText('Ej: LIGERO, OPEN SOURCE, WINDOWS XP')
        self.badges_input.textChanged.connect(self._on_badges_changed)

        self.badges_warn = QtWidgets.QLabel('')
        self.badges_warn.setStyleSheet('color: #e67e22; font-size: 11px;')
        self.badges_warn.setWordWrap(True)

        badges_container = QtWidgets.QWidget()
        bcl = QtWidgets.QVBoxLayout(badges_container)
        bcl.setContentsMargins(0, 0, 0, 0)
        bcl.setSpacing(0)
        bcl.addWidget(self.badges_input)
        bcl.addWidget(self.badges_warn)

        fl.addRow('Nombre:', self.name_input)
        fl.addRow('Info:', self.info_input)
        fl.addRow('Enlace:', self.enlace_input)
        fl.addRow('ID:', self.id_input)
        fl.addRow('Badges:', badges_container)

        icon_tab = QtWidgets.QWidget()
        il = QtWidgets.QVBoxLayout(icon_tab)

        self.icon_preview = QtWidgets.QLabel('Sin icono')
        self.icon_preview.setFixedSize(180, 180)
        self.icon_preview.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.icon_preview.setStyleSheet(
            'background: #1a1a1a; border: 1px solid #333; border-radius: 8px; color: #666;'
        )
        self.icon_preview.setScaledContents(True)

        icon_btn_row = QtWidgets.QHBoxLayout()
        self.btn_change_icon = QtWidgets.QPushButton('Cambiar icono...')
        self.btn_change_icon.clicked.connect(self._on_change_icon)
        self.btn_remove_icon = QtWidgets.QPushButton('Quitar icono')
        self.btn_remove_icon.clicked.connect(self._on_remove_icon)
        self.btn_fix_icons = QtWidgets.QPushButton('Reparar todos')
        self.btn_fix_icons.clicked.connect(self._on_fix_icons)

        icon_btn_row.addWidget(self.btn_change_icon)
        icon_btn_row.addWidget(self.btn_remove_icon)
        icon_btn_row.addWidget(self.btn_fix_icons)

        self.icon_info_label = QtWidgets.QLabel('Selecciona un elemento para gestionar su icono')
        self.icon_info_label.setStyleSheet('color: #888;')
        self.icon_info_label.setWordWrap(True)

        il.addWidget(self.icon_preview, 0, QtCore.Qt.AlignmentFlag.AlignCenter)
        il.addLayout(icon_btn_row)
        il.addWidget(self.icon_info_label)
        il.addStretch()

        tabs.addTab(self.form_widget, 'Editar')
        tabs.addTab(icon_tab, 'Icono')

        md_tab = QtWidgets.QWidget()
        mml = QtWidgets.QVBoxLayout(md_tab)

        md_label = QtWidgets.QLabel('Información adicional (markdown)')
        md_label.setStyleSheet('color: #aaa; font-size: 12px;')

        self.md_editor = QtWidgets.QTextEdit()
        self.md_editor.setPlaceholderText(
            'Contenido en markdown...\n\n'
            'Sintaxis especial:\n'
            '[boton de descarga, color=#hex, icono=fa-icon, enlace=url, title="Texto"]'
        )
        self.md_editor.textChanged.connect(self._mark_modified)

        md_btn_row = QtWidgets.QHBoxLayout()
        self.btn_md_save = QtWidgets.QPushButton('Guardar .md')
        self.btn_md_save.clicked.connect(self._on_md_save)
        self.btn_md_delete = QtWidgets.QPushButton('Eliminar .md')
        self.btn_md_delete.clicked.connect(self._on_md_delete)

        self.md_status = QtWidgets.QLabel('')
        self.md_status.setStyleSheet('color: #888;')

        md_btn_row.addWidget(self.btn_md_save)
        md_btn_row.addWidget(self.btn_md_delete)
        md_btn_row.addStretch()
        md_btn_row.addWidget(self.md_status)

        mml.addWidget(md_label)
        mml.addWidget(self.md_editor, 1)
        mml.addLayout(md_btn_row)

        tabs.addTab(md_tab, 'Info adicional')

        btn_row = QtWidgets.QHBoxLayout()
        self.btn_add = QtWidgets.QPushButton('+ Nuevo')
        self.btn_add.clicked.connect(self._on_add)

        self.btn_delete = QtWidgets.QPushButton('Eliminar')
        self.btn_delete.clicked.connect(self._on_delete)

        self.btn_move_up = QtWidgets.QPushButton('▲ Subir')
        self.btn_move_up.clicked.connect(self._on_move_up)

        self.btn_move_down = QtWidgets.QPushButton('▼ Bajar')
        self.btn_move_down.clicked.connect(self._on_move_down)

        self.btn_reorder = QtWidgets.QPushButton('Reordenar IDs')
        self.btn_reorder.clicked.connect(self._on_reorder)

        self.btn_save = QtWidgets.QPushButton('Guardar')
        self.btn_save.clicked.connect(self._on_save)

        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_delete)
        btn_row.addWidget(self.btn_move_up)
        btn_row.addWidget(self.btn_move_down)
        btn_row.addWidget(self.btn_reorder)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_save)

        rl.addWidget(tabs, 1)
        rl.addLayout(btn_row)
        ml.addWidget(left, 1)
        ml.addWidget(right, 2)

        self.status_bar = QtWidgets.QStatusBar()
        self.setStatusBar(self.status_bar)

    def _setup_shortcuts(self):
        QtGui.QShortcut(QtGui.QKeySequence('Ctrl+S'), self, self._on_save)
        QtGui.QShortcut(QtGui.QKeySequence('Ctrl+N'), self, self._on_add)
        QtGui.QShortcut(QtGui.QKeySequence('Ctrl+D'), self, self._on_delete)
        QtGui.QShortcut(QtGui.QKeySequence('Ctrl+R'), self, self._on_reorder)


    def _update_title(self):
        mark = ' *' if self.dm.modified else ''
        self.setWindowTitle(f'FoxWeb Database Manager{mark}')

    def _mark_modified(self):
        if not self.dm.modified:
            self.dm.modified = True
            self._update_title()

    def _refresh_tree(self):
        self.tree.clear()
        for cat in self.dm.categories_order:
            if cat not in self.dm.data:
                continue
            ci = QtWidgets.QTreeWidgetItem([cat.capitalize(), f'{len(self.dm.data[cat])}'])
            ci.setData(0, QtCore.Qt.ItemDataRole.UserRole, ('cat', cat))
            f = ci.font(0)
            f.setBold(True)
            ci.setFont(0, f)
            self.tree.addTopLevelItem(ci)
            for idx, item in enumerate(self.dm.data[cat]):
                s = QtWidgets.QTreeWidgetItem([item.get('name', ''), item.get('id', '')])
                s.setData(0, QtCore.Qt.ItemDataRole.UserRole, ('item', cat, idx))
                ci.addChild(s)
        self.tree.expandAll()

    def _on_tree_current_changed(self, current, previous):
        if current:
            self._on_tree_click(current, 0)

    def _on_tree_click(self, item, col):
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not data:
            return
        if data[0] == 'cat':
            self.current_cat = data[1]
            self.current_idx = None
            self._clear_form()
            return
        _, cat, idx = data
        self.current_cat = cat
        self.current_idx = idx
        entry = self.dm.data[cat][idx]
        self.name_input.setText(entry.get('name', ''))
        self.info_input.setPlainText(entry.get('info', ''))
        self.enlace_input.setText(entry.get('enlace', ''))
        self.id_input.setText(entry.get('id', ''))
        self.badges_input.setText(', '.join(entry.get('badges', [])))
        self._update_icon_preview(entry.get('id', ''))
        self._load_md_content(entry.get('id', ''))
        self.dm.modified = False
        self._update_title()

    def _clear_form(self):
        for w in [self.name_input, self.enlace_input, self.id_input, self.badges_input]:
            w.clear()
        self.info_input.clear()
        self.icon_preview.clear()
        self.icon_preview.setText('Sin icono')
        self.icon_info_label.setText('Selecciona un elemento para gestionar su icono')
        self.md_editor.clear()
        self.md_status.setText('')
        self.dm.modified = False
        self._update_title()

    def _on_badges_changed(self):
        self._mark_modified()
        text = self.badges_input.text()
        tags = [t.strip() for t in text.split(',') if t.strip()]
        warnings = []
        if len(tags) > 3:
            warnings.append('⚠ Máximo 3 etiquetas')
        over_14 = [t for t in tags if len(t) > 14]
        if over_14:
            warnings.append(f'⚠ {len(over_14)} etiqueta(s) superan los 14 caracteres')
        self.badges_warn.setText('\n'.join(warnings))
        self.badges_warn.setVisible(bool(warnings))

    def _update_icon_preview(self, item_id: str):
        pix = self.dm.get_icon_pixmap(item_id)
        if pix is not None:
            self.icon_preview.setPixmap(pix)
            self.icon_preview.setText('')
            self.icon_info_label.setText(self.dm.get_icon_info(item_id))
        else:
            self.icon_preview.clear()
            self.icon_preview.setText('Sin icono')
            self.icon_info_label.setText(self.dm.get_icon_info(item_id))

    def _on_change_icon(self):
        if self.current_idx is None or not self.current_cat:
            QtWidgets.QMessageBox.warning(self, 'Aviso', 'Selecciona un elemento primero')
            return
        entry = self.dm.data[self.current_cat][self.current_idx]
        item_id = entry.get('id', '')
        if not item_id:
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Seleccionar icono', '',
            'Imágenes (*.png *.jpg *.jpeg *.gif *.bmp *.webp)'
        )
        if not path:
            return
        if self.dm.set_icon(item_id, path):
            self._update_icon_preview(item_id)
            self.status_bar.showMessage(f'Icono guardado: {item_id}.webp', 3000)
        else:
            QtWidgets.QMessageBox.critical(self, 'Error', 'No se pudo procesar la imagen')

    def _on_remove_icon(self):
        if self.current_idx is None or not self.current_cat:
            return
        entry = self.dm.data[self.current_cat][self.current_idx]
        item_id = entry.get('id', '')
        self.dm.remove_icon(item_id)
        self._update_icon_preview(item_id)
        self.status_bar.showMessage('Icono eliminado', 3000)

    def _on_fix_icons(self):
        fixed = self.dm.fix_icons()
        self.status_bar.showMessage(f'Iconos reparados: {fixed}', 5000)
        if self.current_idx is not None and self.current_cat:
            entry = self.dm.data[self.current_cat][self.current_idx]
            self._update_icon_preview(entry.get('id', ''))

    def _load_md_content(self, item_id: str):
        content = self.dm.load_md(item_id)
        if content is not None:
            self.md_editor.setPlainText(content)
            self.md_status.setText(f'{item_id}.md')
        else:
            self.md_editor.clear()
            self.md_status.setText('No hay .md')

    def _on_md_save(self):
        if self.current_idx is None or not self.current_cat:
            QtWidgets.QMessageBox.warning(self, 'Aviso', 'Selecciona un elemento primero')
            return
        entry = self.dm.data[self.current_cat][self.current_idx]
        item_id = entry.get('id', '')
        if not item_id:
            return
        content = self.md_editor.toPlainText()
        if self.dm.save_md(item_id, content):
            self.md_status.setText(f'{item_id}.md guardado')
            self.status_bar.showMessage(f'MD guardado: {item_id}.md', 3000)

    def _on_md_delete(self):
        if self.current_idx is None or not self.current_cat:
            return
        entry = self.dm.data[self.current_cat][self.current_idx]
        item_id = entry.get('id', '')
        self.dm.delete_md(item_id)
        self.md_editor.clear()
        self.md_status.setText('.md eliminado')
        self.status_bar.showMessage(f'MD eliminado: {item_id}.md', 3000)

    def _on_move_up(self):
        if self.current_idx is None or not self.current_cat:
            return
        new_idx = self.dm.move_up(self.current_cat, self.current_idx)
        if new_idx is None:
            return
        self.current_idx = new_idx
        self._refresh_tree()
        self._select_tree_item(self.current_cat, self.current_idx)
        self._update_title()

    def _on_move_down(self):
        if self.current_idx is None or not self.current_cat:
            return
        new_idx = self.dm.move_down(self.current_cat, self.current_idx)
        if new_idx is None:
            return
        self.current_idx = new_idx
        self._refresh_tree()
        self._select_tree_item(self.current_cat, self.current_idx)
        self._update_title()

    def _select_tree_item(self, cat: str, idx: int):
        for i in range(self.tree.topLevelItemCount()):
            ci = self.tree.topLevelItem(i)
            d = ci.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if d and d[0] == 'cat' and d[1] == cat:
                child = ci.child(idx)
                if child:
                    self.tree.setCurrentItem(child)
                    self._on_tree_click(child, 0)
                break

    def _on_reorder(self):
        confirm = QtWidgets.QMessageBox.question(
            self, 'Reordenar IDs',
            '¿Reasignar IDs secuenciales y renombrar iconos/.md?\n'
            'Los elementos se ordenarán por categoría e ID actual.',
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self.dm.reorder_ids()
        self.current_idx = None
        self.current_cat = None
        self._clear_form()
        self._refresh_tree()
        self._update_title()
        self.status_bar.showMessage('IDs reordenados', 5000)

    def _on_add(self):
        if not self.current_cat:
            QtWidgets.QMessageBox.warning(self, 'Aviso', 'Selecciona una categoría primero')
            return
        new_id = self.dm.add_item(self.current_cat)
        if new_id is None:
            return
        self._refresh_tree()
        self.status_bar.showMessage(f'Nuevo elemento creado (ID: {new_id})', 3000)
        self._update_title()

    def _on_delete(self):
        if self.current_idx is None or not self.current_cat:
            QtWidgets.QMessageBox.warning(self, 'Aviso', 'Selecciona un elemento para eliminar')
            return
        entry = self.dm.data[self.current_cat][self.current_idx]
        r = QtWidgets.QMessageBox.question(
            self, 'Confirmar',
            f'¿Eliminar "{entry.get("name")}"?',
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        if r == QtWidgets.QMessageBox.StandardButton.Yes:
            self.dm.delete_item(self.current_cat, self.current_idx)
            self.current_idx = None
            self._clear_form()
            self._refresh_tree()
            self._update_title()
            self.status_bar.showMessage('Elemento eliminado', 3000)

    def _on_save(self):
        if self.current_idx is not None and self.current_cat:
            self._save_current_item()
        if self.dm.save():
            self._update_title()
            self.status_bar.showMessage('Guardado correctamente', 3000)
        else:
            QtWidgets.QMessageBox.critical(self, 'Error', 'No se pudo guardar')

    def _save_current_item(self):
        if self.current_idx is None or not self.current_cat:
            return
        raw = self.enlace_input.text()
        enlace = raw if raw and raw != '#' else '#'
        badges = [b.strip() for b in self.badges_input.text().split(',') if b.strip()]
        self.dm.update_item(
            self.current_cat, self.current_idx,
            name=self.name_input.text(),
            info=self.info_input.toPlainText(),
            enlace=enlace,
            badges=badges,
        )
        self._refresh_tree()

    def closeEvent(self, event):
        if self.dm.modified:
            r = QtWidgets.QMessageBox.question(
                self, 'Cambios sin guardar',
                'Hay cambios sin guardar. ¿Guardar antes de salir?',
                QtWidgets.QMessageBox.StandardButton.Save | QtWidgets.QMessageBox.StandardButton.Discard | QtWidgets.QMessageBox.StandardButton.Cancel,
            )
            if r == QtWidgets.QMessageBox.StandardButton.Save:
                if self.current_idx is not None and self.current_cat:
                    self._save_current_item()
                if not self.dm.save():
                    QtWidgets.QMessageBox.critical(self, 'Error', 'No se pudo guardar')
                    event.ignore()
                    return
            elif r == QtWidgets.QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
        event.accept()


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    w = FoxWebManager()
    w.show()
    sys.exit(app.exec())
