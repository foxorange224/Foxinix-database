#!/usr/bin/env python3
"""PyQt6 GUI manager for FoxWeb database."""

import sys, os, json, re, shutil
import logging
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError
import io

from PIL import Image
from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtGui import QIcon, QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QAction, QKeySequence
from PyQt6.QtWidgets import QApplication, QStyleFactory


from crypto_utils import DATA_FILE, ICONS_DIR
# ...
from data_manager import DataManager

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
logger = logging.getLogger('foxinix_manager')


class MdHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules = []

        h_fmt = QTextCharFormat()
        h_fmt.setForeground(QColor('#e06c75'))
        h_fmt.setFontWeight(QFont.Weight.Bold)
        for i in range(1, 7):
            self.rules.append((re.compile(f'^{"#" * i} .+'), h_fmt))

        bold_fmt = QTextCharFormat()
        bold_fmt.setFontWeight(QFont.Weight.Bold)
        self.rules.append((re.compile(r'\*\*.+?\*\*'), bold_fmt))

        italic_fmt = QTextCharFormat()
        italic_fmt.setFontItalic(True)
        self.rules.append((re.compile(r'\*(.+?)\*'), italic_fmt))

        self.code_fmt = QTextCharFormat()
        self.code_fmt.setForeground(QColor('#e6db74'))
        self.code_fmt.setFontFamilies(['Cascadia Code', 'Fira Code', 'Consolas', 'monospace'])
        self.rules.append((re.compile(r'`[^`]+`'), self.code_fmt))

        link_fmt = QTextCharFormat()
        link_fmt.setForeground(QColor('#56b6c2'))
        link_fmt.setUnderlineStyle(QtGui.QTextCharFormat.UnderlineStyle.SingleUnderline)
        self.rules.append((re.compile(r'\[.+?\]\(.+?\)'), link_fmt))

        list_fmt = QTextCharFormat()
        list_fmt.setForeground(QColor('#c678dd'))
        self.rules.append((re.compile(r'^[-*]\s'), list_fmt))
        self.rules.append((re.compile(r'^\d+\.\s'), list_fmt))

    def highlightBlock(self, text):
        # Code block state
        self.setCurrentBlockState(0)
        if self.previousBlockState() == 1:
            self.setCurrentBlockState(1)

        # Multiline code marker
        if text.startswith('```'):
            # Toggle state
            if self.previousBlockState() == 1:
                self.setCurrentBlockState(0)
            else:
                self.setCurrentBlockState(1)
            
            # Highlight the marker
            self.setFormat(0, 3, self.code_fmt)
            return

        # If inside code block, highlight everything
        if self.previousBlockState() == 1:
            self.setFormat(0, len(text), self.code_fmt)
            return

        # Inline rules
        for pattern, fmt in self.rules:
            for m in pattern.finditer(text):
                start, end = m.span()
                self.setFormat(start, end - start, fmt)



class LinkValidator(QtCore.QThread):
    finished = QtCore.pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            req = Request(self.url, method='HEAD')
            req.add_header('User-Agent', 'Mozilla/5.0')
            with urlopen(req, timeout=10) as resp:
                self.finished.emit(f'OK: {resp.status} {self.url}')
        except URLError as e:
            self.finished.emit(f'Error: {e.reason}')
        except Exception as e:
            self.finished.emit(f'Error: {e}')

class UndoManager:
    def __init__(self, max_states=50):
        self.states = []
        self.pos = -1
        self.max = max_states
        self._saved_pos = -1

    def push(self, state: dict):
        self.states = self.states[:self.pos + 1]
        self.states.append(state)
        if len(self.states) > self.max:
            self.states.pop(0)
        self.pos = len(self.states) - 1

    def undo(self) -> Optional[dict]:
        if self.pos > 0:
            self.pos -= 1
            return self.states[self.pos]
        return None

    def redo(self) -> Optional[dict]:
        if self.pos < len(self.states) - 1:
            self.pos += 1
            return self.states[self.pos]
        return None

    def can_undo(self) -> bool:
        return self.pos > 0

    def can_redo(self) -> bool:
        return self.pos < len(self.states) - 1

    def reset(self):
        self.states.clear()
        self.pos = -1

class PreferencesDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Preferencias')
        self.setMinimumWidth(500)
        
        self.settings = QtCore.QSettings('Foxinix', 'FoxinixManager')
        
        layout = QtWidgets.QVBoxLayout(self)
        self.tabs = QtWidgets.QTabWidget()
        
        # General Tab
        self.general_tab = QtWidgets.QWidget()
        gl = QtWidgets.QFormLayout(self.general_tab)
        
        self.auto_save_cb = QtWidgets.QCheckBox('Habilitar Auto-guardado')
        self.auto_save_cb.setChecked(self.settings.value('auto_save', True, type=bool))
        gl.addRow(self.auto_save_cb)
        
        self.timeout_spin = QtWidgets.QSpinBox()
        self.timeout_spin.setRange(1, 300)
        self.timeout_spin.setValue(self.settings.value('timeout', 5, type=int))
        self.timeout_spin.setSuffix(' segundos')
        gl.addRow('Timeout de Verificación:', self.timeout_spin)
        
        # Appearance Tab
        self.appearance_tab = QtWidgets.QWidget()
        al = QtWidgets.QVBoxLayout(self.appearance_tab)
        
        self.theme_combo = QtWidgets.QComboBox()
        self.theme_combo.addItems(QStyleFactory.keys())
        self.theme_combo.setCurrentText(self.settings.value('theme', 'Breeze'))
        al.addWidget(QtWidgets.QLabel('Tema de la Interfaz:'))
        al.addWidget(self.theme_combo)
        al.addStretch()
        
        self.tabs.addTab(self.general_tab, 'General')
        self.tabs.addTab(self.appearance_tab, 'Apariencia')
        
        layout.addWidget(self.tabs)
        
        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_save = QtWidgets.QPushButton('Guardar')
        self.btn_save.clicked.connect(self.save_settings)
        self.btn_cancel = QtWidgets.QPushButton('Cancelar')
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)

    def save_settings(self):
        self.settings.setValue('auto_save', self.auto_save_cb.isChecked())
        self.settings.setValue('timeout', self.timeout_spin.value())
        self.settings.setValue('theme', self.theme_combo.currentText())
        self.accept()

    def get_values(self):
        return {
            'auto_save': self.auto_save_cb.isChecked(),
            'timeout': self.timeout_spin.value(),
            'theme': self.theme_combo.currentText()
        }

