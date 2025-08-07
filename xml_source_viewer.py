from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTextEdit,
                             QPushButton, QLabel, QMessageBox, QFileDialog, QWidget)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor
from PyQt5.Qsci import QsciScintilla, QsciLexerXML
import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom
import json
from html import escape


class XMLSourceViewer(QDialog):  # Changed back to QDialog for proper modal behavior
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pdf_viewer = parent
        self.setWindowTitle("XML Source Editor")

        # Get data from parent if available
        if parent:
            self.current_page = getattr(parent, 'current_page', 0)
            self.zones_data_by_page = getattr(parent, 'zones_data_by_page', {})
            self.zones_data = getattr(parent, 'zones_data', [])
        else:
            self.current_page = 0
            self.zones_data_by_page = {}
            self.zones_data = []

        self.resize(1000, 900)
        self.setup_ui()
        self.setup_window_controls()

        # Auto-load current page XML when dialog opens
        self.parse_and_display_xml()

    def setup_ui(self):
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Custom title bar
        self.title_bar = self.create_custom_title_bar()
        layout.addWidget(self.title_bar)

        # Content area
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(10, 10, 10, 10)

        # Page info label
        self.page_label = QLabel(f"XML Source Editor - Page {self.current_page + 1}")
        self.page_label.setStyleSheet("font-size: 14px; font-weight: bold; margin-bottom: 5px;")
        content_layout.addWidget(self.page_label)

        # XML editor with syntax highlighting and folding
        self.xml_editor = QsciScintilla()
        self.setup_xml_editor()

        # Enable scroll bars
        self.xml_editor.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.xml_editor.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        content_layout.addWidget(self.xml_editor)

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: green; padding: 5px; font-size: 11px;")
        content_layout.addWidget(self.status_label)

        # Button layout
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(5, 5, 5, 5)
        button_layout.setSpacing(8)

        # Create buttons with icons and improved styling
        self.create_action_buttons(button_layout)

        button_layout.addStretch()
        content_layout.addLayout(button_layout)

        layout.addWidget(content_widget)

    def create_custom_title_bar(self):
        """Create a custom title bar with minimize, maximize, and close buttons"""
        title_bar = QWidget()
        title_bar.setFixedHeight(35)
        title_bar.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                border-bottom: 1px solid #555;
            }
        """)

        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(10, 0, 5, 0)

        # App icon and title
        title_label = QLabel("XML Editor")
        title_label.setStyleSheet("color: white; font-weight: bold; font-size: 12px;")
        title_layout.addWidget(title_label)

        title_layout.addStretch()

        # Window control buttons
        self.minimize_btn = QPushButton("−")
        self.minimize_btn.setFixedSize(30, 25)
        self.minimize_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: white;
                border: none;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #404040;
            }
        """)
        self.minimize_btn.clicked.connect(self.minimize_window)

        self.maximize_btn = QPushButton("□")
        self.maximize_btn.setFixedSize(30, 25)
        self.maximize_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: white;
                border: none;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #404040;
            }
        """)
        self.maximize_btn.clicked.connect(self.toggle_maximize)

        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(30, 25)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: white;
                border: none;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e81123;
            }
        """)
        self.close_btn.clicked.connect(self.close)

        title_layout.addWidget(self.minimize_btn)
        title_layout.addWidget(self.maximize_btn)
        title_layout.addWidget(self.close_btn)

        return title_bar

    def create_action_buttons(self, button_layout):
        """Create action buttons with improved styling"""
        button_style = """
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                padding: 6px 10px;
                border-radius: 6px;
                font-weight: 500;
                min-width: 90px;
                max-width: 120px;
                font-size: 11px;
                margin: 2px;
            }
            QPushButton:hover {
                background-color: #357abd;
                transform: translateY(-1px);
            }
            QPushButton:pressed {
                background-color: #2968a3;
                transform: translateY(0px);
            }
        """

        # Add spacing between buttons
        button_layout.setSpacing(8)

        # Page wise XML button
        page_wise_btn = QPushButton("🔄 Reload")
        page_wise_btn.setStyleSheet(button_style)
        page_wise_btn.clicked.connect(self.parse_and_display_xml)
        page_wise_btn.setToolTip("Reload XML content for current page")
        button_layout.addWidget(page_wise_btn)

        # Validate button
        self.validate_btn = QPushButton("✓ Validate")
        validate_style = button_style.replace("#4a90e2", "#27ae60").replace("#357abd", "#219a52").replace("#2968a3",
                                                                                                          "#1e8449")
        self.validate_btn.setStyleSheet(validate_style)
        self.validate_btn.clicked.connect(self.validate_xml)
        self.validate_btn.setToolTip("Validate XML syntax")
        button_layout.addWidget(self.validate_btn)

        # Format button
        self.format_btn = QPushButton("📐 Format")
        format_style = button_style.replace("#4a90e2", "#e74c3c").replace("#357abd", "#c0392b").replace("#2968a3",
                                                                                                        "#a93226")
        self.format_btn.setStyleSheet(format_style)
        self.format_btn.clicked.connect(self.format_xml)
        self.format_btn.setToolTip("Format and beautify XML")
        button_layout.addWidget(self.format_btn)

        # Folding controls
        fold_all_btn = QPushButton("📁 Fold")
        fold_style = button_style.replace("#4a90e2", "#f39c12").replace("#357abd", "#e67e22").replace("#2968a3",
                                                                                                      "#d35400")
        fold_all_btn.setStyleSheet(fold_style)
        fold_all_btn.clicked.connect(self.fold_all)
        fold_all_btn.setToolTip("Collapse all XML tags")
        button_layout.addWidget(fold_all_btn)

        unfold_all_btn = QPushButton("📂 Unfold")
        unfold_all_btn.setStyleSheet(fold_style)
        unfold_all_btn.clicked.connect(self.unfold_all)
        unfold_all_btn.setToolTip("Expand all XML tags")
        button_layout.addWidget(unfold_all_btn)

        # Copy button
        copy_btn = QPushButton("📋 Copy")
        copy_style = button_style.replace("#4a90e2", "#9b59b6").replace("#357abd", "#8e44ad").replace("#2968a3",
                                                                                                      "#7d3c98")
        copy_btn.setStyleSheet(copy_style)
        copy_btn.clicked.connect(self.copy_xml)
        copy_btn.setToolTip("Copy XML to clipboard")
        button_layout.addWidget(copy_btn)

        # Load/Save buttons
        self.load_btn = QPushButton("📁 Load")
        io_style = button_style.replace("#4a90e2", "#34495e").replace("#357abd", "#2c3e50").replace("#2968a3",
                                                                                                    "#1b2631")
        self.load_btn.setStyleSheet(io_style)
        self.load_btn.clicked.connect(self.load_from_file)
        self.load_btn.setToolTip("Load XML from file")
        button_layout.addWidget(self.load_btn)

        self.save_btn = QPushButton("💾 Save")
        self.save_btn.setStyleSheet(io_style)
        self.save_btn.clicked.connect(self.save_to_file)
        self.save_btn.setToolTip("Save XML to file")
        button_layout.addWidget(self.save_btn)

    def setup_xml_editor(self):
        """Setup the XML editor with syntax highlighting and advanced folding"""
        # Set XML lexer for syntax highlighting
        lexer = QsciLexerXML()

        # Enhanced font settings
        font = QFont("Consolas", 11)
        font.setFixedPitch(True)
        lexer.setDefaultFont(font)

        # Custom color scheme with correct QsciLexerXML attributes
        try:
            lexer.setColor(QColor("#92c5f7"), QsciLexerXML.XMLStart)  # XML declaration start
            lexer.setColor(QColor("#92c5f7"), QsciLexerXML.XMLEnd)  # XML declaration end
            lexer.setColor(QColor("#569cd6"), QsciLexerXML.Tag)  # XML tags
            lexer.setColor(QColor("#9cdcfe"), QsciLexerXML.Attribute)  # Attributes
            lexer.setColor(QColor("#ce9178"), QsciLexerXML.SingleQuotedString)  # Single quoted strings
            lexer.setColor(QColor("#ce9178"), QsciLexerXML.DoubleQuotedString)  # Double quoted strings
            lexer.setColor(QColor("#6a9955"), QsciLexerXML.Comment)  # Comments
            lexer.setColor(QColor("#d4d4d4"), QsciLexerXML.Text)  # Text content
            lexer.setColor(QColor("#ff6b6b"), QsciLexerXML.Entity)  # XML entities
            lexer.setColor(QColor("#4ecdc4"), QsciLexerXML.OtherInTag)  # Other content in tags
        except AttributeError as e:
            # Fallback to basic coloring if specific attributes don't exist
            print(f"Warning: Some XML lexer attributes not available: {e}")
            lexer.setColor(QColor("#569cd6"), 1)  # Tags
            lexer.setColor(QColor("#9cdcfe"), 3)  # Attributes
            lexer.setColor(QColor("#ce9178"), 6)  # Quoted strings
            lexer.setColor(QColor("#6a9955"), 9)  # Comments

        self.xml_editor.setLexer(lexer)

        # Editor settings
        self.xml_editor.setTabWidth(4)
        self.xml_editor.setAutoIndent(True)
        self.xml_editor.setIndentationsUseTabs(False)
        self.xml_editor.setIndentationWidth(4)

        # Advanced folding settings (similar to Notepad++)
        self.xml_editor.setFolding(QsciScintilla.BoxedTreeFoldStyle)
        self.xml_editor.setFoldMarginColors(QColor("#2b2b2b"), QColor("#2b2b2b"))

        # Wrapping and scrolling
        self.xml_editor.setWrapMode(QsciScintilla.WrapWord)
        self.xml_editor.setWrapIndentMode(QsciScintilla.WrapIndentIndented)
        self.xml_editor.setScrollWidth(1)
        self.xml_editor.setScrollWidthTracking(True)

        # Line numbers and margins
        self.xml_editor.setMarginType(0, QsciScintilla.NumberMargin)
        self.xml_editor.setMarginWidth(0, "0000")
        self.xml_editor.setMarginLineNumbers(0, True)
        self.xml_editor.setMarginSensitivity(0, False)
        self.xml_editor.setReadOnly(False)

        # Enhanced visual settings
        self.xml_editor.setWrapVisualFlags(QsciScintilla.WrapFlagByText, QsciScintilla.WrapFlagNone, 4)
        self.xml_editor.setCaretLineVisible(True)
        self.xml_editor.setCaretLineBackgroundColor(QColor("#2d2d30"))

        # Dark theme styling
        self.xml_editor.setStyleSheet("""
            QsciScintilla {
                background-color: #1e1e1e;
                color: #d4d4d4;
                selection-background-color: #264f78;
                border: 1px solid #3c3c3c;
            }
        """)

        # Enable brace matching
        self.xml_editor.setBraceMatching(QsciScintilla.SloppyBraceMatch)

        # Enable current line highlighting
        self.xml_editor.setCaretWidth(2)
        self.xml_editor.setCaretForegroundColor(QColor("#ffffff"))

    def setup_window_controls(self):
        """Setup window controls for minimize/maximize functionality"""
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        # Enable drag functionality for the title bar
        self.title_bar.mousePressEvent = self.title_bar_mouse_press
        self.title_bar.mouseMoveEvent = self.title_bar_mouse_move

        # Window state tracking
        self.is_maximized = False
        self.normal_geometry = self.geometry()

        # Set minimum size
        self.setMinimumSize(800, 600)

    def minimize_window(self):
        """Properly minimize the window"""
        self.setWindowState(Qt.WindowMinimized)

    def toggle_maximize(self):
        """Toggle between maximized and normal window state"""
        if self.isMaximized():
            self.showNormal()
            self.maximize_btn.setText("□")
        else:
            self.showMaximized()
            self.maximize_btn.setText("❐")

    def title_bar_mouse_press(self, event):
        """Handle mouse press on title bar for dragging"""
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def title_bar_mouse_move(self, event):
        """Handle mouse move for window dragging"""
        if event.buttons() == Qt.LeftButton and hasattr(self, 'drag_position'):
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    def title_bar_mouse_press(self, event):
        """Handle mouse press on title bar for dragging"""
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def title_bar_mouse_move(self, event):
        """Handle mouse move for window dragging"""
        if event.buttons() == Qt.LeftButton and hasattr(self, 'drag_position'):
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    def toggle_maximize(self):
        """Toggle between maximized and normal window state"""
        if self.is_maximized:
            self.setGeometry(self.normal_geometry)
            self.maximize_btn.setText("□")
            self.is_maximized = False
        else:
            self.normal_geometry = self.geometry()
            self.showMaximized()
            self.maximize_btn.setText("🗗")
            self.is_maximized = True

    def fold_all(self):
        """Fold all XML tags"""
        self.xml_editor.foldAll(True)
        self.status_label.setText("All tags folded")
        self.status_label.setStyleSheet("color: blue; padding: 5px; font-size: 11px;")

    def unfold_all(self):
        """Unfold all XML tags"""
        self.xml_editor.foldAll(False)
        self.status_label.setText("All tags unfolded")
        self.status_label.setStyleSheet("color: blue; padding: 5px; font-size: 11px;")

    def load_xml_content(self, content):
        """Load XML content into the editor"""
        self.xml_editor.setText(content)

    def get_xml_content(self):
        """Get the current XML content from the editor"""
        return self.xml_editor.text()

    def parse_and_display_xml(self):
        """Parse and display XML for current page"""
        try:
            # Generate XML from current page data
            xml_content = self.generate_page_xml()
            self.xml_editor.setText(xml_content)
            self.status_label.setText(f"Page {self.current_page + 1} XML loaded")
            self.status_label.setStyleSheet("color: green; padding: 5px;")
        except Exception as e:
            self.status_label.setText(f"Error loading page XML: {str(e)}")
            self.status_label.setStyleSheet("color: red; padding: 5px;")

    def generate_page_xml(self):
        """Generate XML for current page from zones data"""
        try:
            # Get current page data
            current_page_data = self.zones_data_by_page.get(self.current_page, [])
            if not current_page_data:
                return self.generate_empty_xml()

            return self.generate_clean_xml(current_page_data)
        except Exception as e:
            return f"<!-- Error generating XML: {str(e)} -->"

    def generate_empty_xml(self):
        """Generate empty XML structure"""
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<page number="{self.current_page + 1}">
    <zones>
        <!-- No zones data available for this page -->
    </zones>
