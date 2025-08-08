import json
import ast
import re
import traceback
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QMessageBox, QApplication, QPushButton, QHBoxLayout, \
    QLabel
from PyQt5.Qsci import QsciScintilla, QsciLexerHTML
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt
from configParser import config_parser

class HtmlSourceViewer(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_page = getattr(parent, 'current_page', 1)
        self.zones_data_by_page = getattr(parent, 'zones_data_by_page')
        self.zones_data = getattr(parent, 'zones_data')
        self.resize(1000, 900)
        # Main layout
        layout = QVBoxLayout(self)
        # Title
        title_label = QLabel(f"HTML Source Viewer - Page {self.current_page+1}")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(title_label)

        # HTML output editor with syntax highlighting
        self.html_editor = QsciScintilla()
        self.setup_html_editor()
        self.setWindowFlags(
            Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)

        # Enable scroll bars
        self.html_editor.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.html_editor.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        layout.addWidget(self.html_editor)

        # Button layout
        button_layout = QHBoxLayout()

        # Refresh button
        refresh_btn = QPushButton("Page Wise Chapter")
        refresh_btn.clicked.connect(self.parse_and_display_html)
        button_layout.addWidget(refresh_btn)

        # Copy button
        copy_btn = QPushButton("Copy HTML")
        copy_btn.clicked.connect(self.copy_html)
        button_layout.addWidget(copy_btn)

        merge_btn = QPushButton("Merge to Single Chapter")
        merge_btn.clicked.connect(self.merge_to_single_chapter)
        button_layout.addWidget(merge_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)


    def setup_html_editor(self):
        """Setup the HTML editor with syntax highlighting"""
        # Set HTML lexer for syntax highlighting
        lexer = QsciLexerHTML()
        lexer.setDefaultFont(QFont("Consolas", 11))
        self.html_editor.setLexer(lexer)

        # Editor settings
        self.html_editor.setTabWidth(4)
        self.html_editor.setAutoIndent(True)
        self.html_editor.setIndentationsUseTabs(False)
        self.html_editor.setIndentationWidth(4)
        self.html_editor.setMarginType(0, QsciScintilla.NumberMargin)
        self.html_editor.setMarginWidth(0, "0000")
        self.html_editor.setMarginLineNumbers(0, True)
        self.html_editor.setMarginSensitivity(0, False)
        self.html_editor.setReadOnly(False)
        self.html_editor.setWrapVisualFlags(QsciScintilla.WrapFlagByText)

        # Set colors
        self.html_editor.setCaretLineVisible(True)
        self.html_editor.setCaretLineBackgroundColor(QColor("#ffe4e1"))

    def parse_and_display_html(self):
        try:
            if isinstance(self.html_editor, (list, dict)):
                html_obj = self.html_editor
            else:
                # Try to parse string input
                html_obj = self.safe_parse_object(str(self.html_editor))
                if html_obj is None:
                    self.html_editor.setText("Error: Unable to parse the HTML object data")
                    return
            # Generate clean HTML
            generated_html = self.generate_clean_html(html_obj)

            # Format the HTML nicely
            formatted_html = self.format_html(generated_html)
            # Display in editor
            self.html_editor.setText(formatted_html)

        except Exception as e:
            error_msg = f"Error parsing HTML object: {str(e)}"
            self.html_editor.setText(error_msg)
            QMessageBox.warning(self, "Parse Error", error_msg)

    def safe_parse_object(self, obj_text):
        try:
            if not obj_text or not isinstance(obj_text, str) or obj_text.strip() == "":
                print("html_text is empty or not a valid string.")
                return None
            try:
                result = ast.literal_eval(obj_text)
                if not isinstance(result, (list, dict)):
                    print("Parsed result is not a list/dict.")
                    return None
                return result
            except Exception as e:
                print("ast.literal_eval failed:", e)

            try:
                result = json.loads(obj_text)
                if not isinstance(result, (list, dict)):
                    print("Parsed JSON is not a list/dict.")
                    return None
                return result
            except Exception as e2:
                traceback.print_exc()
                print("json.loads failed:", e2)

            return None
        except Exception as e:
            print("in safe_parse_object+++++")
            traceback.print_exc()

    @staticmethod
    def generate_clean_html(html_obj):
        if not isinstance(html_obj, list):
            return "<p>Unsupported format</p>"
        from html import escape
        # Mapping of zone types to HTML tags
        tag_maps = config_parser.tag_mapping
        tag_mapping = json.loads(tag_maps)
        def build_zone_html(tag_name, attrs_str, block_id, zone_type_attr, inner_html):
            return f"""<{tag_name} {attrs_str} zone-id="{block_id}" zone-type="{zone_type_attr}">
                <a name="{block_id}">&nbsp;</a>
                    {inner_html}
                    </{tag_name}>"""

        pages = {}

        for obj in html_obj:
            try:
                pg = obj.get("pg", obj.get("page", 1))
                span_id = obj.get("span_id", f"z{pg}-0")
                block_id = obj.get("block_id", f"pz{pg}-0")
                zone_type_attr = obj.get("type", "p").lower()
                parent_wrapper = None

                # New logic: detect if a parent wrapper like "div.parent" is specified
                parent_zone = obj.get("parent_zone", "").lower()
                if parent_zone.endswith(".parent"):
                    parent_wrapper = parent_zone.split(".")[0]  # e.g., "div" → becomes parent tag

                # BBox
                bbox = obj.get("bbox")
                if not bbox and all(k in obj for k in ['x', 'y', 'width', 'height']):
                    x, y, w, h = obj["x"], obj["y"], obj["width"], obj["height"]
                    bbox = (x, y, x + w, y + h)
                bbox_str = f"({bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]})" if bbox else ""

                # Text content
                content_str = escape(obj.get("text", "No Text"))

                # Style
                bold =  False
                italic =  False
                style_str = []
                if bold:
                    style_str.append("font-weight: bold;")
                if italic:
                    style_str.append("font-style: italic;")
                style_str = " ".join(style_str)

                font_tag = f"""<font font-name="Auto" font-size="{obj.get("font_size", 10.0)}pt" id="{span_id}-f" style="{style_str}">"""
                wrapped_content = content_str
                if bold and italic:
                    wrapped_content = f"<b><i>{content_str}</i></b>"
                elif bold:
                    wrapped_content = f"<b>{content_str}</b>"
                elif italic:
                    wrapped_content = f"<i>{content_str}</i>"

                inner_span_html = f"""
                        <span  class="wrapped-text" bbox="{bbox_str}" id="{span_id}" pg="{pg}" span-id="{span_id}">
                            {font_tag}
                            {wrapped_content}
                            </font>
                        </span>
                    """

                tag_name = tag_mapping.get(zone_type_attr, "p")
                attrs_str = f'id="{block_id}"'

                # Special handling for complex types
                if zone_type_attr == "video":
                    attrs_str += ' controls width="640" height="360"'
                    zone_html = build_zone_html(tag_name, attrs_str, block_id, zone_type_attr, inner_span_html)

                elif zone_type_attr == "audio":
                    attrs_str += ' controls'
                    zone_html = build_zone_html(tag_name, attrs_str, block_id, zone_type_attr, inner_span_html)

                elif zone_type_attr == "img":
                    zone_html = f'<img src="{wrapped_content}" alt="{block_id}" id="{block_id}" zone-id="{block_id}" zone-type="{zone_type_attr}" />'

                elif zone_type_attr == "table":
                    zone_html = f"""
                        <table id="{block_id}" zone-id="{block_id}" zone-type="{zone_type_attr}">
                            <tr><td>{inner_span_html}</td></tr>
                        </table>
                        """

                elif zone_type_attr == "dl":
                    zone_html = f"""
                        <dl id="{block_id}" zone-id="{block_id}" zone-type="{zone_type_attr}">
                            <dt>{inner_span_html}</dt><dd>Description here</dd>
                        </dl>
                        """

                elif zone_type_attr in ["list", "li"]:
                    zone_html = build_zone_html("li", attrs_str, block_id, zone_type_attr, inner_span_html)

                else:
                    zone_html = build_zone_html(tag_name, attrs_str, block_id, zone_type_attr, inner_span_html)

                # Wrap in parent tag if specified via parent_zone
                if parent_wrapper:
                    wrapper_id = f"{block_id}-wrapper"
                    zone_html = f'<{parent_wrapper} class="zone-parent" parent-id="{block_id}" id="{wrapper_id}">{zone_html}</{parent_wrapper}>'

                if zone_type_attr in ["li"]:
                    pages.setdefault(pg, []).append(("li", zone_html))
                else:
                    pages.setdefault(pg, []).append(("normal", zone_html))


            except Exception as e:
                import traceback
                traceback.print_exc()
                pages.setdefault(1, []).append(f"<p><span>Error: {escape(str(e))}</span></p>")

        def build_html_doc(page_num, p_tags):
            return f"""<?xml version="1.0" encoding="utf-8"?>
                    <!DOCTYPE html>
                        <html xml:lang="en" xmlns="http://www.w3.org/1999/xhtml">
                          <head>
                            <meta charset="utf-8" />
                            <title>Page {page_num + 1}</title>
                          </head>
                          <body id="body" body-id="body">
                            <div class="chapter" id="sec-{page_num + 1}" div-id="sec-{page_num + 1}">
                              {"".join(p_tags)}
                            </div>
                          </body>
                    </html>"""

        # Group <li> into <ul>
        for pg_num, tag_tuples in pages.items():
            grouped_tags = []
            ul_buffer = []
            ul_index = 0

            for idx, item in enumerate(tag_tuples):
                if isinstance(item, tuple):
                    tag_type, html = item
                else:
                    tag_type, html = "normal", item

                if tag_type == "li":
                    ul_buffer.append(html)
                else:
                    if ul_buffer:
                        ul_id = f"lz{pg_num + 1}-{ul_index + 1}"
                        grouped_tags.append(f'<ul id="{ul_id}" ul-id="{ul_id}">')
                        grouped_tags.extend(ul_buffer)
                        grouped_tags.append("</ul>")
                        ul_buffer.clear()
                        ul_index += 1
                    grouped_tags.append(html)

            if ul_buffer:
                ul_id = f"lz{pg_num + 1}-{ul_index + 1}"
                grouped_tags.append(f'<ul id="{ul_id}" ul-id="{ul_id}">')
                grouped_tags.extend(ul_buffer)
                grouped_tags.append("</ul>")

            pages[pg_num] = grouped_tags

        output_html = "\n\n".join(build_html_doc(pg, pages[pg]) for pg in sorted(pages))
        return output_html

    @staticmethod
    def format_html(html_content):
        """Format HTML with proper indentation and each tag on separate lines"""
        import re
        # First, ensure each tag is on its own line
        # Add newlines before opening tags
        html_content = re.sub(r'(<[^/][^>]*>)', r'\n\1', html_content)
        # Add newlines before closing tags
        html_content = re.sub(r'(<\/[^>]*>)', r'\n\1', html_content)
        # Add newlines after closing tags
        html_content = re.sub(r'(<\/[^>]*>)', r'\1\n', html_content)

        lines = html_content.split('\n')
        formatted_lines = []
        indent_level = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Decrease indent for closing tags
            if stripped.startswith('</') and not stripped.startswith('<!--'):
                indent_level = max(0, indent_level - 1)

            # Add indented line
            formatted_lines.append('    ' * indent_level + stripped)

            # Increase indent for opening tags (but not self-closing or comments)
            if (stripped.startswith('<') and not stripped.startswith('</')
                    and not stripped.endswith('/>') and not stripped.startswith('<!--')
                    and not any(
                        tag in stripped for tag in ['<!DOCTYPE', '<meta', '<link', '<br', '<hr', '<img', '<input'])):
                indent_level += 1

        return '\n'.join(formatted_lines)

    def copy_html(self):
        """Copy HTML content to clipboard"""
        clipboard = QApplication.clipboard()
        clipboard.setText(self.html_editor.text())
        QMessageBox.information(self, "Copied", "HTML content copied to clipboard!")

    def merge_to_single_chapter(self):
        try:
            if isinstance(self.zones_data, (list, dict)):
                html_obj = self.zones_data
            else:
                html_obj = self.safe_parse_object(str(self.zones_data))
                if html_obj is None:
                    self.html_editor.setText("Error: Unable to parse the HTML object data")
                    return

            from html import escape

            tag_maps = config_parser.tag_mapping
            tag_mapping = json.loads(tag_maps)

            all_blocks = []
            li_blocks = []
            list_index = 1

            for obj in html_obj:
                try:
                    pg = obj.get("pg", obj.get("page", 1))
                    span_id = obj.get("span_id", f"z{pg}-0")
                    block_id = obj.get("block_id", f"pz{pg}-0")
                    zone_type_attr = obj.get("type", "p").lower()

                    # BBox
                    bbox = obj.get("bbox")
                    if not bbox and all(k in obj for k in ['x', 'y', 'width', 'height']):
                        x, y, w, h = obj["x"], obj["y"], obj["width"], obj["height"]
                        bbox = (x, y, x + w, y + h)
                    bbox_str = f"({bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]})" if bbox else ""

                    # Text
                    content_str = escape(obj.get("text", "No Text"))

                    # Font style
                    bold = obj.get("feats", {}).get("_N_font_is_bold", False)
                    italic = obj.get("feats", {}).get("_N_font_is_italic", False)
                    style_str = []
                    if bold:
                        style_str.append("font-weight: bold;")
                    if italic:
                        style_str.append("font-style: italic;")
                    style_str = " ".join(style_str)

                    font_tag = f"""<font font-name="Auto" font-size="{obj.get("font_size", 10.0):.2f}pt" id="{span_id}-f" style="{style_str}">"""

                    wrapped_content = content_str
                    if bold and italic:
                        wrapped_content = f"<b><i>{content_str}</i></b>"
                    elif bold:
                        wrapped_content = f"<b>{content_str}</b>"
                    elif italic:
                        wrapped_content = f"<i>{content_str}</i>"

                    span_html = f"""
    <span class="wrapped-text" bbox="{bbox_str}" id="{span_id}" pg="{pg}" span-id="{span_id}">
        {font_tag}
        {wrapped_content}
        </font>
    </span>
    """

                    tag_name = tag_mapping.get(zone_type_attr, "p")
                    attrs_str = f'id="{block_id}" zone-id="{block_id}" zone-type="{zone_type_attr}"'

                    if zone_type_attr == "video":
                        block_html = f'<video {attrs_str} controls width="640" height="360">{span_html}</video>'

                    elif zone_type_attr == "audio":
                        block_html = f'<audio {attrs_str} controls>{span_html}</audio>'

                    elif zone_type_attr == "img":
                        block_html = f'<img src="{wrapped_content}" alt="{block_id}" {attrs_str} />'

                    elif zone_type_attr == "table":
                        block_html = f"""<table {attrs_str}><tr><td>{span_html}</td></tr></table>"""

                    elif zone_type_attr == "dl":
                        block_html = f"""<dl {attrs_str}><dt>{span_html}</dt><dd>Description here</dd></dl>"""

                    elif zone_type_attr in ["li"]:
                        li_blocks.append(f"<li {attrs_str}>{span_html}</li>")

                    else:
                        block_html = f"<{tag_name} {attrs_str}><a name=\"{block_id}\"></a>{span_html}</{tag_name}>"
                        all_blocks.append(block_html)

                except Exception as e:
                    from html import escape
                    all_blocks.append(f"<p><span>Error: {escape(str(e))}</span></p>")

            # Wrap collected <li> in <ul>
            if li_blocks:
                ul_id = f"ul-merged-{list_index}"
                all_blocks.append(f'<ul id="{ul_id}" ul-id="{ul_id}">')
                all_blocks.extend(li_blocks)
                all_blocks.append("</ul>")

            # Final HTML
            merged_html = f"""<?xml version="1.0" encoding="utf-8"?>
    <!DOCTYPE html>
    <html xml:lang="en" xmlns="http://www.w3.org/1999/xhtml">
      <head>
        <meta charset="utf-8" />
        <title>All Pages Merged</title>
        <style>
          .wrapped-text {{
            word-wrap: break-word;
            white-space: normal;
            overflow-wrap: break-word;
          }}
        </style>
      </head>
      <body id="body" body-id="body">
        <div class="chapter" id="merged-chapter" div-id="merged-chapter">
          {"".join(all_blocks)}
        </div>
      </body>
    </html>"""

            formatted_html = self.format_html(merged_html)
            self.html_editor.setText(formatted_html)

        except Exception as e:
            error_msg = f"Error merging HTML: {str(e)}"
            self.html_editor.setText(error_msg)
            QMessageBox.warning(self, "Merge Error", error_msg)

    def scroll_to_zone_html(self, zone_id: str):
        editor = self.html_editor
        target_attr = f'zone-id="{zone_id}"'
        self.clear_previous_highlight()

        lines = editor.text().split('\n')
        target_line = -1
        open_tag = None

        # Step 1: Find line with zone-id and extract the tag
        for i, line in enumerate(lines):
            if target_attr in line:
                target_line = i
                match = re.search(r'<(\w+)[^>]*zone-id="' + re.escape(zone_id) + '"', line)
                if match:
                    open_tag = match.group(1)
                break

        if target_line == -1 or not open_tag:
            return  # Not found or malformed

        # Step 2: Find start and end of the HTML block
        start_line = target_line
        while start_line >= 0:
            if lines[start_line].strip().startswith(f"<{open_tag}"):
                break
            start_line -= 1

        end_line = target_line
        while end_line < len(lines):
            if lines[end_line].strip().startswith(f"</{open_tag}>"):
                break
            end_line += 1

        # Step 3: Highlight the block
        for line_num in range(start_line, end_line + 1):
            if line_num < len(lines):
                self._apply_highlight(line_num, len(lines[line_num]))

        # Step 4: Scroll to the block
        editor.setCursorPosition(start_line, 0)
        editor.ensureLineVisible(start_line)

    def _apply_highlight(self, line: int, length: int):
        """Apply a green highlight to a line"""
        editor = self.html_editor
        pos = editor.positionFromLineIndex(line, 0)

        # Setup style only once
        editor.SendScintilla(QsciScintilla.SCI_SETINDICATORCURRENT, 0)
        editor.SendScintilla(QsciScintilla.SCI_INDICSETSTYLE, 0, QsciScintilla.INDIC_ROUNDBOX)
        color = QColor("#1e8449")  # Dark green
        rgb_int = color.red() | (color.green() << 8) | (color.blue() << 16)
        editor.SendScintilla(QsciScintilla.SCI_INDICSETFORE, 0, rgb_int)

        editor.SendScintilla(QsciScintilla.SCI_INDICATORFILLRANGE, pos, length)

        # Store highlighted ranges for clearing later
        if not hasattr(self, 'highlighted_ranges'):
            self.highlighted_ranges = []
        self.highlighted_ranges.append((pos, length))

    def clear_previous_highlight(self):
        """Clear any existing highlight"""
        if hasattr(self, 'highlighted_ranges'):
            editor = self.html_editor
            editor.SendScintilla(QsciScintilla.SCI_SETINDICATORCURRENT, 0)
            for pos, length in self.highlighted_ranges:
                editor.SendScintilla(QsciScintilla.SCI_INDICATORCLEARRANGE, pos, length)
            self.highlighted_ranges = []


    def detect_and_update_zone_changes(self):
        """Detect any change in HTML and update the corresponding zone objects by zone-id"""
        from bs4 import BeautifulSoup
        try:
            modified_html = self.html_editor.text()
            soup = BeautifulSoup(modified_html, "html.parser")
            updated_count = 0

            # Access zone list via parent

            if not hasattr(self, 'zones_data_by_page'):
                QMessageBox.warning(self, "Error", "Cannot access zone data from parent.")
                return

            zone_list = self.zones_data_by_page.get(self.current_page, [])

            # Build fast access index for zone-id → zone object
            zone_map = {}
            for zone in zone_list:
                zid = zone.get("block_id") or zone.get("span_id")
                if zid:
                    zone_map[zid] = zone

            # Scan each block (<p>, <div>) for changes
            for block_tag in soup.find_all(["p", "div"]):
                zone_id = block_tag.get("zone-id") or block_tag.get("id")
                if not zone_id:
                    continue

                span = block_tag.find("span")
                if not span:
                    continue

                font_tag = span.find("font")
                if not font_tag:
                    continue

                # Get updated text (with formatting tags)
                updated_inner_html = ''.join(str(c) for c in font_tag.contents).strip()

                # Get updated font size and styles
                font_size_str = font_tag.get("font-size", "10.0pt")
                updated_font_size = float(font_size_str.replace("pt", "")) if "pt" in font_size_str else 10.0

                font_style = font_tag.get("style", "")
                is_bold = "bold" in font_style
                is_italic = "italic" in font_style

                # Get bbox from <span>
                updated_bbox = span.get("bbox", "")
                updated_text_plain = span.get_text(strip=True)

                # Find the original zone
                zone = zone_map.get(zone_id)
                if not zone:
                    continue

                # Compare and update fields
                changed = False

                if zone.get("text", "").strip() != updated_text_plain:
                    zone["text"] = updated_text_plain
                    changed = True

                if "feats" not in zone:
                    zone["feats"] = {}

                if zone["feats"].get("_N_font_is_bold", False) != is_bold:
                    zone["feats"]["_N_font_is_bold"] = is_bold
                    changed = True

                if zone["feats"].get("_N_font_is_italic", False) != is_italic:
                    zone["feats"]["_N_font_is_italic"] = is_italic
                    changed = True

                # if abs(zone.get("font_size", 10.0) - updated_font_size) > 0.1:
                #     zone["font_size"] = updated_font_size
                #     changed = True

                # if updated_bbox and zone.get("bbox", "") != updated_bbox:
                #     zone["bbox"] = updated_bbox
                #     changed = True

                if changed:
                    updated_count += 1

            QMessageBox.information(self, "Zone Sync Complete", f"{updated_count} zone(s) updated.")

        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "Update Error", f"Failed to apply updates:\n{str(e)}")