class FoxWebManager(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Settings
        self.settings = QtCore.QSettings('Foxinix', 'FoxinixManager')
        
        # Set default style from settings
        theme = self.settings.value('theme', 'Breeze')
        if theme in QStyleFactory.keys():
            QApplication.setStyle(theme)
        elif 'Breeze' in QStyleFactory.keys():
            QApplication.setStyle('Breeze')
        elif 'Fusion' in QStyleFactory.keys():
            QApplication.setStyle('Fusion')

        self.dm = DataManager()
        self.current_cat: Optional[str] = None
        self.current_idx: Optional[int] = None
        self._switching = False
        self._refreshing = False
        self.undo_mgr = UndoManager()
        
        # Load preferences
        self.auto_save_enabled = self.settings.value('auto_save', True, type=bool)
        self.timeout_pref = self.settings.value('timeout', 5, type=int)
        
        self.auto_save_timer = QtCore.QTimer()
        self.auto_save_timer.setSingleShot(True)
        self.auto_save_timer.timeout.connect(self._do_auto_save)
        self._ignore_form_changes = False

        # File watcher for real-time icon updates
        self.watcher = QtCore.QFileSystemWatcher()
        if os.path.exists(ICONS_DIR):
            self.watcher.addPath(ICONS_DIR)
        self.watcher.directoryChanged.connect(self._on_icons_dir_changed)

        self._build_ui()
        self._setup_shortcuts()

        if not self.dm.load():
            QtWidgets.QMessageBox.critical(self, 'Error', f'No se encuentra o no se puede leer {DATA_FILE}')
            sys.exit(1)
        self._refresh_tree()
        self._update_title()
        self._update_stats()

    def _build_ui(self):
        self.setWindowTitle('Foxinix Manager')
        self.setWindowIcon(QIcon(os.path.join(os.path.dirname(__file__), 'favicon.ico')))
        self.setGeometry(100, 100, 1400, 750)

        mw = QtWidgets.QWidget()
        self.setCentralWidget(mw)
        ml = QtWidgets.QVBoxLayout(mw)
        ml.setContentsMargins(0, 0, 0, 0)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        
        left = QtWidgets.QWidget()
        ll = QtWidgets.QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)

        self.tree_search = QtWidgets.QLineEdit()
        self.tree_search.setPlaceholderText('Buscar en el árbol...')
        self.tree_search.setClearButtonEnabled(True)
        self.tree_search.textChanged.connect(self._refresh_tree)
        ll.addWidget(self.tree_search)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(['Nombre', 'ID'])
        self.tree.setColumnWidth(0, 200)
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDropIndicatorShown(True)
        self.tree.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
        self.tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        self.tree.currentItemChanged.connect(self._on_tree_current_changed)
        self.tree.model().rowsMoved.connect(self._on_tree_rows_moved)
        ll.addWidget(self.tree, 1)

        right = QtWidgets.QWidget()
        rl = QtWidgets.QVBoxLayout(right)

        tabs = QtWidgets.QTabWidget()
        self.form_widget = QtWidgets.QWidget()
        fl = QtWidgets.QFormLayout(self.form_widget)

        self.name_input = QtWidgets.QLineEdit()
        self.name_input.textChanged.connect(self._on_form_changed)
        self.info_input = QtWidgets.QTextEdit()
        self.info_input.setMaximumHeight(80)
        self.info_input.setPlaceholderText('Sin descripción - No aparecera el cuadro de descripción')
        self.info_input.textChanged.connect(self._on_form_changed)
        self.enlace_input = QtWidgets.QLineEdit()
        self.enlace_input.textChanged.connect(self._on_form_changed)
        self.id_input = QtWidgets.QLineEdit()
        self.id_input.setReadOnly(True)
        self.id_input.setToolTip('No se puede cambiar los IDs para evitar desorden. Si quiere reordenar presiona el boton que esta abajo.')
        
        self.verified_cb = QtWidgets.QCheckBox('Verificado')
        self.verified_cb.stateChanged.connect(self._on_form_changed)
        
        self.badges_input = QtWidgets.QLineEdit()
        self.badges_input.setPlaceholderText('Ej: LIGERO, OPEN SOURCE, WINDOWS XP')
        self.badges_input.textChanged.connect(self._on_badges_changed)

        # Quick Badges
        self.quick_badges_layout = QtWidgets.QHBoxLayout()
        self.quick_badges_layout.setSpacing(5)
        common_badges = ['LIGERO', 'OPEN SOURCE', 'ESENCIAL', 'WINDOWS XP', 'GRATUITO']
        for badge in common_badges:
            btn = QtWidgets.QPushButton(badge)
            btn.setFixedWidth(80)
            btn.setStyleSheet('font-size: 10px; padding: 2px;')
            btn.clicked.connect(lambda checked, b=badge: self._add_quick_badge(b))
            self.quick_badges_layout.addWidget(btn)
        self.quick_badges_layout.addStretch()

        self.badges_warn = QtWidgets.QWidget()
        self.badges_warn.setVisible(False)
        bw_layout = QtWidgets.QHBoxLayout(self.badges_warn)
        bw_layout.setContentsMargins(0, 2, 0, 0)
        bw_layout.setSpacing(4)
        self.badges_warn_icon = QtWidgets.QLabel()
        self.badges_warn_icon.setFixedSize(16, 16)
        warning_icon = QIcon.fromTheme('dialog-warning')
        if not warning_icon.isNull():
            self.badges_warn_icon.setPixmap(warning_icon.pixmap(16, 16))
        self.badges_warn_text = QtWidgets.QLabel('')
        self.badges_warn_text.setStyleSheet('color: #e67e22; font-size: 11px;')
        self.badges_warn_text.setWordWrap(True)
        bw_layout.addWidget(self.badges_warn_icon)
        bw_layout.addWidget(self.badges_warn_text, 1)

        badges_container = QtWidgets.QWidget()
        bcl = QtWidgets.QVBoxLayout(badges_container)
        bcl.setContentsMargins(0, 0, 0, 0)
        bcl.setSpacing(0)
        bcl.addWidget(self.badges_input)
        bcl.addLayout(self.quick_badges_layout)
        bcl.addWidget(self.badges_warn)

        self.btn_validate_link = QtWidgets.QPushButton()
        self.btn_validate_link.setIcon(QIcon.fromTheme('emblem-web'))
        self.btn_validate_link.setToolTip('Probar enlace')
        self.btn_validate_link.setFixedWidth(32)
        self.btn_validate_link.clicked.connect(self._on_validate_link)

        enlace_row = QtWidgets.QHBoxLayout()
        enlace_row.addWidget(self.enlace_input, 1)
        enlace_row.addWidget(self.btn_validate_link)

        enlace_container = QtWidgets.QWidget()
        enlace_container.setLayout(enlace_row)

        fl.addRow('Nombre:', self.name_input)
        fl.addRow('Info:', self.info_input)
        fl.addRow('Enlace:', enlace_container)
        fl.addRow('ID:', self.id_input)
        fl.addRow('Verificado:', self.verified_cb)
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
        self.btn_change_icon.setIcon(QIcon.fromTheme('document-open'))
        self.btn_change_icon.clicked.connect(self._on_change_icon)
        self.btn_remove_icon = QtWidgets.QPushButton('Quitar icono')
        self.btn_remove_icon.setIcon(QIcon.fromTheme('edit-delete'))
        self.btn_remove_icon.clicked.connect(self._on_remove_icon)
        self.btn_sync_name = QtWidgets.QPushButton('Sincro Nombre')
        self.btn_sync_name.setToolTip('Renombrar imagen basándose en el nombre del programa')
        self.btn_sync_name.clicked.connect(self._on_sync_icon_name)
        self.btn_verify_icons = QtWidgets.QPushButton('Verificar')
        self.btn_verify_icons.setIcon(QIcon.fromTheme('dialog-information'))
        self.btn_verify_icons.clicked.connect(self._on_verify_icons)
        self.btn_fix_icons = QtWidgets.QPushButton('Reparar todos')
        self.btn_fix_icons.setIcon(QIcon.fromTheme('tools'))
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

        self.md_stack = QtWidgets.QStackedWidget()
        self.md_editor = QtWidgets.QTextEdit()
        self.md_editor.setPlaceholderText(
            'Contenido en markdown...\n\n'
            'Sintaxis especial:\n'
            '[boton de descarga, color=#hex, icono=fa-icon, enlace=url, title="Texto"]\n\n'
            'Pega una imagen (Ctrl+V) para insertarla automáticamente.'
        )
        self.md_editor.textChanged.connect(self._mark_modified)
        self.md_highlighter = MdHighlighter(self.md_editor.document())

        self.preview_browser = QtWidgets.QTextBrowser()
        self.preview_browser.setOpenExternalLinks(True)
        self.preview_browser.setStyleSheet(
            'background: #1a1a2e; color: #ccc; border: 1px solid #333; border-radius: 6px; padding: 12px;'
        )

        self.md_stack.addWidget(self.md_editor)
        self.md_stack.addWidget(self.preview_browser)

        md_btn_row = QtWidgets.QHBoxLayout()
        self.btn_md_save = QtWidgets.QPushButton('Guardar .md')
        self.btn_md_save.setIcon(QIcon.fromTheme('document-save'))
        self.btn_md_save.clicked.connect(self._on_md_save)
        self.btn_md_delete = QtWidgets.QPushButton('Eliminar .md')
        self.btn_md_delete.setIcon(QIcon.fromTheme('edit-delete'))
        self.btn_md_delete.clicked.connect(self._on_md_delete)

        self.btn_md_preview = QtWidgets.QPushButton('Vista previa')
        self.btn_md_preview.setIcon(QIcon.fromTheme('zoom-in'))
        self.btn_md_preview.clicked.connect(self._toggle_md_preview)

        self.md_status = QtWidgets.QLabel('')
        self.md_status.setStyleSheet('color: #888;')

        md_btn_row.addWidget(self.btn_md_save)
        md_btn_row.addWidget(self.btn_md_delete)
        md_btn_row.addWidget(self.btn_md_preview)
        md_btn_row.addStretch()
        md_btn_row.addWidget(self.md_status)

        mml.addWidget(md_label)
        mml.addWidget(self.md_stack, 1)
        mml.addLayout(md_btn_row)

        tabs.addTab(md_tab, 'Info adicional')
        
        # Top customization bar
        top_bar = QtWidgets.QHBoxLayout()
        top_bar.addStretch()
        
        btn_row = QtWidgets.QHBoxLayout()
        self.btn_add = QtWidgets.QPushButton('Nuevo')


        self.btn_add.setIcon(QIcon.fromTheme('list-add'))
        self.btn_add.clicked.connect(self._on_add)

        self.btn_delete = QtWidgets.QPushButton('Eliminar')
        self.btn_delete.setIcon(QIcon.fromTheme('edit-delete'))
        self.btn_delete.clicked.connect(self._on_delete)

        self.btn_move_up = QtWidgets.QPushButton('Subir')
        self.btn_move_up.setIcon(QIcon.fromTheme('go-up'))
        self.btn_move_up.clicked.connect(self._on_move_up)

        self.btn_move_down = QtWidgets.QPushButton('Bajar')
        self.btn_move_down.setIcon(QIcon.fromTheme('go-down'))
        self.btn_move_down.clicked.connect(self._on_move_down)

        self.btn_reorder = QtWidgets.QPushButton('Reordenar')
        self.btn_reorder.setIcon(QIcon.fromTheme('view-refresh'))
        self.btn_reorder.clicked.connect(self._on_reorder)
        
        self.auto_save_cb = QtWidgets.QCheckBox('Auto-guardado')
        self.auto_save_cb.stateChanged.connect(self._on_auto_save_toggled)
        
        self.btn_save = QtWidgets.QPushButton('Guardar')
        self.btn_save.setIcon(QIcon.fromTheme('document-save'))
        self.btn_save.clicked.connect(self._on_save)
        

        
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_delete)
        btn_row.addWidget(self.btn_move_up)
        btn_row.addWidget(self.btn_move_down)
        btn_row.addWidget(self.btn_reorder)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_save)


        rl.addLayout(top_bar)
        rl.addWidget(tabs, 1)
        rl.addLayout(btn_row)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([600, 800])
        ml.addWidget(splitter)

        self.status_bar = QtWidgets.QStatusBar()
        self.stats_label = QtWidgets.QLabel()
        self.stats_label.setStyleSheet('color: #888; margin-right: 15px;')
        self.status_bar.addPermanentWidget(self.stats_label)
        
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)
        
        self.setStatusBar(self.status_bar)

        # Menu Bar
        self.menu_bar = self.menuBar()
        
        file_menu = self.menu_bar.addMenu('&Archivo')
        save_act = QAction('Guardar', self)
        save_act.setShortcut('Ctrl+S')
        save_act.triggered.connect(self._on_save)
        file_menu.addAction(save_act)
        
        file_menu.addSeparator()
        exit_act = QAction('Salir', self)
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)
        
        edit_menu = self.menu_bar.addMenu('&Edición')
        undo_act = QAction('Deshacer', self)
        undo_act.setShortcut('Ctrl+Z')
        undo_act.triggered.connect(self._on_undo)
        edit_menu.addAction(undo_act)
        
        redo_act = QAction('Rehacer', self)
        redo_act.setShortcut('Ctrl+Y')
        redo_act.triggered.connect(self._on_redo)
        edit_menu.addAction(redo_act)
        
        tools_menu = self.menu_bar.addMenu('&Herramientas')
        
        verify_icons_act = QAction('Verificar iconos', self)
        verify_icons_act.triggered.connect(self._on_verify_icons)
        tools_menu.addAction(verify_icons_act)
        
        config_menu = self.menu_bar.addMenu('&Configuración')
        pref_act = QAction('Preferencias', self)
        pref_act.triggered.connect(self._on_preferences)
        config_menu.addAction(pref_act)

    def _setup_shortcuts(self):
        QtGui.QShortcut(QtGui.QKeySequence('Ctrl+S'), self, self._on_save)
        QtGui.QShortcut(QtGui.QKeySequence('Ctrl+N'), self, self._on_add)
        QtGui.QShortcut(QtGui.QKeySequence('Ctrl+D'), self, self._on_delete)
        QtGui.QShortcut(QtGui.QKeySequence('Ctrl+R'), self, self._on_reorder)
        QtGui.QShortcut(QtGui.QKeySequence('Ctrl+Z'), self, self._on_undo)
        QtGui.QShortcut(QtGui.QKeySequence('Ctrl+Y'), self, self._on_redo)
        QtGui.QShortcut(QtGui.QKeySequence('Ctrl+Shift+P'), self, self._toggle_md_preview)
        QtGui.QShortcut(QtGui.QKeySequence('Ctrl+C'), self, self._on_copy_item)
        QtGui.QShortcut(QtGui.QKeySequence('Ctrl+V'), self, self._on_paste_item)

    def _get_form_state(self) -> dict:
        return {
            'name': self.name_input.text(),
            'info': self.info_input.toPlainText(),
            'enlace': self.enlace_input.text(),
            'verified': self.verified_cb.isChecked(),
            'badges': self.badges_input.text(),
            'md': self.md_editor.toPlainText(),
        }

    def _apply_form_state(self, state: dict):
        self._ignore_form_changes = True
        self.name_input.setText(state.get('name', ''))
        self.info_input.setPlainText(state.get('info', ''))
        self.enlace_input.setText(state.get('enlace', ''))
        self.verified_cb.setChecked(state.get('verified', False))
        self.badges_input.setText(state.get('badges', ''))
        self.md_editor.setPlainText(state.get('md', ''))
        self._ignore_form_changes = False


    def _on_form_changed(self):
        if self._ignore_form_changes:
            return
        self._mark_modified()
        self.undo_mgr.push(self._get_form_state())
        if self.auto_save_enabled:
            self.auto_save_timer.start(1000)

    def _on_undo(self):
        state = self.undo_mgr.undo()
        if state:
            self._apply_form_state(state)
            if self.auto_save_enabled:
                self.auto_save_timer.start(1000)

    def _on_redo(self):
        state = self.undo_mgr.redo()
        if state:
            self._apply_form_state(state)
            if self.auto_save_enabled:
                self.auto_save_timer.start(1000)

    def _update_title(self):
        mark = ' *' if self.dm.modified else ''
        self.setWindowTitle(f'Foxinix Manager{mark}')

    def _mark_modified(self):
        if not self.dm.modified:
            self.dm.modified = True
            self._update_title()

    def _update_stats(self):
        total = sum(len(v) for v in self.dm.data.values())
        cats = len(self.dm.data)
        self.stats_label.setText(f'{cats} cat. | {total} elem.')

    def _refresh_tree(self):
        self._refreshing = True
        try:
            query = self.tree_search.text().lower().strip()
            self.tree.clear()
            self.tree.setIconSize(QtCore.QSize(24, 24))
            self.tree.setColumnWidth(0, 450)
            for cat in self.dm.categories_order:

                if cat not in self.dm.data:
                    continue
                items = self.dm.data[cat]
                if query:
                    items = [it for it in items if query in it.get('name', '').lower() or query in it.get('id', '').lower()]
                if query and not items:
                    continue
                ci = QtWidgets.QTreeWidgetItem([f'{cat.capitalize()} ({len(items)})'])
                ci.setData(0, QtCore.Qt.ItemDataRole.UserRole, ('cat', cat))
                f = ci.font(0)
                f.setBold(True)
                ci.setFont(0, f)
                self.tree.addTopLevelItem(ci)
                for idx, item in enumerate(self.dm.data[cat]):
                    if query and query not in item.get('name', '').lower() and query not in item.get('id', '').lower():
                        continue
                    
                    name = item.get('name', '')
                    status = item.get('link_status', 'pending')
                    if status == 'verified':
                        name = f'✅ {name}'
                    elif status == 'broken':
                        name = f'❌ {name}'
                        
                    s = QtWidgets.QTreeWidgetItem([name, item.get('id', '')])
                    s.setData(0, QtCore.Qt.ItemDataRole.UserRole, ('item', cat, idx))
                    ip = os.path.join('icons', f'{item.get("id", "")}.webp')
                    if os.path.exists(ip):
                        s.setIcon(0, QIcon(ip))
                    ci.addChild(s)
            self.tree.expandAll()
        finally:
            self._refreshing = False

    def _on_tree_current_changed(self, current, previous):
        if not current or self._switching or self._refreshing:
            return
        try:
            current.data(0, QtCore.Qt.ItemDataRole.UserRole)
        except RuntimeError:
            return
        if self.dm.modified:
            r = QtWidgets.QMessageBox.question(
                self, 'Cambios sin guardar',
                'Hay cambios sin guardar en el elemento actual. '
                '¿Guardar antes de cambiar?',
                QtWidgets.QMessageBox.StandardButton.Save
                | QtWidgets.QMessageBox.StandardButton.Discard
                | QtWidgets.QMessageBox.StandardButton.Cancel,
            )
            if r == QtWidgets.QMessageBox.StandardButton.Save:
                self._save_current_item()
            elif r == QtWidgets.QMessageBox.StandardButton.Cancel:
                self._switching = True
                self.tree.setCurrentItem(previous)
                self._switching = False
                return
        try:
            self._on_tree_click(current, 0)
        except RuntimeError:
            pass

    def _on_tree_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        menu = QtWidgets.QMenu()
        
        if item:
            data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if data and data[0] == 'item':
                act_del = menu.addAction('Eliminar')
                act_up = menu.addAction('Subir')
                act_down = menu.addAction('Bajar')
                
                action = menu.exec(self.tree.mapToGlobal(pos))
                if action == act_del: self._on_delete()
                elif action == act_up: self._on_move_up()
                elif action == act_down: self._on_move_down()
            elif data and data[0] == 'cat':
                act_add = menu.addAction('Nuevo elemento')
                action = menu.exec(self.tree.mapToGlobal(pos))
                if action == act_add: self._on_add()
        else:
            # Right click on empty area
            act_reorder = menu.addAction('Reordenar todos los IDs')
            action = menu.exec(self.tree.mapToGlobal(pos))
            if action == act_reorder: self._on_reorder()

    def _on_icons_dir_changed(self):
        """Handles automatic updates when the icons directory changes."""
        # Clear DataManager's icon cache to force reloading from disk
        self.dm._icon_cache.clear()
        
        # Update the current preview if an item is selected
        if self.current_idx is not None and self.current_cat:
            entry = self.dm.data[self.current_cat][self.current_idx]
            self._update_icon_preview(entry.get('id', ''))
        
        # Update all icons in the tree without clearing the tree
        self._update_tree_icons()

    def _update_tree_icons(self):
        """Updates icons for all items in the tree without resetting the tree structure."""
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            cat_item = root.child(i)
            for j in range(cat_item.childCount()):
                item = cat_item.child(j)
                data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if data and data[0] == 'item':
                    _, cat, idx = data
                    if cat in self.dm.data and idx < len(self.dm.data[cat]):
                        item_id = self.dm.data[cat][idx].get('id', '')
                        ip = os.path.join(ICONS_DIR, f'{item_id}.webp')
                        if os.path.exists(ip):
                            item.setIcon(0, QIcon(ip))
                        else:
                            item.setIcon(0, QIcon())

    def _on_tree_click(self, item, col):
        try:
            data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        except RuntimeError:
            return
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
        self._ignore_form_changes = True
        self.name_input.setText(entry.get('name', ''))
        self.info_input.setPlainText(entry.get('info', ''))
        self.enlace_input.setText(entry.get('enlace', ''))
        self.id_input.setText(entry.get('id', ''))
        self.verified_cb.setChecked(entry.get('verified', False))
        self.badges_input.setText(', '.join(entry.get('badges', [])))
        self.undo_mgr.reset()
        self.undo_mgr.push(self._get_form_state())
        self._ignore_form_changes = False
        self._update_icon_preview(entry.get('id', ''))
        self._load_md_content(entry.get('id', ''))
        self.dm.modified = False
        self._update_title()

    def _update_current_item_in_tree(self):
        """Updates only the current item in the tree to avoid full refresh lag."""
        if self.current_cat is None or self.current_idx is None:
            return
        
        # Find the category item
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            ci = root.child(i)
            d = ci.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if d and d[0] == 'cat' and d[1] == self.current_cat:
                # Find the specific item
                if self.current_idx < ci.childCount():
                    item_widget = ci.child(self.current_idx)
                    entry = self.dm.data[self.current_cat][self.current_idx]
                    
                    # Update name with status icon
                    name = entry.get('name', '')
                    status = entry.get('link_status', 'pending')
                    if status == 'verified':
                        name = f'✅ {name}'
                    elif status == 'broken':
                        name = f'❌ {name}'
                    
                    item_widget.setText(0, name)
                    item_widget.setText(1, entry.get('id', ''))
                    
                    # Update icon
                    ip = os.path.join(ICONS_DIR, f'{entry.get("id", "")}.webp')
                    if os.path.exists(ip):
                        item_widget.setIcon(0, QIcon(ip))
                    else:
                        item_widget.setIcon(0, QIcon())
                break

    def _on_tree_rows_moved(self, parent, start, end, dest, row):
        ci = self.tree.currentItem()
        if not ci:
            return
        try:
            data = ci.data(0, QtCore.Qt.ItemDataRole.UserRole)
        except RuntimeError:
            return
        if not data or data[0] != 'item':
            return
        _, cat, old_idx = data
        parent_item = ci.parent()
        if not parent_item:
            return
        new_idx = parent_item.indexOfChild(ci)
        if new_idx < 0 or old_idx == new_idx:
            return
        items = self.dm.data[cat]
        item = items.pop(old_idx)
        items.insert(new_idx, item)
        self.current_idx = new_idx
        self.dm.modified = True
        self._update_title()
        self._on_tree_click(ci, 0)

        ci = self.tree.currentItem()
        if not ci:
            return
        try:
            data = ci.data(0, QtCore.Qt.ItemDataRole.UserRole)
        except RuntimeError:
            return
        if not data or data[0] != 'item':
            return
        _, cat, old_idx = data
        parent_item = ci.parent()
        if not parent_item:
            return
        new_idx = parent_item.indexOfChild(ci)
        if new_idx < 0 or old_idx == new_idx:
            return
        items = self.dm.data[cat]
        item = items.pop(old_idx)
        items.insert(new_idx, item)
        self.current_idx = new_idx
        self.dm.modified = True
        self._update_title()
        self._on_tree_click(ci, 0)

    def _clear_form(self):
        self._ignore_form_changes = True
        for w in [self.name_input, self.enlace_input, self.id_input, self.badges_input]:
            w.clear()
        self.info_input.clear()
        self.undo_mgr.reset()
        self._ignore_form_changes = False
        self.icon_preview.clear()
        self.icon_preview.setText('Sin icono')
        self.icon_info_label.setText('Selecciona un elemento para gestionar su icono')
        self.md_editor.clear()
        self.md_status.setText('')
        self.badges_warn.setVisible(False)
        self.md_stack.setCurrentIndex(0)
        self.btn_md_preview.setText('Vista previa')
        self.btn_md_preview.setIcon(QIcon.fromTheme('zoom-in'))
        self.dm.modified = False
        self._update_title()

    def _add_quick_badge(self, badge: str):
        current = self.badges_input.text()
        tags = [t.strip() for t in current.split(',') if t.strip()]
        if badge not in tags:
            tags.append(badge)
            self.badges_input.setText(', '.join(tags))

    def _on_badges_changed(self):
        self._mark_modified()
        text = self.badges_input.text()
        tags = [t.strip() for t in text.split(',') if t.strip()]
        warnings = []
        if len(tags) > 3:
            warnings.append('Máximo 3 etiquetas')
        over_14 = [t for t in tags if len(t) > 14]
        if over_14:
            warnings.append(f'{len(over_14)} etiqueta(s) superan los 14 caracteres')
        if warnings:
            self.badges_warn_text.setText('\n'.join(warnings))
            self.badges_warn.setVisible(True)
        else:
            self.badges_warn.setVisible(False)

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
            QtWidgets.QMessageBox.warning(self, 'Aviso', 'Selecciona un elemento primero')
            return
        entry = self.dm.data[self.current_cat][self.current_idx]
        item_id = entry.get('id', '')
        if not item_id:
            return
        r = QtWidgets.QMessageBox.question(
            self, 'Confirmar',
            f'¿Eliminar el icono de {item_id}?',
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        if r != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        if self.dm.remove_icon(item_id):
            self._update_icon_preview(item_id)
            self.status_bar.showMessage(f'Icono eliminado: {item_id}.webp', 3000)
        else:
            QtWidgets.QMessageBox.critical(self, 'Error', 'No se pudo eliminar el icono')

    def _on_sync_icon_name(self):
        if self.current_idx is None or not self.current_cat:
            return
        entry = self.dm.data[self.current_cat][self.current_idx]
        item_id = entry.get('id', '')
        name = entry.get('name', 'sin_nombre')
        if self.dm.rename_icon_by_name(item_id, name):
            self.status_bar.showMessage(f'Icono renombrado a {name}.webp', 3000)
            self._update_icon_preview(item_id)
        else:
            QtWidgets.QMessageBox.warning(self, 'Aviso', 'No se encontró la imagen original para renombrar')

    def _on_verify_icons(self):
        report = self.dm.verify_icons()
        msg = (
            f"<b>Análisis de Iconos:</b><br><br>"
            f"Total Elementos: {report['total_items']}<br>"
            f"Total Archivos .webp: {report['total_icons']}<br><br>"
            f"<span style='color:red;'>Faltantes: {len(report['missing'])}</span><br>"
            f"<span style='color:orange;'>Huérfanos: {len(report['orphans'])}</span>"
        )
        if report['missing'] or report['orphans']:
            msg += "<br><br><i>Revisa la consola para ver la lista detallada de IDs.</i>"
            logger.info("Missing icons: %s", report['missing'])
            logger.info("Orphan icons: %s", report['orphans'])
        else:
            msg += "<br><br><b>✅ Todo está sincronizado correctamente.</b>"
            
        QtWidgets.QMessageBox.information(self, 'Verificación de Iconos', msg)
        if self.current_idx is not None and self.current_cat:
            entry = self.dm.data[self.current_cat][self.current_idx]
            self._update_icon_preview(entry.get('id', ''))

    def _on_fix_icons(self):
        fixed = self.dm.fix_icons()
        self.status_bar.showMessage(f'Iconos reparados: {fixed}', 5000)
        if self.current_idx is not None and self.current_cat:
            entry = self.dm.data[self.current_cat][self.current_idx]
            self._update_icon_preview(entry.get('id', ''))

    def _load_md_content(self, item_id: str):
        is_preview = self.md_stack.currentIndex() == 1
        content = self.dm.load_md(item_id)
        if content is not None:
            self.md_editor.setPlainText(content)
            self.md_status.setText(f'{item_id}.md')
        else:
            self.md_editor.clear()
            self.md_status.setText('No hay .md')
        
        if is_preview:
            self._update_preview()
        else:
            self.md_stack.setCurrentIndex(0)
            self.btn_md_preview.setText('Vista previa')
            self.btn_md_preview.setIcon(QIcon.fromTheme('zoom-in'))

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
        r = QtWidgets.QMessageBox.question(
            self, 'Confirmar',
            f'¿Eliminar {item_id}.md?',
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        if r != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self.dm.delete_md(item_id)
        self.md_editor.clear()
        self.md_stack.setCurrentIndex(0)
        self.btn_md_preview.setText('Vista previa')
        self.btn_md_preview.setIcon(QIcon.fromTheme('zoom-in'))
        self.md_status.setText('.md eliminado')
        self.status_bar.showMessage(f'MD eliminado: {item_id}.md', 3000)

    def _toggle_md_preview(self):
        if self.md_stack.currentIndex() == 0:
            self._update_preview()
            self.md_stack.setCurrentIndex(1)
            self.btn_md_preview.setText('Editar')
            self.btn_md_preview.setIcon(QIcon.fromTheme('document-edit'))
        else:
            self.md_stack.setCurrentIndex(0)
            self.btn_md_preview.setText('Vista previa')
            self.btn_md_preview.setIcon(QIcon.fromTheme('zoom-in'))

    def _update_preview(self):
        text = self.md_editor.toPlainText()
        if not text.strip():
            self.preview_browser.setHtml(
                '<p style="color:#666; text-align:center; margin-top:20px;">El contenido markdown está vacío.</p>'
            )
            return
        html = self._render_markdown(text)
        style = (
            'body { background: #0d0d0f; color: #f4f4f7; font-family: "Inter", "Segoe UI", Roboto, sans-serif; '
            'padding: 20px; line-height: 1.6; font-size: 14px; }'
            'h1, h2, h3, h4, h5, h6 { color: #ff5e00; margin: 1.5em 0 0.6em; font-weight: 600; line-height: 1.3; }'
            'h1 { font-size: 2.2em; border-bottom: 2px solid #27272a; padding-bottom: 0.3em; }'
            'h2 { font-size: 1.7em; border-bottom: 1px solid #27272a; padding-bottom: 0.2em; }'
            'h3 { font-size: 1.4em; }'
            'a { color: #ff5e00; text-decoration: none; transition: color 0.2s; }'
            'a:hover { color: #e65500; text-decoration: underline; }'
            'img { max-width: 100%; border-radius: 10px; margin: 1.5em 0; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }'
            'code { background: #1c1c22; color: #ffb86c; padding: 3px 6px; border-radius: 6px; font-size: 0.9em; font-family: Consolas, monospace; }'
            'pre { background: #16161a; border: 1px solid #27272a; border-radius: 10px; padding: 1.2em; overflow-x: auto; margin: 1em 0; }'
            'pre code { background: none; color: #f4f4f7; padding: 0; font-size: 13px; }'
            'blockquote { margin: 1.5em 0; padding: 0.8em 1.2em; border-left: 4px solid #ff5e00; background: #16161a; color: #a1a1aa; border-radius: 0 10px 10px 0; }'
            'table { border-collapse: collapse; width: 100%; margin: 1.5em 0; background: #16161a; border-radius: 10px; overflow: hidden; }'
            'th, td { border: 1px solid #27272a; padding: 12px; text-align: left; }'
            'th { background: #1c1c22; color: #fff; font-weight: 600; }'
            'ul, ol { margin: 1em 0 1em 1.5em; }'
            'li { margin-bottom: 0.5em; }'
            'hr { border: none; border-top: 1px solid #27272a; margin: 2em 0; }'
            '.mermaid { background: #16161a; border-radius: 10px; padding: 1em; margin: 1em 0; overflow-x: auto; color: #a1a1aa; }'
            '.btn-download { display: inline-flex; align-items: center; justify-content: center; gap: 10px; '
            'padding: 12px 24px; border-radius: 10px; color: white !important; text-decoration: none !important; '
            'font-weight: 600; margin: 15px 0; transition: background 0.2s, transform 0.1s; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }'
            '.btn-download:hover { transform: translateY(-2px); }'
        )
        self.preview_browser.setHtml(f'<html><head><style>{style}</style></head><body>{html}</body></html>')


    @staticmethod
    def _render_markdown(text: str) -> str:
        lines = text.split('\n')
        html = ''
        in_code = False
        code_buf = []
        code_lang = ''
        in_list = False
        list_tag = ''

        i = 0
        while i < len(lines):
            line = lines[i]

            if line.startswith('```'):
                if not in_code:
                    in_code = True
                    code_lang = line[3:].strip()
                    code_buf = []
                    i += 1
                    continue
                else:
                    in_code = False
                    lang_class = f' class="language-{code_lang}"' if code_lang else ''
                    code_html = ''.join(code_buf)
                    html += f'<pre><code{lang_class}>{FoxWebManager._escape_html(code_html)}</code></pre>\n'
                    code_buf = []
                    i += 1
                    continue

            if in_code:
                code_buf.append(line + '\n')
                i += 1
                continue

            if line.strip() == '':
                if in_list:
                    html += f'</{list_tag}>\n'
                    in_list = False
                html += '\n'
                i += 1
                continue

            m = re.match(r'^(#{1,6})\s+(.+)$', line)
            if m:
                if in_list:
                    html += f'</{list_tag}>\n'; in_list = False
                level = len(m.group(1))
                html += f'<h{level}>{FoxWebManager._render_inline(m.group(2))}</h{level}>\n'
                i += 1; continue

            m = re.match(r'^>\s*(.*)$', line)
            if m:
                if in_list:
                    html += f'</{list_tag}>\n'; in_list = False
                html += f'<blockquote><p>{FoxWebManager._render_inline(m.group(1))}</p></blockquote>\n'
                i += 1; continue

            m = re.match(r'^(\d+)\.\s+(.+)$', line)
            if m:
                if in_list and list_tag != 'ol':
                    html += f'</{list_tag}>\n'; in_list = False
                if not in_list:
                    html += '<ol>\n'; in_list = True; list_tag = 'ol'
                html += f'<li>{FoxWebManager._render_inline(m.group(2))}</li>\n'
                i += 1; continue

            m = re.match(r'^[-*]\s+(.+)$', line)
            if m:
                if in_list and list_tag != 'ul':
                    html += f'</{list_tag}>\n'; in_list = False
                if not in_list:
                    html += '<ul>\n'; in_list = True; list_tag = 'ul'
                html += f'<li>{FoxWebManager._render_inline(m.group(1))}</li>\n'
                i += 1; continue

            m = re.match(r'^---+$', line)
            if m:
                if in_list:
                    html += f'</{list_tag}>\n'; in_list = False
                html += '<hr>\n'
                i += 1; continue

            m = re.match(r'^\|(.+)\|$', line)
            if m:
                if in_list:
                    html += f'</{list_tag}>\n'; in_list = False
                cells = [c.strip() for c in m.group(1).split('|')]
                is_header = i + 1 < len(lines) and re.match(r'^\|[-| :]+\|$', lines[i+1])
                if is_header:
                    html += '<table>\n<thead>\n<tr>'
                    for c in cells:
                        html += f'<th>{FoxWebManager._render_inline(c)}</th>'
                    html += '</tr>\n</thead>\n<tbody>\n'
                    i += 2
                    while i < len(lines):
                        m2 = re.match(r'^\|(.+)\|$', lines[i])
                        if not m2:
                            break
                        rc = [c.strip() for c in m2.group(1).split('|')]
                        html += '<tr>'
                        for c in rc:
                            html += f'<td>{FoxWebManager._render_inline(c)}</td>'
                        html += '</tr>\n'
                        i += 1
                    html += '</tbody>\n</table>\n'
                    continue
                else:
                    html += f'<p>{FoxWebManager._render_inline(line)}</p>\n'
                    i += 1; continue

            if in_list:
                html += f'</{list_tag}>\n'; in_list = False
            html += f'<p>{FoxWebManager._render_inline(line)}</p>\n'
            i += 1

        if in_code:
            html += f'<pre><code>{FoxWebManager._escape_html("".join(code_buf))}</code></pre>\n'
        if in_list:
            html += f'</{list_tag}>\n'

        return html

    @staticmethod
    def _render_inline(text: str) -> str:
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
        text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', r'<img src="\2" alt="\1">', text)
        text = re.sub(
            r'\[([^\]]+)\]\(([^)]+)\)',
            r'<a href="\2" target="_blank" rel="noopener">\1</a>',
            text
        )
        
        def replace_button(match):
            link_url = match.group(1)
            title = match.group(2)
            
            bg_color = '#d24500'
            text_color = '#fff'
            icon_svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640" width="20" height="20" style="vertical-align: middle; margin-right: 8px;"><path fill="currentColor" d="M352 96C352 78.3 337.7 64 320 64C302.3 64 288 78.3 288 96L288 306.7L246.6 265.3C234.1 252.8 213.8 252.8 201.3 265.3C188.8 277.8 188.8 298.1 201.3 310.6L297.3 406.6C309.8 419.1 330.1 419.1 342.6 406.6L438.6 310.6C451.1 298.1 451.1 277.8 438.6 265.3C426.1 252.8 405.8 252.8 393.3 265.3L352 306.7L352 96zM160 384C124.7 384 96 412.7 96 448L96 480C96 515.3 124.7 544 160 544L480 544C515.3 544 544 515.3 544 480L544 448C544 412.7 515.3 384 480 384L433.1 384L376.5 440.6C345.3 471.8 294.6 471.8 263.4 440.6L206.9 384L160 384zM464 440C477.3 440 488 450.7 488 464C488 477.3 477.3 488 464 488C450.7 488 440 477.3 440 464C440 450.7 450.7 440 464 440z"/></svg>'
            
            if 'github.com' in link_url:
                bg_color = '#000'
                text_color = '#fff'
                icon_svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640" width="20" height="20" style="vertical-align: middle; margin-right: 8px;"><path fill="currentColor" d="M280.5 426.5C214.5 418.5 168 371 168 309.5C168 284.5 177 257.5 192 239.5C185.5 223 186.5 188 194 173.5C214 171 241 181.5 257 196C276 190 296 187 320.5 187C345 187 365 190 383 195.5C398.5 181.5 426 171 446 173.5C453 187 454 222 447.5 239C463.5 258 472 283.5 472 309.5C472 371 425.5 417.5 358.5 426C375.5 437 387 461 387 488.5L387 540.5C387 555.5 399.5 564 414.5 558C505 523.5 576 433 576 321C576 179.5 461 64 319.5 64C178 64 64 179.5 64 321C64 432 134.5 524 229.5 558.5C243 563.5 256 554.5 256 541L256 501C249 504 240 506 232 506C199 506 179.5 488 165.5 454.5C160 441 154 433 142.5 431.5C136.5 431 134.5 428.5 134.5 425.5C134.5 419.5 144.5 415 154.5 415C169 415 181.5 424 194.5 442.5C204.5 457 215 463.5 227.5 463.5C240 463.5 248 459 259.5 447.5C268 439 274.5 431.5 280.5 426.5z"/></svg>'
            elif 'mediafire.com' in link_url:
                bg_color = '#07f'
                text_color = '#fff'
                icon_svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-6.8887712 -3.69853465 81.96659882 46.80035628" width="20" height="20" style="vertical-align: middle; margin-right: 8px;"><path fill="currentColor" d="m20.7 8.3a51.47 51.47 0 0 1 9.34 1c2.9.55 5.85 1.56 8.83 1.55 2.28 0 4.12-1.6 4.1-3.53s-1.85-3.57-4.17-3.56a13.35 13.35 0 0 0 -3.9.65c.33-.23.66-.47 1-.68a26.14 26.14 0 0 1 15.1-3.68c5.6.26 11.46 2 15.8 5.72a19.9 19.9 0 0 1 6.62 17.82 19.75 19.75 0 0 1 -12.17 15.07 24 24 0 0 1 -14.45.52c-6.2-1.58-11.64-5-17.48-7.54a46.86 46.86 0 0 0 -10.57-2.68h.05a9 9 0 0 0 4.1-.7c1.74-.83 1.73-2.83.83-4.3-1.07-1.73-3.23-2.44-5.1-3a24.36 24.36 0 0 0 -10-.48 15.06 15.06 0 0 0 -6.83 2.52 5.67 5.67 0 0 0 -1.8 2.2c3.08-8.53 9.2-7.57 13-9.9a2.16 2.16 0 0 0 -1.57-3.94 7.24 7.24 0 0 0 -2.92 1.46l-.85.65s3.04-5.17 13.04-5.17z"/></svg>'
            
            return f'<a href="{link_url}" style="background-color:{bg_color};color:{text_color};padding:10px 20px;border-radius:5px;text-decoration:none;display:inline-flex;align-items:center;gap:10px;margin:10px 0;font-weight:bold;" target="_blank" rel="nofollow noopener noreferrer">{icon_svg} {title}</a>'

        text = re.sub(
            r'\[button,\s*url="([^"]+)",\s*title="([^"]+)"\]',
            replace_button,
            text
        )
        text = re.sub(
            r'```mermaid\n?([\s\S]*?)```',
            r'<div class="mermaid">\1</div>',
            text
        )
        return text

    @staticmethod
    def _escape_html(text: str) -> str:
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;'))

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
        if self.auto_save_enabled:
            self.dm.save()
            self.status_bar.showMessage('Auto-guardado...', 1000)

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
        if self.auto_save_enabled:
            self.dm.save()
            self.status_bar.showMessage('Auto-guardado...', 1000)

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
        self._update_stats()
        self.status_bar.showMessage('IDs reordenados', 5000)
        if self.auto_save_enabled:
            self.dm.save()
            self.status_bar.showMessage('Auto-guardado...', 1000)

    def _on_add(self):
        if not self.current_cat:
            QtWidgets.QMessageBox.warning(self, 'Aviso', 'Selecciona una categoría primero')
            return
        new_id = self.dm.add_item(self.current_cat)
        if new_id is None:
            return
        self._refresh_tree()
        self._update_stats()
        self.status_bar.showMessage(f'Nuevo elemento creado (ID: {new_id})', 3000)
        self._update_title()
        if self.auto_save_enabled:
            self.dm.save()
            self.status_bar.showMessage('Auto-guardado...', 1000)

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
            self._update_stats()
            self.status_bar.showMessage('Elemento eliminado', 3000)
            if self.auto_save_enabled:
                self.dm.save()
                self.status_bar.showMessage('Auto-guardado...', 1000)

    def _on_save(self):
        if self.current_idx is not None and self.current_cat:
            self._save_current_item()
        if self.dm.save():
            self._update_current_item_in_tree()
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
            verified=self.verified_cb.isChecked(),
            badges=badges,
        )


    def _on_copy_item(self):
        if self.current_idx is None or not self.current_cat:
            return
        entry = self.dm.data[self.current_cat][self.current_idx]
        data = json.dumps(entry, ensure_ascii=False)
        QApplication.clipboard().setText(data)
        self.status_bar.showMessage(f'Copiado: {entry.get("name", "")}', 2000)

    def _on_auto_save_toggled(self, state):
        self.auto_save_enabled = (state == QtCore.Qt.CheckState.Checked.value)

    def _do_auto_save(self):
        if self.current_idx is not None and self.current_cat:
            self._save_current_item()
        if self.dm.save():
            self._update_current_item_in_tree()
            self._update_title()
            self.status_bar.showMessage('Auto-guardado...', 1000)

    def _on_paste_item(self):
        if not self.current_cat:
            QtWidgets.QMessageBox.warning(self, 'Aviso', 'Selecciona una categoría primero')
            return
        try:
            data = json.loads(QApplication.clipboard().text())
        except (json.JSONDecodeError, TypeError):
            QtWidgets.QMessageBox.warning(self, 'Error', 'El portapapeles no contiene datos válidos')
            return
        if not isinstance(data, dict):
            QtWidgets.QMessageBox.warning(self, 'Error', 'Datos inválidos en el portapapeles')
            return
        new_id = self.dm.generate_next_id()
        data['id'] = new_id
        data['name'] = data.get('name', 'Pegado') + ' (copia)'
        self.dm.data[self.current_cat].append(data)
        self.dm.modified = True
        self._refresh_tree()
        self._update_stats()
        self.status_bar.showMessage(f'Pegado en {self.current_cat}', 3000)

    def _on_validate_link(self):
        url = self.enlace_input.text().strip()
        if not url or url == '#':
            QtWidgets.QMessageBox.warning(self, 'Aviso', 'No hay enlace que validar')
            return
        if url.startswith('http://') or url.startswith('https://'):
            self.status_bar.showMessage('Validando enlace...', 0)
            self.validator = LinkValidator(url)
            self.validator.finished.connect(lambda msg: self.status_bar.showMessage(msg, 5000))
            self.validator.start()
        else:
            self.status_bar.showMessage('Enlace cifrado — no se puede validar directamente', 5000)

    def _on_theme_changed(self, style_name):
        QApplication.setStyle(style_name)
        self.settings.setValue('theme', style_name)
        self.status_bar.showMessage(f'Tema cambiado a {style_name}', 3000)

    def _on_preferences(self):
        dlg = PreferencesDialog(self)
        if dlg.exec():
            vals = dlg.get_values()
            self.auto_save_enabled = vals['auto_save']
            self.timeout_pref = vals['timeout']
            
            # Apply theme immediately
            theme = vals['theme']
            QApplication.setStyle(theme)
            self.status_bar.showMessage('Preferencias actualizadas', 3000)

    def _update_link_status_message(self, name, status):
        icon = '✅' if status == 'verified' else '❌'
        self.status_bar.showMessage(f'Verificando: {name} {icon}', 0)

    def _update_verification_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_bar.showMessage(f'Verificando enlaces... {current}/{total}', 0)

    def _on_verification_finished(self, verified, broken):
        self.btn_verify_all.setEnabled(True)
        self.progress_bar.setVisible(False)
        self._refresh_tree()
        self.dm.save()
        QtWidgets.QMessageBox.information(
            self, 'Verificación Completada',
            f'Se han verificado todos los enlaces.\n\n'
            f'✅ Verificados: {verified}\n'
            f'❌ Rotos/Incorrectos: {broken}'
        )
        self.status_bar.showMessage('Verificación masiva finalizada', 5000)

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
    app.setStyle('Fusion')
    w = FoxWebManager()
    w.show()
    sys.exit(app.exec())
