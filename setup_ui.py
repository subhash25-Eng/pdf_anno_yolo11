### setup_ui.py
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWidgets import (
    QMenuBar, QMenu, QAction, QLabel, QPushButton, QSpinBox,
    QScrollArea, QVBoxLayout, QWidget, QSplitter, QHBoxLayout, QTextBrowser, QPlainTextEdit, QDialog, QShortcut, QFrame
)
from PyQt5.QtCore import Qt
from richtexteditor import RichTextEditor
from configParser import config_parser
import json
from xml_source_viewer import XMLSourceViewer


def setup_menu_bar(main_window):
    """Setup menu bar for PDF Viewer"""
    menu_bar = main_window.menuBar()

    # File menu
    file_menu = menu_bar.addMenu("File")
    open_action = QAction("New", main_window)
    open_action.triggered.connect(main_window.open_pdf)
    file_menu.addAction(open_action)

    # --- "Open" loads zones if json exists ---
    open_action = QAction("Open", main_window)
    open_action.triggered.connect(main_window.open_pdf_with_zones_if_available)
    file_menu.addAction(open_action)

    save_action = QAction("Save",main_window)
    save_action.triggered.connect(main_window.save_zones_to_json)
    file_menu.addAction(save_action)

    # Edit menu
    edit_menu = menu_bar.addMenu("Edit")
    # main_window.create_zone_action = QAction("Create Zone", main_window)
    # # main_window.create_zone_action.setCheckable(True)
    # main_window.create_zone_action.setShortcut("z")
    # main_window.create_zone_action.triggered.connect(main_window.toggle_creation_mode)
    # edit_menu.addAction(main_window.create_zone_action)

    # zone_shortcut = QShortcut(QKeySequence("Z"), main_window)
    # zone_shortcut.activated.connect(main_window.toggle_creation_mode)

    # undo_action = QAction("Undo", main_window)
    # undo_action.setShortcut("Ctrl+Z")
    # undo_action.triggered.connect(main_window.undo_last_action)
    # edit_menu.addAction(undo_action)

    # View menu
    view_menu = menu_bar.addMenu("View")
    text_view_action = QAction("Text View", main_window)
    text_view_action.triggered.connect(main_window.show_text_viewer)
    view_menu.addAction(text_view_action)

    html_source_action = QAction("HTML Source", main_window)
    html_source_action.triggered.connect(main_window.show_html_source_viewer)
    view_menu.addAction(html_source_action)

    # xml_source_action = QAction("XML Source", main_window)
    # xml_source_action.triggered.connect(main_window.show_xml_editor)  # Direct connection
    # view_menu.addAction(xml_source_action)

    # Help menu
    help_menu = menu_bar.addMenu("Help")

    shortcuts_action = QAction("Keyboard Shortcuts", main_window)
    shortcuts_action.triggered.connect(lambda: show_shortcuts_dialog(main_window))
    help_menu.addAction(shortcuts_action)

    toggle_sequence_action = QAction("Hide Sequence Circle", main_window)
    toggle_sequence_action.triggered.connect(main_window.toggle_sequence_circles)
    menu_bar.addAction(toggle_sequence_action)
    main_window.toggle_sequence_action = toggle_sequence_action

    # Direct Exit menu item
    exit_action = QAction("Exit", main_window)
    exit_action.setShortcut("Ctrl+Q")
    exit_action.triggered.connect(main_window.close)
    menu_bar.addAction(exit_action)