</page>"""

    def generate_clean_xml(self, html_obj):
        """Generate clean XML from JSON data with proper type-based tags and formatting"""
        if not isinstance(html_obj, list):
            return "<root><error>Unsupported format</error></root>"

        # Enhanced tag mapping based on type
        type_to_tag_mapping = {
            "title": "title",
            "paragraph": "paragraph",
            "audio": "paragraph",  # treating audio type as paragraph
            "heading": "heading",
            "h1": "heading1",
            "h2": "heading2",
            "h3": "heading3",
            "h4": "heading4",
            "h5": "heading5",
            "h6": "heading6",
            "div": "division",
            "span": "span",
            "li": "listitem",
            "ul": "list",
            "table": "table",
            "img": "image",
            "video": "video",
            "text": "paragraph"  # default text to paragraph
        }

        def format_text_content(content, is_bold, is_italic):
            """Apply bold and italic formatting to text content"""
            formatted_content = escape(content)

            if is_bold and is_italic:
                return f"<b><i>{formatted_content}</i></b>"
            elif is_bold:
                return f"<b>{formatted_content}</b>"
            elif is_italic:
                return f"<i>{formatted_content}</i>"
            else:
                return formatted_content

        def build_zone_xml(tag_name, block_id, zone_type_attr, content, bbox_str, font_info, is_bold, is_italic):
            """Build XML zone with proper formatting"""
            # Format the content with bold/italic tags
            formatted_content = format_text_content(content, is_bold, is_italic)

            # Split long text content into multiple lines (wrap at ~80 characters)
            wrapped_content = self.wrap_text_content(formatted_content, 80)

            return f"""    <{tag_name} id="{block_id}" zone-type="{zone_type_attr}" bbox="{bbox_str}">
            <content font-name="{font_info['name']}" font-size="{font_info['size']}">{wrapped_content}</content>
        </{tag_name}>"""

        pages = {}

        for obj in html_obj:
            try:
                pg = obj.get("pg", obj.get("page", 1))
                span_id = obj.get("span_id", f"z{pg}-0")
                block_id = obj.get("block_id", f"pz{pg}-0")
                zone_type_attr = obj.get("type", "paragraph").lower()

                # BBox
                bbox = obj.get("bbox")
                if not bbox and all(k in obj for k in ['x', 'y', 'width', 'height']):
                    x, y, w, h = obj["x"], obj["y"], obj["width"], obj["height"]
                    bbox = (x, y, x + w, y + h)
                bbox_str = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}" if bbox else ""

                # Text content
                content_str = obj.get("text", "No Text")

                # Font information
                font_info = {
                    'name': obj.get("font_name", "Auto"),
                    'size': f"{obj.get('font_size', 10.0):.2f}pt"
                }

                # Get bold and italic flags from feats
                feats = obj.get("feats", {})
                is_bold = feats.get("font_is_bold", False) or feats.get("_N_font_is_bold", False)
                is_italic = feats.get("font_is_italic", False) or feats.get("_N_font_is_italic", False)

                # Get XML tag name based on type
                xml_tag = type_to_tag_mapping.get(zone_type_attr, "paragraph")

                # Special handling for different types
                if zone_type_attr == "img" or zone_type_attr == "image":
                    zone_xml = f'    <image id="{block_id}" zone-type="{zone_type_attr}" bbox="{bbox_str}" src="{escape(content_str)}" alt="{block_id}" />'
                elif zone_type_attr == "table":
                    formatted_content = format_text_content(content_str, is_bold, is_italic)
                    zone_xml = f"""    <table id="{block_id}" zone-type="{zone_type_attr}" bbox="{bbox_str}">
            <cell>{formatted_content}</cell>
        </table>"""
                elif zone_type_attr in ["list", "li"]:
                    zone_xml = build_zone_xml("listitem", block_id, zone_type_attr, content_str, bbox_str, font_info,
                                              is_bold, is_italic)
                else:
                    # Use the mapped tag name for the element
                    zone_xml = build_zone_xml(xml_tag, block_id, zone_type_attr, content_str, bbox_str, font_info,
                                              is_bold, is_italic)

                # Group by page
                if zone_type_attr in ["li"]:
                    pages.setdefault(pg, []).append(("li", zone_xml))
                else:
                    pages.setdefault(pg, []).append(("normal", zone_xml))

            except Exception as e:
                import traceback
                traceback.print_exc()
                error_xml = f'    <error>Error processing zone: {escape(str(e))}</error>'
                pages.setdefault(1, []).append(("normal", error_xml))

        def build_xml_doc(page_num, xml_tags):
            return f"""<?xml version="1.0" encoding="UTF-8"?>
    <document>
        <page number="{page_num + 1}" page-id="page-{page_num + 1}">
           
    {chr(10).join(xml_tags)}
         
        </page>
    </document>"""

        # Group list items into lists
        for pg_num, tag_tuples in pages.items():
            grouped_tags = []
            ul_buffer = []
            ul_index = 0

            for idx, item in enumerate(tag_tuples):
                if isinstance(item, tuple):
                    tag_type, xml = item
                else:
                    tag_type, xml = "normal", item

                if tag_type == "li":
                    ul_buffer.append(xml)
                else:
                    if ul_buffer:
                        ul_id = f"list-{pg_num + 1}-{ul_index + 1}"
                        grouped_tags.append(f'    <list id="{ul_id}" list-type="unordered">')
                        grouped_tags.extend(ul_buffer)
                        grouped_tags.append('    </list>')
                        ul_buffer.clear()
                        ul_index += 1
                    grouped_tags.append(xml)

            if ul_buffer:
                ul_id = f"list-{pg_num + 1}-{ul_index + 1}"
                grouped_tags.append(f'    <list id="{ul_id}" list-type="unordered">')
                grouped_tags.extend(ul_buffer)
                grouped_tags.append('    </list>')

            pages[pg_num] = grouped_tags

        # Return XML for current page only
        current_page_tags = pages.get(self.current_page, [])
        if not current_page_tags:
            return self.generate_empty_xml()

        return build_xml_doc(self.current_page, current_page_tags)


    def validate_xml(self):
        """Validate the XML content"""
        content = self.get_xml_content().strip()
        if not content:
            self.status_label.setText("No XML content to validate")
            self.status_label.setStyleSheet("color: orange; padding: 5px;")
            return False

        try:
            ET.fromstring(content)
            self.status_label.setText("XML is valid ✓")
            self.status_label.setStyleSheet("color: green; padding: 5px;")
            return True
        except ET.ParseError as e:
            self.status_label.setText(f"XML Parse Error: {str(e)}")
            self.status_label.setStyleSheet("color: red; padding: 5px;")
            return False

    def format_xml(self):
        """Format the XML content with proper indentation"""
        content = self.get_xml_content().strip()
        if not content:
            QMessageBox.warning(self, "Warning", "No XML content to format")
            return

        try:
            # Parse and format the XML
            parsed = ET.fromstring(content)
            rough_string = ET.tostring(parsed, encoding='unicode')
            reparsed = minidom.parseString(rough_string)
            formatted = reparsed.toprettyxml(indent="  ")

            # Remove empty lines and fix formatting
            lines = [line for line in formatted.split('\n') if line.strip()]
            formatted_xml = '\n'.join(lines)

            # Remove the XML declaration if it was added
            if formatted_xml.startswith('<?xml'):
                lines = formatted_xml.split('\n')
                if not content.strip().startswith('<?xml'):
                    formatted_xml = '\n'.join(lines[1:])

            self.xml_editor.setText(formatted_xml)
            self.status_label.setText("XML formatted successfully")
            self.status_label.setStyleSheet("color: green; padding: 5px;")

        except ET.ParseError as e:
            QMessageBox.critical(self, "Format Error", f"Cannot format invalid XML:\n{str(e)}")

    def load_from_file(self):
        """Load XML content from a file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load XML File", "", "XML Files (*.xml);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    content = file.read()
                    self.xml_editor.setText(content)
                    self.status_label.setText(f"Loaded from {file_path}")
                    self.status_label.setStyleSheet("color: green; padding: 5px;")
            except Exception as e:
                QMessageBox.critical(self, "Load Error", f"Could not load file:\n{str(e)}")

    def save_to_file(self):
        """Save XML content to a file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save XML File", "", "XML Files (*.xml);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as file:
                    file.write(self.get_xml_content())
                    self.status_label.setText(f"Saved to {file_path}")
                    self.status_label.setStyleSheet("color: green; padding: 5px;")
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Could not save file:\n{str(e)}")

    def copy_xml(self):
        """Copy XML content to clipboard"""
        try:
            from PyQt5.QtWidgets import QApplication
            content = self.get_xml_content()
            clipboard = QApplication.clipboard()
            clipboard.setText(content)
            self.status_label.setText("XML copied to clipboard")
            self.status_label.setStyleSheet("color: green; padding: 5px;")
        except Exception as e:
            self.status_label.setText(f"Error copying XML: {str(e)}")
            self.status_label.setStyleSheet("color: red; padding: 5px;")

    def wrap_text_content(self, text, max_width=80):
        """Wrap text content while preserving XML structure"""
        if len(text) <= max_width:
            return text

        # Split long text into multiple lines
        words = text.split()
        lines = []
        current_line = ""

        for word in words:
            if len(current_line + " " + word) <= max_width:
                if current_line:
                    current_line += " " + word
                else:
                    current_line = word
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)

        return "\n            ".join(lines)  # Proper indentation for wrapped lines


# Fixed implementation for pdf_viewer
def show_xml_editor(self):
    """Show XML editor dialog"""
    try:
        # Create and show the XML viewer dialog
        xml_viewer = XMLSourceViewer(self)
        xml_viewer.generate_page_xml()
        xml_viewer.exec_()  # Use exec_() for modal dialog
    except Exception as e:
        print(f"Error showing XML editor: {e}")
        # Fallback: show error message
        QMessageBox.critical(self, "Error", f"Could not open XML editor:\n{str(e)}")

# For setup_ui.py - this should work correctly now
# xml_source_action = QAction("XML Source", main_window)
# xml_source_action.triggered.connect(main_window.show_xml_editor)
# view_menu.addAction(xml_source_action)