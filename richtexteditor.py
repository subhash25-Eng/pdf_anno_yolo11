import re

from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtGui import QFont, QColor, QTextCharFormat, QTextCursor, QIcon, QPixmap, QPainter
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QTextEdit, QAction, QToolBar,
                             QLabel, QSpinBox, QComboBox, QColorDialog, QFontDialog,
                             QApplication, QMainWindow, QPushButton)


class RichTextEditor(QWidget):
    """Enhanced rich text editor with comprehensive formatting features"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        """Setup the enhanced rich text editor UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)

        # Setup toolbar
        self.setup_toolbar()
        layout.addWidget(self.toolbar)

        # Setup text editor
        self.text_editor = QTextEdit()
        self.text_editor.setReadOnly(False)

        # Set up rich text formatting
        font = QFont("Arial", 11)
        self.text_editor.setFont(font)
        self.text_editor.setPlaceholderText("Start typing your rich text content here...")

        # Connect signals
        self.text_editor.cursorPositionChanged.connect(self.update_toolbar_states)
        self.text_editor.selectionChanged.connect(self.update_toolbar_states)

        layout.addWidget(self.text_editor)
        self.setLayout(layout)

    def create_colored_icon(self, color, size=(16, 16)):
        """Create a colored square icon"""
        pixmap = QPixmap(*size)
        pixmap.fill(color)
        return QIcon(pixmap)

    def setup_toolbar(self):
        """Setup comprehensive formatting toolbar"""
        self.toolbar = QToolBar("Text Formatting")
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)

        # === BASIC FORMATTING ===
        # Bold
        self.bold_action = QAction("B", self)
        self.bold_action.setCheckable(True)
        self.bold_action.setShortcut("Ctrl+B")
        self.bold_action.triggered.connect(self.toggle_bold)
        self.bold_action.setToolTip("Bold (Ctrl+B)")
        self.toolbar.addAction(self.bold_action)

        # Italic
        self.italic_action = QAction("I", self)
        self.italic_action.setCheckable(True)
        self.italic_action.setShortcut("Ctrl+I")
        self.italic_action.triggered.connect(self.toggle_italic)
        self.italic_action.setToolTip("Italic (Ctrl+I)")
        self.toolbar.addAction(self.italic_action)

        # Underline
        self.underline_action = QAction("U", self)
        self.underline_action.setCheckable(True)
        self.underline_action.setShortcut("Ctrl+U")
        self.underline_action.triggered.connect(self.toggle_underline)
        self.underline_action.setToolTip("Underline (Ctrl+U)")
        self.toolbar.addAction(self.underline_action)

        # Strikethrough
        self.strikethrough_action = QAction("S", self)
        self.strikethrough_action.setCheckable(True)
        self.strikethrough_action.triggered.connect(self.toggle_strikethrough)
        self.strikethrough_action.setToolTip("Strikethrough")
        self.toolbar.addAction(self.strikethrough_action)

        self.toolbar.addSeparator()

        # === FONT CONTROLS ===
        # Font family
        font_family_label = QLabel("Font:")
        self.toolbar.addWidget(font_family_label)

        self.font_combo = QComboBox()
        self.font_combo.addItems(['Arial', 'Times New Roman', 'Courier New', 'Helvetica',
                                  'Georgia', 'Verdana', 'Calibri', 'Comic Sans MS'])
        self.font_combo.currentTextChanged.connect(self.change_font_family)
        self.toolbar.addWidget(self.font_combo)

        # Font size
        font_size_label = QLabel("Size:")
        self.toolbar.addWidget(font_size_label)

        self.font_size_spinbox = QSpinBox()
        self.font_size_spinbox.setMinimum(6)
        self.font_size_spinbox.setMaximum(144)
        self.font_size_spinbox.setValue(11)
        self.font_size_spinbox.valueChanged.connect(self.change_font_size)
        self.toolbar.addWidget(self.font_size_spinbox)

        # Font dialog button
        font_dialog_action = QAction("Font...", self)
        font_dialog_action.triggered.connect(self.open_font_dialog)
        font_dialog_action.setToolTip("Open Font Dialog")
        self.toolbar.addAction(font_dialog_action)

        self.toolbar.addSeparator()

        # === COLOR CONTROLS ===
        # Text color
        self.text_color_action = QAction("A", self)
        self.text_color_action.setIcon(self.create_colored_icon(QColor("black")))
        self.text_color_action.triggered.connect(self.change_text_color)
        self.text_color_action.setToolTip("Text Color")
        self.toolbar.addAction(self.text_color_action)

        # Background color
        self.bg_color_action = QAction("H", self)
        self.bg_color_action.setIcon(self.create_colored_icon(QColor("yellow")))
        self.bg_color_action.triggered.connect(self.change_background_color)
        self.bg_color_action.setToolTip("Highlight Color")
        self.toolbar.addAction(self.bg_color_action)

        self.toolbar.addSeparator()

        # === ALIGNMENT ===
        # Left align
        self.align_left_action = QAction("≡", self)
        self.align_left_action.setCheckable(True)
        self.align_left_action.triggered.connect(lambda: self.set_alignment(Qt.AlignLeft))
        self.align_left_action.setToolTip("Align Left")
        self.toolbar.addAction(self.align_left_action)

        # Center align
        self.align_center_action = QAction("≣", self)
        self.align_center_action.setCheckable(True)
        self.align_center_action.triggered.connect(lambda: self.set_alignment(Qt.AlignCenter))
        self.align_center_action.setToolTip("Align Center")
        self.toolbar.addAction(self.align_center_action)

        # Right align
        self.align_right_action = QAction("≡", self)
        self.align_right_action.setCheckable(True)
        self.align_right_action.triggered.connect(lambda: self.set_alignment(Qt.AlignRight))
        self.align_right_action.setToolTip("Align Right")
        self.toolbar.addAction(self.align_right_action)

        # Justify
        self.align_justify_action = QAction("≣", self)
        self.align_justify_action.setCheckable(True)
        self.align_justify_action.triggered.connect(lambda: self.set_alignment(Qt.AlignJustify))
        self.align_justify_action.setToolTip("Justify")
        self.toolbar.addAction(self.align_justify_action)

        self.toolbar.addSeparator()

        # === LISTS ===
        # Bullet list
        bullet_list_action = QAction("• List", self)
        bullet_list_action.triggered.connect(self.insert_bullet_list)
        bullet_list_action.setToolTip("Bullet List")
        self.toolbar.addAction(bullet_list_action)

        # Numbered list
        numbered_list_action = QAction("1. List", self)
        numbered_list_action.triggered.connect(self.insert_numbered_list)
        numbered_list_action.setToolTip("Numbered List")
        self.toolbar.addAction(numbered_list_action)

        self.toolbar.addSeparator()

        # === ADVANCED FEATURES ===
        # Insert link
        link_action = QAction("Link", self)
        link_action.triggered.connect(self.insert_link)
        link_action.setToolTip("Insert Hyperlink")
        self.toolbar.addAction(link_action)

        # Insert horizontal rule
        hr_action = QAction("HR", self)
        hr_action.triggered.connect(self.insert_horizontal_rule)
        hr_action.setToolTip("Insert Horizontal Rule")
        self.toolbar.addAction(hr_action)

        self.toolbar.addSeparator()

        # === UTILITY ===
        # Clear formatting
        clear_format_action = QAction("Clear", self)
        clear_format_action.triggered.connect(self.clear_formatting)
        clear_format_action.setToolTip("Clear Formatting")
        self.toolbar.addAction(clear_format_action)

        # Apply toolbar styles
        self.toolbar.setStyleSheet("""
            QToolBar {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                padding: 4px;
                spacing: 2px;
            }
            QAction {
                font-weight: bold;
                padding: 6px 10px;
                margin: 1px;
                border: 1px solid transparent;
                border-radius: 3px;
            }
            QAction:hover {
                background-color: #e9ecef;
                border-color: #adb5bd;
            }
            QAction:checked {
                background-color: #007bff;
                color: white;
            }
            QLabel {
                color: #495057;
                font-weight: bold;
                margin: 0 5px;
            }
            QSpinBox, QComboBox {
                padding: 2px 5px;
                border: 1px solid #ced4da;
                border-radius: 3px;
            }
        """)

    def update_toolbar_states(self):
        """Update toolbar button states based on current cursor position"""
        fmt = self.text_editor.currentCharFormat()
        cursor = self.text_editor.textCursor()

        # Update formatting buttons
        self.bold_action.setChecked(fmt.fontWeight() == QFont.Bold)
        self.italic_action.setChecked(fmt.fontItalic())
        self.underline_action.setChecked(fmt.fontUnderline())
        self.strikethrough_action.setChecked(fmt.fontStrikeOut())

        # Update font controls
        if fmt.fontPointSize() > 0:
            self.font_size_spinbox.blockSignals(True)
            self.font_size_spinbox.setValue(int(fmt.fontPointSize()))
            self.font_size_spinbox.blockSignals(False)

        if fmt.fontFamily():
            self.font_combo.blockSignals(True)
            font_family = fmt.fontFamily()
            index = self.font_combo.findText(font_family)
            if index >= 0:
                self.font_combo.setCurrentIndex(index)
            self.font_combo.blockSignals(False)

        # Update alignment buttons
        alignment = cursor.blockFormat().alignment()
        self.align_left_action.setChecked(alignment == Qt.AlignLeft or alignment == 0)
        self.align_center_action.setChecked(alignment == Qt.AlignCenter)
        self.align_right_action.setChecked(alignment == Qt.AlignRight)
        self.align_justify_action.setChecked(alignment == Qt.AlignJustify)

    # === BASIC FORMATTING METHODS ===

    def get_pdf_viewer(self):
        parent = self.parent()
        while parent:
            if hasattr(parent, "zones_data_by_page"):
                return parent
            parent = parent.parent()
        return None

    def find_zone_id_for_text(self, selected_text, html_content):
        """Find the paragraph zone ID that contains the selected text"""
        import re

        # Normalize the selected text - remove extra whitespace and newlines
        normalized_selected = re.sub(r'\s+', ' ', selected_text.strip())

        #print(f"Looking for normalized text: '{normalized_selected}'")

        # Look for zone IDs first
        zone_ids = re.findall(r'id="(pz\d+-\d+)"', html_content)
        #print(f"zone_ids {zone_ids}")

        for zone_id in zone_ids:
            # Updated pattern to capture content between paragraph tags with specific zone ID
            zone_pattern = f'<p[^>]*id="{zone_id}"[^>]*>(.*?)</p>'
            zone_match = re.search(zone_pattern, html_content, re.DOTALL)

            if zone_match:
                zone_content = zone_match.group(1)
                # Remove HTML tags and normalize whitespace
                clean_content = re.sub(r'<[^>]+>', '', zone_content)
                normalized_content = re.sub(r'\s+', ' ', clean_content.strip())

                print(f"Zone {zone_id} content: '{normalized_content}'")

                # Check if normalized selected text is in normalized zone content
                if normalized_selected in normalized_content:
                    print(f"Found zone ID: {zone_id} for text: '{normalized_selected}'")
                    return zone_id

        print(f"No zone ID found for text: '{normalized_selected}'")
        return None

    def toggle_bold(self):
        pdf_viewer = self.get_pdf_viewer()
        if not pdf_viewer:
            return

        current_page = pdf_viewer.current_page
        current_zones = pdf_viewer.zones_data_by_page.get(current_page, [])
        selected_text = self.text_editor.textCursor().selectedText().strip()
        print(f"current_zones {current_zones}")
        import re
        def normalize(text):
            return re.sub(r'\s+', ' ', text).strip()
        normalized_selected = normalize(selected_text)

        for zone in current_zones:
            zone_text = zone.get("text", "")
            normalized_zone_text = normalize(zone_text)

            if normalized_selected in normalized_zone_text:
                zone_id = zone.get("block_id") or zone.get("span_id")
                print(f"✅ Matched Zone ID: {zone_id}")
                current_bold = zone["feats"].get("_N_font_is_bold", False)
                zone["feats"]["_N_font_is_bold"] = not current_bold
                pdf_viewer.call_display_page_content()
                break
            else:
                print(f"❌ No match for: {normalized_selected} in {normalized_zone_text}")

        # === Toggle bold formatting in QTextEdit ===
        if self.text_editor.fontWeight() == QFont.Bold:
            self.text_editor.setFontWeight(QFont.Normal)
        else:
            self.text_editor.setFontWeight(QFont.Bold)

    def toggle_italic(self):
        pdf_viewer = self.get_pdf_viewer()
        if not pdf_viewer:
            return

        current_page = pdf_viewer.current_page
        current_zones = pdf_viewer.zones_data_by_page.get(current_page, [])
        selected_text = self.text_editor.textCursor().selectedText().strip()
        print(f"current_zones {current_zones}")
        import re
        def normalize(text):
            return re.sub(r'\s+', ' ', text).strip()

        normalized_selected = normalize(selected_text)

        for zone in current_zones:
            zone_text = zone.get("text", "")
            normalized_zone_text = normalize(zone_text)

            if normalized_selected in normalized_zone_text:
                zone_id = zone.get("block_id") or zone.get("span_id")
                print(f"✅ Matched Zone ID: {zone_id}")
                current_italic = zone["feats"].get("_N_font_is_italic", False)
                zone["feats"]["_N_font_is_italic"] = not current_italic
                pdf_viewer.call_display_page_content()
                break
            else:
                print(f"❌ No match for: {normalized_selected} in {normalized_zone_text}")
        """Toggle italic formatting"""
        self.text_editor.setFontItalic(not self.text_editor.fontItalic())

    def toggle_underline(self):
        """Toggle underline formatting"""
        self.text_editor.setFontUnderline(not self.text_editor.fontUnderline())

    def toggle_strikethrough(self):
        """Toggle strikethrough formatting"""
        fmt = self.text_editor.currentCharFormat()
        fmt.setFontStrikeOut(not fmt.fontStrikeOut())
        self.text_editor.setCurrentCharFormat(fmt)

    def change_font_size(self, size):
        """Change font size"""
        self.text_editor.setFontPointSize(size)

    def change_font_family(self, family):
        """Change font family"""
        self.text_editor.setFontFamily(family)

    def open_font_dialog(self):
        """Open font selection dialog"""
        font, ok = QFontDialog.getFont(self.text_editor.currentFont(), self)
        if ok:
            self.text_editor.setCurrentFont(font)

    # === COLOR METHODS ===
    def change_text_color(self):
        """Change text color"""
        color = QColorDialog.getColor(Qt.black, self)
        if color.isValid():
            self.text_editor.setTextColor(color)
            # Update icon color
            self.text_color_action.setIcon(self.create_colored_icon(color))

    def change_background_color(self):
        """Change text background color"""
        color = QColorDialog.getColor(Qt.yellow, self)
        if color.isValid():
            self.text_editor.setTextBackgroundColor(color)
            # Update icon color
            self.bg_color_action.setIcon(self.create_colored_icon(color))

    # === ALIGNMENT METHODS ===
    def set_alignment(self, alignment):
        """Set text alignment"""
        self.text_editor.setAlignment(alignment)

    # === LIST METHODS ===
    def insert_bullet_list(self):
        """Insert or toggle bullet list"""
        cursor = self.text_editor.textCursor()

        # Create bullet list format
        list_format = cursor.currentList()
        if list_format and list_format.style() == 1:  # Already a bullet list
            # Remove from list
            cursor.currentList().remove(cursor.block())
        else:
            # Add to bullet list
            cursor.createList(1)  # QTextListFormat.ListDisc

    def insert_numbered_list(self):
        """Insert or toggle numbered list"""
        cursor = self.text_editor.textCursor()

        # Create numbered list format
        list_format = cursor.currentList()
        if list_format and list_format.style() == 2:  # Already a numbered list
            # Remove from list
            cursor.currentList().remove(cursor.block())
        else:
            # Add to numbered list
            cursor.createList(2)  # QTextListFormat.ListDecimal

    # === ADVANCED METHODS ===
    def insert_link(self):
        """Insert a hyperlink"""
        cursor = self.text_editor.textCursor()

        # Simple implementation - in a real app, you'd want a dialog
        link_text = "Link Text"
        link_url = "https://example.com"

        # Create hyperlink format
        fmt = QTextCharFormat()
        fmt.setAnchor(True)
        fmt.setAnchorHref(link_url)
        fmt.setForeground(QColor("blue"))
        fmt.setFontUnderline(True)

        cursor.insertText(link_text, fmt)

    def insert_horizontal_rule(self):
        """Insert horizontal rule"""
        cursor = self.text_editor.textCursor()
        cursor.insertHtml("<hr>")

    def clear_formatting(self):
        """Clear all formatting from selected text"""
        cursor = self.text_editor.textCursor()
        if cursor.hasSelection():
            # Clear formatting for selection
            fmt = QTextCharFormat()
            cursor.setCharFormat(fmt)
        else:
            # Reset current format
            self.text_editor.setCurrentCharFormat(QTextCharFormat())

    # === CONTENT METHODS ===
    def set_html(self, html_content):
        """Set HTML content in the editor"""
        self.text_editor.setHtml(html_content)

    def get_html(self):
        """Get HTML content from the editor"""
        return self.text_editor.toHtml()

    def set_plain_text(self, text):
        """Set plain text content"""
        self.text_editor.setPlainText(text)

    def get_plain_text(self):
        """Get plain text content"""
        return self.text_editor.toPlainText()
    def handle_text_change(self):
        block_found = False
        pdf_viewer = self.get_pdf_viewer()
        if not pdf_viewer:
            return

        current_page = pdf_viewer.current_page
        zones = pdf_viewer.zones_data_by_page.get(current_page, [])
        # current_html = self.text_editor.toHtml()

        cursor = self.text_editor.textCursor()
        block_text = cursor.block().text().strip()
        print("block_text++++++++++",block_text)
        def normalize(text):
            return re.sub(r'\s+', ' ', text).strip()

        normalized_block = normalize(block_text)

        for zone in zones:
            zone_text = zone.get("text", "")
            normalized_zone = normalize(zone_text)

            if normalized_block in normalized_zone:
                block_found = True
            elif normalized_zone in normalized_block:
                block_found = True
            if block_found:
                zone_id = zone.get("block_id")
                print(f"Modified text matches zone: {zone_id}")
                zone["text"] = block_text
                break

        print("No matching zone found for modified text.")
        return None