def setup_main_layout(main_window):
    """Setup main layout including PDF viewer and rich text editor"""
    # Create scrollable page layout
    main_window.page_layout = QVBoxLayout()
    main_window.page_layout.setAlignment(Qt.AlignTop)
    main_window.page_layout.setSpacing(5)

    main_window.page_container = QWidget()
    main_window.page_container.setLayout(main_window.page_layout)

    # Create scroll widget and layout
    main_window.scroll_widget = QWidget()
    main_window.scroll_layout = QVBoxLayout(main_window.scroll_widget)
    main_window.scroll_layout.setContentsMargins(0, 0, 0, 0)
    main_window.scroll_layout.setSpacing(0)

    # Attach to scroll area
    main_window.scroll_area = QScrollArea()
    main_window.scroll_area.setWidgetResizable(True)
    main_window.scroll_area.setWidget(main_window.scroll_widget)

    # Setup initial editor and splitter
    main_window.rich_text_editor = RichTextEditor()
    main_window.text_display = main_window.rich_text_editor  # Track current
    main_window.splitter = QSplitter(Qt.Horizontal)
    main_window.splitter.addWidget(main_window.scroll_area)
    main_window.splitter.addWidget(main_window.text_display)
    main_window.splitter.setSizes([800, 400])

    # Create main central widget and layout
    central_widget = QWidget()
    main_layout = QVBoxLayout()
    main_layout.setContentsMargins(0, 0, 0, 0)
    main_layout.setSpacing(0)
    main_layout.addWidget(main_window.splitter)
    central_widget.setLayout(main_layout)
    main_window.setCentralWidget(central_widget)

    # --- Setup navigation/status bar ---
    nav_container = QWidget()
    nav_layout = QHBoxLayout(nav_container)
    nav_layout.setContentsMargins(0, 0, 0, 0)
    nav_layout.setSpacing(10)

    main_window.prev_btn = QPushButton("◀ Previous")
    nav_layout.addWidget(main_window.prev_btn)

    nav_layout.addWidget(QLabel("Page:"))

    main_window.page_spinbox = QSpinBox()
    main_window.page_spinbox.setMinimum(1)
    main_window.page_spinbox.setMaximum(1000)
    main_window.page_spinbox.setValue(0)
    nav_layout.addWidget(main_window.page_spinbox)

    main_window.page_label = QLabel("of 0")
    nav_layout.addWidget(main_window.page_label)

    main_window.next_btn = QPushButton("Next ▶")
    nav_layout.addWidget(main_window.next_btn)

    main_window.zoom_out_btn = QPushButton("🔍−")
    main_window.zoom_out_btn.clicked.connect(main_window.zoom_out)
    nav_layout.addWidget(main_window.zoom_out_btn)

    main_window.zoom_label = QLabel("100%")
    main_window.zoom_label.setMinimumWidth(50)
    main_window.zoom_label.setAlignment(Qt.AlignCenter)
    nav_layout.addWidget(main_window.zoom_label)

    main_window.zoom_in_btn = QPushButton("🔍+")
    main_window.zoom_in_btn.clicked.connect(main_window.zoom_in)
    nav_layout.addWidget(main_window.zoom_in_btn)

    nav_container.setMaximumWidth(600)
    status_bar = main_window.statusBar()
    status_bar.addWidget(nav_container)

    # Additional info
    main_window.page_info_label = QLabel("No document")
    main_window.memory_info_label = QLabel("Memory: 0/0")
    main_window.performance_label = QLabel("Ready")

    status_bar.addWidget(main_window.page_info_label)
    status_bar.addPermanentWidget(main_window.memory_info_label)
    status_bar.addPermanentWidget(main_window.performance_label)

    main_window.page_info_label.setToolTip("Current page and status")
    main_window.memory_info_label.setToolTip("Memory usage info")
    main_window.performance_label.setToolTip("App performance or state")

    main_window.prev_btn.clicked.connect(main_window.go_to_previous_page)
    main_window.next_btn.clicked.connect(main_window.go_to_next_page)
    main_window.page_spinbox.valueChanged.connect(main_window.go_to_page)


