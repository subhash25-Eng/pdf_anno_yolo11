import sys
from PyQt5 import sip
from loading_class import LoadingDialog
from pdf_utils import FastRenderTask
from setup_ui import setup_menu_bar, setup_main_layout
from resizable_zone import ResizableZone
from ZoneShortcutManager import ZoneShortcutManager
from zone_extractor import BackgroundZoneExtractionTask
import fitz
import logging
import traceback
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from style_loader import load_stylesheet
from display_content import display_page_content
from html_viewer import HtmlSourceViewer
from pdf_utils import PdfUtils
from richtexteditor import RichTextEditor
import os, json
from xml_source_viewer import XMLSourceViewer
from pathlib import Path

class PDFViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        # Core data
        self.zones_data_by_page = None
        self.html_viewer = None
        self.pdf_doc = None
        self.doc_path = None
        self.zones_data = []
        self.zone_extractor = None
        # Performance settings for 500+ pages
        self.zoom_factor = 1  # Start with 1.0 for consistency
        self.page_cache = {}
        self.max_cache_size = 25  # Reasonable cache size
        self.viewport_buffer = 2  # Better buffer for smoother scrolling
        self.priority_pages = 5  # First 3 pages get priority rendering
        self.current_page = 0
        # UI components
        self.page_widgets = []
        self.active_scenes = {}
        self.active_views = {}

        # Create a label to show centered status messages
        self.center_status_label = QLabel("")
        self.center_status_label.setAlignment(Qt.AlignCenter)
        self.statusBar().addPermanentWidget(self.center_status_label, 1)

        # Threading - separate pools for fast and background tasks
        self.fast_thread_pool = QThreadPool()
        self.fast_thread_pool.setMaxThreadCount(10)  # Balanced thread count

        self.background_thread_pool = QThreadPool()
        self.background_thread_pool.setMaxThreadCount(6)  # Limited for background tasks

        # State management
        self.creation_mode = False
        self.zone_history = []
        self.zones_added = set()
        self.loading_dialog = None
        self.last_scroll_position = 0
        self.document_ready = False
        self.current_text_viewer = "text_viewer"

        # Ultra-fast debouncing
        self.scroll_timer = QTimer()
        self.scroll_timer.setSingleShot(True)
        # self.scroll_timer.timeout.connect(self.handle_scroll_delayed)

        # Priority loading timer
        self.priority_timer = QTimer()
        self.priority_timer.setSingleShot(True)
        self.priority_timer.timeout.connect(self.load_priority_pages)
        self.pdf_utils_obj = PdfUtils(self)
        # self.xml_source_viewer_obj = XMLSourceViewer(self)
        self.shortcut_manager = ZoneShortcutManager(self)
        # Memory management timer
        self.memory_timer = QTimer()
        self.memory_timer.timeout.connect(self.manage_memory)
        self.memory_timer.start(5000)  # every 5 seconds
        # Clean up every 5 seconds
        self.rich_text_editor = RichTextEditor()
        self.init_ui()
        self.init_styles()
        self.setup_keyboard_shortcuts()

        self.batch_size = 1
        self.current_batch_index = 0
        self.total_batches = 0
        self.batches_submitted = set()
        self.full_doc = None  # fitz.Document()
        self.original_pdf_name = ""

    def init_ui(self):
        """Initialize UI with status indicators"""
        self.setWindowTitle("PDF Loader")
        screen = QApplication.primaryScreen()
        rect = screen.availableGeometry()
        self.setGeometry(rect)

        self.showMaximized()  # Scroll bar style not loading due to this.

        setup_menu_bar(self)  # UI
        setup_main_layout(self)  # uI

    def init_styles(self):
        self.setStyleSheet(load_stylesheet("style.css"))

    def show_text_viewer(self):
        self.current_text_viewer = "text_viewer"
        self.displayContent()
        self.pdf_utils_obj.showtextviewer(self)

    def merge_zones(self, selected_zones):
        self.pdf_utils_obj.mergezones(self, selected_zones)

    def show_html_source_viewer(self):
        if not self.zones_data:
            QMessageBox.warning(self, "No HTML", "No HTML content available.")
            return
        # Create the HTML viewer and replace the right panel
        # html_text = self.zones_data_by_page[self.current_page]
        html_text = self.zones_data_by_page.get(self.current_page, [])
        html_viewer = HtmlSourceViewer(self)
        clean_html = html_viewer.generate_clean_html(html_text)
        format_html = html_viewer.format_html(clean_html)
        html_viewer.html_editor.setText(format_html)
        html_viewer.setWindowFlags(Qt.Widget)  # so it embeds properly

        self.splitter.replaceWidget(1, html_viewer)
        self.text_display = html_viewer
        self.current_text_viewer = "html_viewer"

    def show_xml_editor(self):
        from xml_source_viewer import show_xml_editor
        show_xml_editor(self)


    def toggle_sequence_circles(self):
        self.pdf_utils_obj.toggle_sequence_circles()
        if self.pdf_utils_obj.sequence_circles_visible:
            self.toggle_sequence_action.setText("Hide Sequence Circle")
        else:
            self.toggle_sequence_action.setText("Show Sequence Circle")


    def manage_memory(self):
        """Safely remove unused page views and cache entries."""
        max_cache_limit = self.max_cache_size  # e.g., 25

        # Remove pages from page_cache beyond limit
        if len(self.page_cache) > max_cache_limit:
            pages_in_use = set(self.active_views.keys()) | {self.current_page}
            removable_pages = [pg for pg in self.page_cache if pg not in pages_in_use]

            for pg in removable_pages[:5]:  # Remove max 5 at a time
                del self.page_cache[pg]
                logging.debug(f"Removed cached page: {pg}")

        # Remove old views/scenes not visible
        to_delete = [pg for pg in self.active_views if pg != self.current_page]
        for pg in to_delete:
            view = self.active_views.pop(pg, None)
            scene = self.active_scenes.pop(pg, None)

            try:
                if view and not sip.isdeleted(view):
                    view.setParent(None)
                    view.deleteLater()
            except Exception as e:
                logging.warning(f"Error deleting view for page {pg}: {e}")

            if scene:
                del scene

            logging.debug(f"Cleaned up view/scene for page: {pg}")

    ########################

    def open_pdf(self):
        """Ultra-fast PDF opening"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open PDF", "", "PDF Files (*.pdf)"
        )
        # self.clear_temp_pdf_folder()
        if not file_path:
            return
        start_time = QTime.currentTime()

        self.loading_dialog = LoadingDialog("Extracting zones...", self)
        self.loading_dialog.setModal(False)
        self.loading_dialog.show()
        self.loading_dialog.start()

        try:
            # Cleanup previous
            self.cleanup_previous_document()

            self.doc_path = file_path
            self.pdf_filename = os.path.basename(file_path)
            self.update_window_title()
            self.pdf_doc = fitz.open(self.doc_path)
            page_count = len(self.pdf_doc)

            # Display parsed text first

            logging.info(f"Opening PDF with {page_count} pages")
            self.page_info_label.setText(f"Document: {page_count} pages")
            self.performance_label.setText("Loading...")
            self.page_spinbox.setValue(0)
            self.current_page = 0
            self.display_single_page(self.current_page)
            self.prepare_batch_extraction(self.doc_path)
            elapsed = start_time.msecsTo(QTime.currentTime())
            self.performance_label.setText(f"Loaded in {elapsed}ms")
            self.page_label.setText(f"of {page_count}")
            self.document_ready = True

            logging.info(f"PDF opened in {elapsed}ms")

        except Exception as e:
            logging.error(f"Failed to open PDF: {e}")
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to open PDF:\n{str(e)}")


    def display_single_page(self, page_number, force_rerender=False):
        self.current_page = page_number
        self.scroll_area.setUpdatesEnabled(False)
        try:
            for i in reversed(range(self.scroll_layout.count())):
                item = self.scroll_layout.itemAt(i)
                widget = item.widget()
                if widget:
                    widget.setVisible(False)
                    QTimer.singleShot(500, widget.deleteLater)

            # 🔁 Clear old references
            self.active_views.pop(page_number, None)
            self.active_scenes.pop(page_number, None)

            # 🧠 Use cached image if available and no force_rerender
            if not force_rerender and page_number in self.page_cache:
                image, used_zoom = self.page_cache[page_number]
                self.create_page_view_fast(page_number, image, used_zoom)
                QTimer.singleShot(10, self.render_pending_zones)
                return

            # ⚡ Trigger fast rendering task
            task = FastRenderTask(
                self.doc_path,
                page_number,
                self.zoom_factor,
                self.fast_render_callback,
                self.render_error_callback,
                priority=True
            )
            self.fast_thread_pool.start(task)

        finally:
            # ✅ Re-enable updates after a small delay for smoothness
            QTimer.singleShot(10, lambda: self.scroll_area.setUpdatesEnabled(True))

    def displayContent(self):
        if self.current_text_viewer == "html_viewer":
            QTimer.singleShot(10, self.show_html_source_viewer)
        else:
            display_page_content(self)

    def call_display_page_content(self):
        display_page_content(self)

    def load_priority_pages(self):
        """Load first few pages with highest priority"""
        if not self.pdf_doc:
            return

        priority_count = min(self.priority_pages, len(self.pdf_doc))

        for i in range(priority_count):
            task = FastRenderTask(
                self.doc_path,
                i,
                self.zoom_factor,
                self.fast_render_callback,
                self.render_error_callback,
                priority=True
            )
            self.fast_thread_pool.start(task)

        logging.info(f"Started priority loading for first {priority_count} pages")


    def get_selected_zones(self):
        selected = []
        acitveScenes = list(self.active_scenes.values())
        for scene in acitveScenes:
            selected += [item for item in scene.selectedItems() if isinstance(item, ResizableZone)]
        return selected

    def load_page_fast(self, page_number):
        """Ultra-fast page loading"""
        if page_number in self.active_scenes or page_number >= len(self.page_widgets):
            return

        # Check cache first
        if page_number in self.page_cache:
            image, used_zoom = self.page_cache[page_number]
            # Only use cached image if zoom matches closely
            if abs(used_zoom - self.zoom_factor) < 0.1:
                self.create_page_view_fast(page_number, image, used_zoom)
                return

        # Start fast rendering
        task = FastRenderTask(
            self.doc_path,
            page_number,
            self.zoom_factor,
            self.fast_render_callback,
            self.render_error_callback,
            priority=False
        )
        self.fast_thread_pool.start(task)

    def create_page_view_fast(self, page_number, image, used_zoom):

        self.pdf_utils_obj.createpageviewfast(self, page_number, image, used_zoom)

    @pyqtSlot(int, QImage, float)
    def fast_render_callback(self, page_number, image, used_zoom):
        if len(self.page_cache) >= self.max_cache_size:
            oldest_keys = list(self.page_cache.keys())[:5]
            for key in oldest_keys:
                del self.page_cache[key]

        self.page_cache[page_number] = (image, used_zoom)

        if page_number == self.current_page:
            self.create_page_view_fast(page_number, image, used_zoom)

    def setup_keyboard_shortcuts(self):
        """Setup keyboard shortcuts for navigation"""
        # Up arrow - Previous page
        up_shortcut = QShortcut(QKeySequence(Qt.Key_Up), self)
        up_shortcut.activated.connect(self.go_to_previous_page)

        # Right arrow - Next page
        right_shortcut = QShortcut(QKeySequence(Qt.Key_Right), self)
        right_shortcut.activated.connect(self.go_to_next_page)

        # Down arrow - Next page (alternative)
        down_shortcut = QShortcut(QKeySequence(Qt.Key_Down), self)
        down_shortcut.activated.connect(self.go_to_next_page)

        # Left arrow - Previous page (alternative)
        left_shortcut = QShortcut(QKeySequence(Qt.Key_Left), self)
        left_shortcut.activated.connect(self.go_to_previous_page)

    @pyqtSlot(int, str)
    def render_error_callback(self, page_number, error_msg):
        """Handle rendering errors"""
        logging.error(f"Render error for page {page_number}: {error_msg}")


    def swap_sequence(self, selected_zones):
        self.pdf_utils_obj.replace_sequence_number(self, selected_zones)

    def add_zones_to_scene_fast(self, scene, page_number, used_zoom):
        self.pdf_utils_obj.addzones_to_scene_fast(self, scene, page_number, used_zoom)

    def zoom_in(self):
        if self.zoom_factor < 3.0:
            self.zoom_factor = round(self.zoom_factor + 0.2, 2)
            self.zoom_label.setText(f"{int(self.zoom_factor * 100)}%")
            logging.info(f"Zoom in: {self.zoom_factor:.1f}x")
            self.display_single_page(self.current_page, force_rerender=True)

    def zoom_out(self):
        if self.zoom_factor > 0.4:
            self.zoom_factor = round(self.zoom_factor - 0.2, 2)
            self.zoom_label.setText(f"{int(self.zoom_factor * 100)}%")
            logging.info(f"Zoom out: {self.zoom_factor:.1f}x")
            self.display_single_page(self.current_page, force_rerender=True)

    def toggle_creation_mode(self):
        """Toggle zone creation mode and update status/cursor."""
        self.creation_mode = not self.creation_mode

        if self.creation_mode:
            self.center_status_label.setStyleSheet("color: red; font-weight: bold;")
            self.center_status_label.setText("Zone creation mode ON")
            self.setCursor(Qt.CrossCursor)

        else:
            self.center_status_label.setStyleSheet("color: black;")
            self.center_status_label.setText("Zone creation mode OFF")
            self.setCursor(Qt.ArrowCursor)

    def create_zone(self, rect, scene, page_number):
        self.pdf_utils_obj.createzone(self, rect, scene, page_number)

    def insert_zone_in_order(self, new_zone):
        self.pdf_utils_obj.insert_new_zone_toall_html(self, new_zone)

    def undo_last_action(self):
        """Undo last zone action"""
        if self.zone_history:
            last_action = self.zone_history.pop()
            # Implement undo logic based on action type
            logging.info(f"Undoing action: {last_action}")

    def on_zones_updated(self):
        """Handle zone updates"""
        if hasattr(self, 'zones_data') and self.zones_data:
            zone_count = len(self.zones_data) if self.zones_data else 0
            self.performance_label.setText(f"Zones updated: {zone_count}")
    def closeEvent(self, event):
        """Clean shutdown"""
        try:
            # Stop all timers
            self.scroll_timer.stop()
            self.priority_timer.stop()
            self.memory_timer.stop()

            # Wait for thread pools to finish
            self.fast_thread_pool.waitForDone(1000)  # Wait max 1 second
            self.background_thread_pool.waitForDone(1000)

            # Cleanup document
            self.cleanup_previous_document()

            event.accept()
        except Exception as e:
            logging.error(f"Error during shutdown: {e}")
            event.accept()

    def cleanup_previous_document(self):
        self.pdf_utils_obj.cleanupprevious_document(self)

    def go_to_next_page(self):
        if self.pdf_doc and self.current_page < len(self.pdf_doc) - 1:
            self.current_page += 1
            self.page_spinbox.setValue(self.current_page + 1)
            self._ensure_batch_for_current_page()
            self.display_single_page(self.current_page)
            QTimer.singleShot(10, self.displayContent)

    def go_to_previous_page(self):
        if self.pdf_doc and self.current_page > 0:
            self.current_page -= 1
            self.page_spinbox.setValue(self.current_page + 1)
            self._ensure_batch_for_current_page()
            self.display_single_page(self.current_page)
            QTimer.singleShot(10, self.displayContent)

    def _ensure_batch_for_current_page(self):
        if not hasattr(self, 'batches_submitted'):
            self.batches_submitted = set()
        page = self.current_page
        batch_index = page // self.batch_size
        if batch_index not in self.batches_submitted:
            self.create_and_submit_batch(batch_index)

    def go_to_page(self, page_number):
        """Go to a specific page (1-based index from user)"""
        target_page = page_number - 1  # Convert to 0-based index

        if self.pdf_doc and 0 <= target_page < len(self.pdf_doc):
            self.current_page = target_page
            self.page_spinbox.setValue(self.current_page + 1)
            self._ensure_batch_for_current_page()
            self.display_single_page(self.current_page)

    def update_window_title(self):
        if hasattr(self, 'pdf_filename') and self.pdf_filename:
            self.setWindowTitle(f"PDF Viewer - {self.pdf_filename}")
        else:
            self.setWindowTitle("PDF Viewer")
    def calculate_page_height_for_viewport(self):
        """Calculate page height to fit exactly one page in viewport"""
        if not hasattr(self, 'scroll_area'):
            return 800  # default height

        viewport_height = self.scroll_area.viewport().height()
        # Reserve some space for margins/spacing
        available_height = viewport_height - 20  # 20px for margins
        return max(available_height, 600)  # minimum 600px height


    @pyqtSlot(int, list)
    def _update_page_ui(self, page_number, zones):
        try:
            if not hasattr(self, 'zones_data_by_page') or self.zones_data_by_page is None:
                self.zones_data_by_page = {}
            if not hasattr(self, 'zones_data'):
                self.zones_data = []

            # Store zones
            self.zones_data_by_page[page_number] = zones
            self.zones_data.extend(zones)

            # ✅ If the page is currently displayed and has a scene, try rendering immediately
            if page_number == self.current_page and page_number in self.active_scenes:
                scene = self.active_scenes[page_number]
                cached_data = self.page_cache.get(page_number)
                used_zoom = cached_data[1] if cached_data else self.zoom_factor
                self.add_zones_to_scene_fast(scene, page_number, used_zoom)
                self.zones_added.add(page_number)
                logging.info(f"Zones rendered immediately for current page {page_number}")
            # else:
            #     logging.info(f"Scene for page {page_number} not ready yet. Will render later.")

            # Stop loading dialog if any
            if self.loading_dialog:
                self.loading_dialog.stop()
                self.loading_dialog = None

            # Update performance label
            ready_pages = len(self.zones_data_by_page)
            total_zones = len(self.zones_data)
            total_pages = len(self.pdf_doc) if self.pdf_doc else 0

            self.performance_label.setText(
                f"Pages with zones: {ready_pages}/{total_pages} | Total zones: {total_zones}"
            )
            if page_number == self.current_page:
                QTimer.singleShot(10, self.displayContent)

        except Exception as e:
            traceback.print_exc()
            logging.error(f"Error in _update_page_ui: {e}")

    def render_pending_zones(self):
        page_number = self.current_page
        scene = self.active_scenes.get(page_number)
        if not scene:
            return

        zones = self.zones_data_by_page.get(page_number, [])
        if not zones:
            return

        has_zone = any(isinstance(item, ResizableZone) for item in scene.items())
        if not has_zone:
            used_zoom = self.page_cache.get(page_number, (None, self.zoom_factor))[1]
            self.add_zones_to_scene_fast(scene, page_number, used_zoom)

    def prepare_batch_extraction(self, full_pdf_path):
        self.full_doc = fitz.open(full_pdf_path)
        self.total_pages = self.full_doc.page_count
        self.total_batches = (self.total_pages + self.batch_size - 1) // self.batch_size
        self.original_pdf_name = os.path.splitext(os.path.basename(full_pdf_path))[0]
        self.batches_submitted.clear()
        self.current_batch_index = 0
        self.create_and_submit_batch(0)

    def create_and_submit_batch(self, batch_index):
        try:
            if batch_index in self.batches_submitted or batch_index >= self.total_batches:
                return

            start_page = batch_index * self.batch_size
            end_page = min(start_page + self.batch_size, self.total_pages)
            temp_path = f"temp/{self.original_pdf_name}_batch_{start_page}_{end_page}.pdf"

            batch_doc = fitz.open()
            for i in range(start_page, end_page):
                batch_doc.insert_pdf(self.full_doc, from_page=i, to_page=i)
            batch_doc.save(temp_path)
            batch_doc.close()

            self.batches_submitted.add(batch_index)
            self.current_batch_index = batch_index

            if batch_index == 0 and self.loading_dialog is None:
                self.loading_dialog = LoadingDialog("Extracting zones...", self)
                self.loading_dialog.setModal(False)
                self.loading_dialog.show()
                self.loading_dialog.start()

            task = BackgroundZoneExtractionTask(
                file_path=temp_path,
                page_offset=start_page,
                on_finish=self.handle_batch_finish,
                on_page=self.handle_page_zone,
            )
            self.background_thread_pool.start(task)
        except Exception as e:
            traceback.print_exc()

    def handle_page_zone(self, page_number, zones):
        logging.info(f"Zone extracted for page {page_number} ({len(zones)} zones)")

        QMetaObject.invokeMethod(
            self,
            "_update_page_ui",
            Qt.QueuedConnection,
            Q_ARG(int, page_number),
            Q_ARG(list, zones)
        )

        if page_number == self.current_page:
            QTimer.singleShot(250, self.displayContent)
            QTimer.singleShot(300, self.render_pending_zones)

    def handle_batch_finish(self, extractor):
        try:
            if extractor and hasattr(extractor, 'file_path'):
                os.remove(extractor.file_path)
                logging.info(f"Deleted temp batch file: {extractor.file_path}")
        except Exception as e:
            logging.warning(f"Failed to delete batch file: {e}")

        if self.zones_data_by_page == {}:
            if self.loading_dialog:
                self.loading_dialog.stop()
                self.loading_dialog = None

        next_batch = self.current_batch_index + 1
        if next_batch < self.total_batches:
            logging.info(f"Queueing next batch: {next_batch}")
            QTimer.singleShot(100, lambda: self.create_and_submit_batch(next_batch))
        else:
            logging.info("All batches completed")

    ########################## File save Logic ###############################
    def save_zones_to_json(self):
        if not self.doc_path:
            return
        all_zones = []
        for page, zones in self.zones_data_by_page.items():
            for zone in zones:
                if zone.get("page") is None:
                    zone["page"] = page
                all_zones.append(zone)
        os.makedirs("saved_zones", exist_ok=True)
        base_name = os.path.basename(self.doc_path)
        name_without_ext = os.path.splitext(base_name)[0]
        save_path = os.path.join("saved_zones", f"{name_without_ext}.json")
        os.makedirs("temp_train_data", exist_ok=True)
        # Create subdirectory for this specific PDF
        pdf_train_dir = os.path.join("temp_train_data", name_without_ext)
        os.makedirs(pdf_train_dir, exist_ok=True)
        train_data_path = os.path.join(pdf_train_dir, name_without_ext+".json")

        image_data = self.convert_pdf_to_images(self.doc_path, pdf_train_dir)

        self.extract_bboxes(all_zones,image_data[0],train_data_path,name_without_ext)
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(all_zones, f, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save zones: {str(e)}")

    def convert_pdf_to_images(self, pdf_path, output_dir,image_format="png", max_pages=None):
        print(f"Converting PDF to images: {pdf_path}")

        images_dir = os.path.join(output_dir, "images")
        os.makedirs(images_dir, exist_ok=True)

        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            print(f"Error opening PDF: {e}")
            return []

        pdf_name = Path(pdf_path).stem
        total_pages = len(doc)
        pages_to_convert = min(max_pages, total_pages) if max_pages else total_pages

        print(f"Converting {pages_to_convert} pages from {total_pages} total pages...")

        created_images = []

        for page_num in range(pages_to_convert):
            try:
                print(f"Converting page {page_num + 1}/{pages_to_convert}...")

                page = doc.load_page(page_num)

                # Convert DPI to scale factor
                mat = fitz.Matrix(self.zoom_factor, self.zoom_factor)

                # Optimized pixmap creation
                pix = page.get_pixmap(
                    matrix=mat,
                    alpha=False,
                    colorspace=fitz.csRGB,
                    annots=False
                )

                # Create filename
                if total_pages == 1:
                    image_filename = f"{pdf_name}.{image_format}"
                else:
                    image_filename = f"{pdf_name}_page_{page_num + 1:03d}.{image_format}"

                image_path = os.path.join(images_dir, image_filename)

                if image_format.lower() in ['jpg', 'jpeg']:
                    img_data = pix.tobytes("png")
                    pil_image = Image.open(io.BytesIO(img_data))
                    if pil_image.mode == 'RGBA':
                        background = Image.new('RGB', pil_image.size, (255, 255, 255))
                        background.paste(pil_image, mask=pil_image.split()[-1])
                        pil_image = background
                    pil_image.save(image_path, 'JPEG', quality=95)
                else:
                    pix.save(image_path)

                page_info = {
                    "page_number": page_num + 1,
                    "image_path": image_path,
                    "image_filename": image_filename,
                    "width": pix.width,
                    "height": pix.height,
                    "original_page_size": [float(page.rect.width), float(page.rect.height)],
                    "scale_factor": self.zoom_factor
                }

                created_images.append(page_info)

                print(f"  ✓ Saved: {image_filename} ({pix.width}x{pix.height})")


            except Exception as e:
                print(f"  ✗ Error converting page {page_num + 1}: {e}")
                continue

        doc.close()
        return created_images
    def extract_bboxes(self, data, image_data, train_data_path,name_without_ext):
        annotations = {}
        objects = []
        train_data = []
        bboxes = []
        words = []
        labels = []
        for item in data:
            if 'bbox' in item:
                bbox = item['bbox']
            else:
                continue
            objects.append({
                "bbox": bbox,
                "label": "paragraph",
                "page": item.get("page", 0) + 1,
                "text": item.get("text", ""),
                "reading_order": 1
            })

        annotations["id"] = f"{name_without_ext}_{self.current_page + 1}"
        annotations["image_width"] = image_data["width"]
        annotations["image_height"] = image_data["height"]
        annotations["image_path"] = image_data["image_path"]
        annotations["paragraphs"] = objects

        # train_data.append(train_object)
        # Save the train data
        with open(train_data_path, "w", encoding="utf-8") as f:
            json.dump(annotations, f, indent=4, ensure_ascii=False)

    def open_pdf_with_zones_if_available(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open PDF", "", "PDF Files (*.pdf)")
        if not file_path:
            return
        self.cleanup_previous_document()
        self.doc_path = file_path
        self.pdf_doc = fitz.open(file_path)
        self.full_doc = self.pdf_doc
        self.page_spinbox.setValue(0)
        base_name = os.path.basename(file_path)
        name_without_ext = os.path.splitext(base_name)[0]
        json_path = os.path.join("saved_zones", f"{name_without_ext}.json")

        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    loaded_zones = json.load(f)
                    self.zones_data = loaded_zones
                    self.zones_data_by_page = {}

                    for zone in loaded_zones:
                        pg = zone.get("page", 1)
                        self.zones_data_by_page.setdefault(pg, []).append(zone)

                logging.info(f"Loaded zones from {json_path}")
            except Exception as e:
                logging.warning(f"Failed to load saved zones: {e}")
                self.zones_data = []
                self.zones_data_by_page = {}
        else:
            logging.info(f"No saved zones found for {file_path}, running extractor")
            self.zones_data = []
            self.zones_data_by_page = {}
            self.create_and_submit_batch(0)

        self.current_page = 0
        self.display_single_page(0)

        # 🔁 Render zones if already loaded
        QTimer.singleShot(20, self.render_pending_zones)

        # Setup page controls
        self.page_spinbox.setRange(1, len(self.full_doc))
        self.page_spinbox.setValue(1)
        self.page_spinbox.valueChanged.connect(self.go_to_page)

        QTimer.singleShot(30, self.displayContent)


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    app.setApplicationName("Fast PDF Viewer")
    app.setApplicationVersion("1.0")

    # Logging setup
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('pdf_viewer.log')
        ]
    )

    try:
        viewer = PDFViewer()
        viewer.show()
        sys.exit(app.exec_())

    except Exception as e:
        logging.critical(f"Critical error starting application: {e}")
        traceback.print_exc()
        QMessageBox.critical(None, "Startup Error", f"{e}")
        sys.exit(1)

if __name__ == "__main__":
    main()