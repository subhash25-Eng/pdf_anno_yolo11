import re

from PyQt5.Qsci import QsciScintilla
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QTextCursor, QTextCharFormat
from PyQt5.QtWidgets import QTextEdit

from html_viewer import  HtmlSourceViewer


def display_page_content(self):
    """Display DOM-based content for a specific page"""
    if not self.zones_data:
        error_html = """
        <html><body><div style='color:red;padding:20px;'>
        <h3>No DOM content available</h3>
        <p>Please ensure the DOM has been built using build_dom_once() first.</p>
        </div></body></html>"""
        self.rich_text_editor.set_html(error_html)
        return

    try:
        # Filter zones for the specified page
        # page_zones = [zone for zone in zones if zone['page'] == page_number + 1]
        page_zones = self.zones_data_by_page.get(self.current_page, [])
        if not page_zones:
            no_content_html = f"""
            <html><body><div style='color:#666;padding:20px;'>
            <h3>Content Loading.. </h3>
            </div></body></html>"""
            self.rich_text_editor.set_html(no_content_html)
            return
        if page_zones:
            html_viewer = HtmlSourceViewer(self)
            generated_html = html_viewer.generate_clean_html(page_zones)
            formatted_html = html_viewer.format_html(generated_html)
            self.rich_text_editor.set_html(formatted_html)
    except Exception as e:
        error_html = f"""
        <html><body><div style='color:red;padding:20px;border:1px solid #e74c3c;border-radius:6px;background:#fdf2f2;'>
        <h3>❌ Error loading DOM content</h3>
        <p><strong>Error details:</strong> {str(e)}</p>
        <p><strong>Available zones:</strong> {len(getattr(self, 'all_zones', []))}</p>
        </div></body></html>"""
        self.rich_text_editor.set_html(error_html)


def scroll_to_zone_id(rich_text_editor, zone_id: str):
    editor = rich_text_editor.text_editor
    html_lines = editor.toHtml().split('\n')
    anchor_name = re.sub(r"^p", "", zone_id)
    target_attr = f'name="{anchor_name}"'

    target_line = -1
    anchor_tag = '<a'
    for i, line in enumerate(html_lines):
        if target_attr in line and anchor_tag in line:
            target_line = i
            break

    if target_line == -1:
        return

    parent_tag = None
    open_tag_line = -1

    for i in range(target_line, -1, -1):
        match = re.search(r'<(\w+)[^>]*?>', html_lines[i])
        if match:
            parent_tag = match.group(1)
            open_tag_line = i
            break

    if not parent_tag:
        return

    # Step 3: Find the closing tag
    close_tag = f"</{parent_tag}>"
    close_tag_line = target_line
    while close_tag_line < len(html_lines):
        if close_tag in html_lines[close_tag_line]:
            break
        close_tag_line += 1

    if close_tag_line >= len(html_lines):
        return

    block_html = "\n".join(html_lines[open_tag_line:close_tag_line + 1])
    text_fragment = _extract_text_from_html(block_html).strip()
    if not text_fragment:
        return

    # Step 5: Scroll to and highlight the block
    doc_cursor = editor.document().find(text_fragment)
    if doc_cursor.isNull():
        return

    editor.setExtraSelections([])

    highlight = QTextEdit.ExtraSelection()
    highlight.cursor = doc_cursor
    highlight.cursor.select(QTextCursor.BlockUnderCursor)
    highlight.format.setBackground(QColor("#fcf3cf"))
    highlight.format.setForeground(QColor("black"))
    highlight.format.setProperty(QTextCharFormat.FullWidthSelection, True)

    editor.setExtraSelections([highlight])
    editor.setTextCursor(doc_cursor)
    doc_cursor.clearSelection()
    editor.setTextCursor(doc_cursor)
    editor.ensureCursorVisible()
    editor.viewport().update()

def _extract_text_from_html(html_block: str) -> str:
    from html.parser import HTMLParser

    class HTMLTextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.text = []

        def handle_data(self, data):
            self.text.append(data)

        def get_text(self):
            return ''.join(self.text)

    parser = HTMLTextExtractor()
    parser.feed(html_block)
    return parser.get_text()