def show_shortcuts_dialog(parent):
    from PyQt5.QtWidgets import (
        QDialog, QVBoxLayout, QLabel, QHBoxLayout,
        QPushButton, QScrollArea, QWidget, QFrame
    )
    from PyQt5.QtCore import Qt

    zone_json_str = config_parser.zones_type
    zone_mappings = json.loads(zone_json_str)
    shortcuts = [
        ("Create Zone", "Z"),
        ("Undo", "Ctrl+Z"),
        ("Exit", "Ctrl+Q"),
        ("Next Page", "→ / Down Arrow"),
        ("Previous Page", "← / Up Arrow"),
        ("Zoom In", "Ctrl + +"),
        ("Zoom Out", "Ctrl + -"),
        ("Text View", "View → Text View"),
        ("HTML Source View", "View → HTML Source"),
    ]
    for mapping in zone_mappings:
        zone_type = mapping.get("type")
        shortcut_key = mapping.get("shortcut_key")
        shortcuts.append((zone_type, shortcut_key))



    dialog = QDialog(parent)
    dialog.setWindowTitle("Keyboard Shortcuts")
    dialog.setFixedSize(500, 600)
    dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)

    layout = QVBoxLayout(dialog)
    layout.setSpacing(18)
    layout.setContentsMargins(28, 25, 28, 20)

    # Header with icon and title
    header_layout = QHBoxLayout()

    icon_label = QLabel("⌨️")
    icon_label.setStyleSheet("font-size: 30px; margin-right: 8px;")

    title_label = QLabel("Keyboard Shortcuts")
    title_label.setStyleSheet("font-size: 22px; font-weight: 700; color: #1a202c;")

    header_layout.addWidget(icon_label)
    header_layout.addWidget(title_label)
    header_layout.addStretch()
    layout.addLayout(header_layout)

    subtitle = QLabel("Master these shortcuts to boost your productivity")
    subtitle.setStyleSheet("font-size: 13px; color: #718096;")
    layout.addWidget(subtitle)

    # Scrollable area
    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_area.setStyleSheet("""
        QScrollArea {
            background: transparent;
            border: none;
        }
    """)
    scroll_widget = QWidget()
    scroll_layout = QVBoxLayout(scroll_widget)
    scroll_layout.setSpacing(10)
    scroll_layout.setContentsMargins(10, 10, 10, 10)

    for name, key in shortcuts:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
            }
            QFrame:hover {
                background: #f7fafc;
                border: 1px solid #cbd5e0;
            }
        """)
        inner_layout = QHBoxLayout(frame)
        inner_layout.setContentsMargins(16, 10, 16, 10)

        name_label = QLabel(name)
        name_label.setStyleSheet("font-size: 14px; color: #2d3748; font-weight: 500;")

        key_label = QLabel(key)
        key_label.setStyleSheet("""
            background: #edf2f7;
            color: #2d3748;
            font-family: 'Courier New', monospace;
            font-size: 13px;
            font-weight: 600;
            padding: 6px 12px;
            border: 1px solid #cbd5e0;
            border-radius: 6px;
        """)
        key_label.setAlignment(Qt.AlignCenter)

        inner_layout.addWidget(name_label)
        inner_layout.addStretch()
        inner_layout.addWidget(key_label)
        scroll_layout.addWidget(frame)

    scroll_area.setWidget(scroll_widget)
    layout.addWidget(scroll_area)
    scroll_card = QFrame()
    scroll_card.setStyleSheet("""
        QFrame {
            background: white;
            border-radius: 10px;
            border: 1px solid #e2e8f0;
        }
    """)
    scroll_card_layout = QVBoxLayout(scroll_card)
    scroll_card_layout.addWidget(scroll_area)
    layout.addWidget(scroll_card)

    # Button
    button_layout = QHBoxLayout()
    button_layout.addStretch()

    close_button = QPushButton("✨ Got it!")
    close_button.clicked.connect(dialog.accept)
    close_button.setCursor(Qt.PointingHandCursor)
    close_button.setStyleSheet("""
        QPushButton {
            background-color: #667eea;
            color: white;
            border-radius: 8px;
            padding: 10px 24px;
            font-size: 14px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #5a67d8;
        }
        QPushButton:pressed {
            background-color: #4c51bf;
        }
    """)

    dialog.setStyleSheet("""
        QDialog {
            background-color: #f9fafb;
            border-radius: 12px;
        }
    """)

    button_layout.addWidget(close_button)
    layout.addLayout(button_layout)

    dialog.setGraphicsEffect(create_shadow_effect())

    # Center the dialog on parent
    if parent:
        geo = parent.geometry()
        x = geo.x() + (geo.width() - dialog.width()) // 2
        y = geo.y() + (geo.height() - dialog.height()) // 2
        dialog.move(x, y)
    layout.addSpacing(10)
    dialog.adjustSize()
    dialog.exec_()


def create_shadow_effect():
    from PyQt5.QtWidgets import QGraphicsDropShadowEffect
    from PyQt5.QtGui import QColor

    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(20)
    shadow.setColor(QColor(0, 0, 0, 60))
    shadow.setOffset(0, 4)
    return shadow





