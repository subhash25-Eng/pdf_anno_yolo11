import logging
import traceback
import fitz
from PyQt5 import sip
from PyQt5.QtGui import QImage, QPixmap, QColor, QPen, QBrush, QPainter
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from display_content import scroll_to_zone_id
from resizable_zone import ResizableZone
from html_viewer import HtmlSourceViewer
from zone_creation import ZoneCreationGraphicsView
from PyQt5.QtGui import QFont

class LightweightPageWidget(QWidget):
    def __init__(self, page_number, estimated_height=800):
        super().__init__()
        self.page_number = page_number
        self.setMinimumHeight(estimated_height)
        # self.setMinimumWidth(600)
        self._loaded = False
        self._view = None
        self._scene = None

        # Placeholder for unloaded pages
        self.placeholder_label = QLabel(f"Page {page_number + 1}")
        self.placeholder_label.setAlignment(Qt.AlignCenter)
        self.placeholder_label.setStyleSheet("background-color: #f0f0f0; border: 1px solid #ccc;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.placeholder_label)

    def set_content(self, view, scene):
        """Replace placeholder with actual content"""
        if self._loaded:
            return

        # Clear existing widgets from layout
        layout = self.layout()
        if layout:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

        # Add real content
        layout.addWidget(view)

        self._view = view
        self._scene = scene
        self._loaded = True

    def clear_content(self):
        """Revert to placeholder"""
        if not self._loaded:
            return

        # Remove real content
        layout = self.layout()
        if layout:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().setParent(None)

        # Restore placeholder
        self.placeholder_label = QLabel(f"Page {self.page_number + 1}")
        self.placeholder_label.setAlignment(Qt.AlignCenter)
        self.placeholder_label.setStyleSheet("background-color: #f0f0f0; border: 1px solid #ccc;")
        layout.addWidget(self.placeholder_label)

        self._view = None
        self._scene = None
        self._loaded = False

class FastRenderSignals(QObject):
    finished = pyqtSignal(int, QImage, float)
    error = pyqtSignal(int, str)


class FastRenderTask(QRunnable):
    """Ultra-fast rendering task for immediate loading"""

    def __init__(self, doc_path, page_number, zoom, callback, error_callback=None, priority=False):
        super().__init__()
        self.doc_path = doc_path
        self.page_number = page_number
        self.zoom_factor = zoom
        self.priority = priority
        self.signals = FastRenderSignals()
        self.signals.finished.connect(callback)
        if error_callback:
            self.signals.error.connect(error_callback)

    def run(self):
        doc = None
        try:
            if self.priority:
                effective_zoom = self.zoom_factor
                use_alpha = False
                colorspace = fitz.csRGB
            else:
                effective_zoom = self.zoom_factor
                use_alpha = False
                colorspace = fitz.csRGB
            doc = fitz.open(self.doc_path)
            page = doc.load_page(self.page_number)

            # Optimized matrix
            mat = fitz.Matrix(effective_zoom, effective_zoom)

            # Ultra-fast pixmap creation
            pix = page.get_pixmap(
                matrix=mat,
                alpha=use_alpha,
                colorspace=colorspace,
                annots=True
            )
            print("image pix ++++++ ",pix)
            # Fast QImage conversion
            fmt = QImage.Format_RGB888
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()

            # Immediate cleanup
            del pix, page
            self.signals.finished.emit(self.page_number, img, effective_zoom)

        except Exception as e:
            error_msg = f"Fast render error on page {self.page_number}: {str(e)}"
            logging.error(error_msg)
            self.signals.error.emit(self.page_number, error_msg)
        finally:
            if doc:
                doc.close()
###########################################################################
# pdf_utils.py
from richtexteditor import RichTextEditor
class PdfUtils:
    def __init__(self, viewer_instance):
        self.pdf_viewer = viewer_instance
        # Add this to your class initialization
        self.sequence_circles_visible = True
        self.sequence_circle_groups = []  # Store references to all circle groups
    def showtextviewer(self, viewer):
        """Attach a RichTextEditor to the viewer dynamically."""
        if not hasattr(viewer, 'rich_text_editor'):
            viewer.rich_text_editor = RichTextEditor()

        viewer.splitter.replaceWidget(1, viewer.rich_text_editor)
        viewer.text_display = viewer.rich_text_editor
        viewer.current_text_viewer = "text_viewer"

    def mergezones(self, viewer, selected_zones):
        """Merge multiple selected zones into one"""
        try:
            if len(selected_zones) < 2:
                QMessageBox.warning(viewer, "Merge Error", "Select at least 2 zones to merge.")
                return

            # Get the page number and ensure all zones are on the same page
            page_num = selected_zones[0].zone_data.get("page", 1)
            for zone in selected_zones[1:]:
                if zone.zone_data.get("page", 1) != page_num:
                    QMessageBox.warning(viewer, "Merge Error", "All zones must be on the same page to merge.")
                    return

            # Calculate bounding rectangle in scene coordinates
            merged_rect = selected_zones[0].mapRectToScene(selected_zones[0].rect())
            for zone in selected_zones[1:]:
                zone_rect = zone.mapRectToScene(zone.rect())
                merged_rect = merged_rect.united(zone_rect)

            # Convert back to PDF coordinates using the same logic as ResizableZone.update_zone_data()
            page = viewer.pdf_doc.load_page(page_num - 1)
            pdf_height = page.rect.height

            x = merged_rect.left() / viewer.zoom_factor
            width = merged_rect.width() / viewer.zoom_factor
            height = merged_rect.height() / viewer.zoom_factor

            # Convert Y coordinate from screen space back to PDF space
            screen_y = merged_rect.top() / viewer.zoom_factor
            y = pdf_height - screen_y - height

            zone_type = selected_zones[0].zone_data.get("type", "paragraph")
            page_number = selected_zones[0].zone_data.get("page")
            zonestodelete = []

            # Create new merged zone data
            new_zone = {
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "page": page_num,
                "type": zone_type,
                "action_type":"new_zone"
            }
            scene = selected_zones[0].scene()

            for zone in selected_zones:
                if zone.zone_data in viewer.zones_data_by_page.get(page_number, []):
                    viewer.zones_data_by_page.get(page_number, []).remove(zone.zone_data)
                    zonestodelete.append(zone.zone_data.get("block_id"))
                scene.removeItem(zone)

            # Add new merged zone
            rect_item = ResizableZone(
                merged_rect,
                new_zone,
                viewer.zoom_factor,
                viewer.zones_data_by_page.get(page_number, []),
                viewer.on_zones_updated,
                viewer=viewer
            )
            zones_data_copy = viewer.zones_data_by_page.get(page_number, [])
            new_zone["block_id"] = zonestodelete[0]
            for _id in zonestodelete:
                zone_data = rect_item.pop_value_by_id(zones_data_copy, _id)
            viewer.zones_data_by_page[page_number] = zone_data
            new_text = rect_item.extract_text_from_zone()
            new_zone["text"] = new_text
            viewer.insert_zone_in_order(new_zone)
            rect_item.setSelected(True)
            self.addzones_to_scene_fast(viewer, scene, page_number, viewer.zoom_factor, True)
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(viewer, "Merge Error", f"Failed to merge zones:\n{str(e)}")

    def createpageviewfast(self, viewer, page_number, image, used_zoom):
        """Fast creation of a single page view"""
        try:
            if page_number in viewer.active_scenes:
                old_scene = viewer.active_scenes.pop(page_number)
                if old_scene:
                    old_scene.clear()

            if page_number in viewer.active_views:
                old_view = viewer.active_views.pop(page_number)
                if old_view:
                    old_view.deleteLater()

            scene = QGraphicsScene()
            view = ZoneCreationGraphicsView(scene, viewer, page_number)

            pixmap = QPixmap.fromImage(image)
            view.setMinimumHeight(pixmap.height())
            view.setMinimumWidth(pixmap.width())
            scene.addPixmap(pixmap)
            # ✅ Add zones if available and needed
            if page_number in viewer.zones_data_by_page:
                zones = viewer.zones_data_by_page[page_number]
                has_zone = any(isinstance(item, ResizableZone) for item in scene.items())
                if not has_zone and zones:
                    viewer.add_zones_to_scene_fast(scene, page_number, used_zoom)

            # 🧱 Add to scroll layout
            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(view)
            viewer.scroll_layout.addWidget(container)

            # Update references
            viewer.active_scenes[page_number] = scene
            viewer.active_views[page_number] = view

        except Exception as e:
            logging.error(f"Error in createpageviewfast({page_number}): {e}")

    def addzones_to_scene_fast(self, viewer, scene, page_number, used_zoom,re_arranged_sequence=False):
        try:
            if not scene:
                scene = self.pdf_viewer.active_scenes.get(page_number)


            for item in list(scene.items()):
                if isinstance(item, ResizableZone) or isinstance(item, QGraphicsItemGroup):
                    scene.removeItem(item)

            if not used_zoom:
                used_zoom = viewer.zoom_factor

            zones = viewer.zones_data_by_page.get(page_number, [])
            if not zones:
                return

            page = viewer.pdf_doc.load_page(page_number)
            page_height = page.rect.height
            zoom = used_zoom

            if any("sequence_number" in z for z in zones):
                zones = sorted(zones, key=lambda z: z.get("sequence_number", 0))

            for i, zone in enumerate(zones):

                #sequence_number = zone.get("sequence_number", i + 1)

                x = zone["x"] * zoom
                # y = (page_height - zone["y"] - zone["height"]) * zoom
                y = zone["y"] * zoom
                w = zone["width"] * zoom
                h = zone["height"] * zoom
                zone_color = zone.get("zone_color")

                if re_arranged_sequence:
                    sequence_number = i + 1
                    zone["sequence_number"] = sequence_number
                else:
                    sequence_number = zone.get("sequence_number")
                    if sequence_number is None:
                        sequence_number = i + 1
                        zone["sequence_number"] = sequence_number


                if "block_id" not in zone:
                    zone_page = zone.get("page", page_number + 1)
                    zone["block_id"] = f"page-{zone_page}-block-{hash((zone['x'], zone['y'])) & 0xfffff}"

                zone_item = ResizableZone(
                    QRectF(x, y, w, h),
                    zone,
                    zoom,
                    viewer.zones_data,
                    viewer.on_zones_updated,
                    viewer,
                    zone_color
                )
                scene.addItem(zone_item)

                # Attach circle (scene passed explicitly)

                self.add_sequence_number_circle_attached(scene, zone_item, sequence_number, zoom)
        except Exception as e:
            logging.error(f"Error adding zones to page {page_number}: {e}")
            traceback.print_exc()

    def toggle_sequence_circles(self):
        """Toggle visibility of all sequence circles"""
        self.sequence_circles_visible = not self.sequence_circles_visible

        # Clean up deleted groups and update existing ones
        valid_groups = []

        for group in self.sequence_circle_groups:
            try:
                if not sip.isdeleted(group) and group.scene():
                    group.setVisible(self.sequence_circles_visible)
                    valid_groups.append(group)
                # If group.scene() is None, the group was removed but object still exists
                elif not sip.isdeleted(group):
                    valid_groups.append(group)  # Keep reference in case it gets re-added
            except (RuntimeError, AttributeError):
                # Object was deleted, skip it
                continue

        # Update the list with only valid groups
        self.sequence_circle_groups = valid_groups

    def add_sequence_number_circle_attached(self, scene, zone_item, sequence_number, zoom):
        try:
            if not scene:
                scene = zone_item.scene()
                if not scene:
                    print("⚠️ No scene found. Cannot attach sequence circle.")
                    return

            base_radius = 12
            circle_radius = base_radius * zoom

            # Position at top-left of the zone
            zone_bounds = zone_item.sceneBoundingRect()
            circle_x = zone_bounds.left()
            circle_y = zone_bounds.top()

            # Create circle pixmap
            pixmap_size = int(circle_radius * 2)
            pixmap = QPixmap(pixmap_size, pixmap_size)
            pixmap.fill(Qt.transparent)

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QBrush(QColor(255, 255, 153, 200)))  # light yellow
            painter.setPen(QPen(QColor(204, 204, 0), 2))  # border
            painter.drawEllipse(1, 1, pixmap_size - 2, pixmap_size - 2)
            painter.end()

            circle_item = QGraphicsPixmapItem(pixmap)
            circle_item.setOffset(circle_x, circle_y)
            circle_item.setZValue(1000)

            # Create text label
            text_item = QGraphicsTextItem(str(sequence_number))
            font = QFont("Segoe UI", max(8, int(7 * zoom)), QFont.Bold)
            text_item.setFont(font)
            text_item.setDefaultTextColor(QColor(0, 0, 0))
            text_item.setZValue(1001)

            text_rect = text_item.boundingRect()
            text_item.setPos(
                circle_x + circle_radius - text_rect.width() / 2,
                circle_y + circle_radius - text_rect.height() / 2
            )

            # Group circle + text
            group = QGraphicsItemGroup()
            group.addToGroup(circle_item)
            group.addToGroup(text_item)
            group.setZValue(1000)

            # Set initial visibility based on current state
            group.setVisible(self.sequence_circles_visible)

            # ✅ Tag group with block_id
            block_id = zone_item.zone_data.get("block_id")
            if not block_id:
                print("❌ block_id missing in zone_data")
                return

            group.setData(0, block_id)

            scene.addItem(group)

            # Store reference to the group for toggling visibility
            self.sequence_circle_groups.append(group)


        except Exception as e:
            logging.error(f"Error attaching sequence number circle: {e}")
            traceback.print_exc()

    def createzone(self, viewer, rect, scene, page_number):
        try:
            if not viewer.pdf_doc:
                QMessageBox.warning(viewer, "No Document", "Please open a PDF document first.")
                return

            page = viewer.pdf_doc.load_page(page_number)
            pdf_height = page.rect.height

            # Convert from scene to PDF coordinates
            x = rect.left() / viewer.zoom_factor
            width = rect.width() / viewer.zoom_factor
            height = rect.height() / viewer.zoom_factor

            screen_y = rect.top() / viewer.zoom_factor
            y = pdf_height - screen_y - height

            # Determine sequence number
            if page_number in viewer.zones_data_by_page:
                existing_zones = viewer.zones_data_by_page[page_number]
                max_sequence = max([zone.get('sequence_number', 0) for zone in existing_zones], default=0)
            else:
                max_sequence = 0

            new_zone = {
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "page": page_number ,
                "block_id": f"pz{page_number + 1}-{max_sequence + 1}",
                "type": "paragraph",
                "action_type": "new_zone",
                "sequence_number": max_sequence + 1,
                "span_id": f'z{page_number + 1}-{max_sequence + 1}'
            }

            zone_item = ResizableZone(
                rect,
                new_zone,
                viewer.zoom_factor,
                viewer.zones_data,
                viewer.on_zones_updated,
                viewer=viewer
            )

            # Extract and attach text to the zone
            new_text = zone_item.extract_text_from_zone()
            new_zone["text"] = new_text

            # Add to scene
            scene.addItem(zone_item)

            self.add_sequence_number_circle_attached(scene, zone_item, new_zone["sequence_number"], viewer.zoom_factor)

            # Update internal data
            viewer.insert_zone_in_order(new_zone)
            zone_item.setSelected(True)
            viewer.zone_history.append(zone_item)
            viewer.on_zones_updated()


        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(viewer, "Creation Error", f"Failed to create zone:\n{str(e)}")

    def clear_sequence_circles(self):
        """Clear all sequence circles (call this when refreshing/clearing zones)"""
        for group in self.sequence_circle_groups[:]:  # Use slice to avoid modification during iteration
            try:
                if not sip.isdeleted(group) and group.scene():
                    group.scene().removeItem(group)
            except (RuntimeError, AttributeError):
                # Object already deleted, skip
                continue
        self.sequence_circle_groups.clear()

    def cleanup_removed_circles(self):
        """Remove references to circles that are no longer in the scene or have been deleted"""
        valid_groups = []
        for group in self.sequence_circle_groups:
            try:
                if not sip.isdeleted(group):
                    valid_groups.append(group)
            except (RuntimeError, AttributeError):
                # Object was deleted, skip it
                continue
        self.sequence_circle_groups = valid_groups

    def insert_new_zone_toall_html(self, viewer, new_zone):
        current_page = viewer.current_page
        current_page_zone = viewer.zones_data_by_page.get(current_page, [])

        scene = self.pdf_viewer.active_scenes.get(current_page)
        if scene:
            # Remove all ResizableZone items from the QGraphicsScene
            for item in scene.items():
                if isinstance(item, ResizableZone):
                    scene.removeItem(item)

        def zone_top_y(z):
            if "y" in z:
                return z["y"]
            elif "bbox" in z:
                return z["bbox"][1]
            return 0

        def get_zone_x(z):
            if "x" in z:
                return z["x"]
            elif "bbox" in z:
                return z["bbox"][0]
            return 0

        # Remove the new zone if it's already in the list (to avoid duplicates)
        current_page_zone = [zone for zone in current_page_zone if zone != new_zone]

        # Sort all zones (including new zone) by reading order
        all_zones = current_page_zone + [new_zone]

        def reading_order_key(zone):
            y = zone_top_y(zone)
            x = get_zone_x(zone)
            column = 0 if x < 200 else 1
            return (column, -y)

        # Sort zones in reading order (top-to-bottom, left-to-right)
        all_zones.sort(key=reading_order_key)
        page_num = current_page + 1
        for i, zone in enumerate(all_zones):
            block_id = f'pz{page_num}-{i + 1}'
            zone['block_id'] = block_id
            zone['span_id'] = f'z{page_num}-{i + 1}'
            if 'zone_object' in zone:
                original = zone.get("zone_object")
                zone["zone_object"] = self.update_id_in_string(original, block_id)
        viewer.zones_data_by_page[current_page] = all_zones

        # Update the zones data
        viewer.zones_data_by_page[current_page] = all_zones

        # Re-add zones to scene
        has_zone = any(isinstance(item, ResizableZone) for item in scene.items())
        if not has_zone:
            used_zoom = self.pdf_viewer.page_cache.get(current_page, (None, self.pdf_viewer.zoom_factor))[1]
            self.addzones_to_scene_fast(viewer, scene, current_page, used_zoom)

        # Update HTML display
        if viewer.current_text_viewer == "html_viewer":
            html = viewer.text_display.generate_clean_html(all_zones)
            formatted_html = viewer.text_display.format_html(html)
            viewer.text_display.html_editor.setText(formatted_html)
            viewer.text_display.scroll_to_zone_html(block_id)
        else:
            html_viewer = HtmlSourceViewer(viewer)
            html = html_viewer.generate_clean_html(all_zones)
            formatted_html = html_viewer.format_html(html)
            viewer.rich_text_editor.set_html(formatted_html)
            scroll_to_zone_id(viewer.rich_text_editor,block_id)

    def update_id_in_string(self,tag_str: str, new_id: str) -> str:
        if "'id': '" in tag_str:
            prefix = tag_str.split("'id': '")[0]
            suffix = tag_str.split("'id': '")[1].split("'")[1:]
            updated_tag = prefix + f"'id': '{new_id}'" + "'" + "'".join(suffix)
            return updated_tag
        else:
            raise ValueError("No 'id' key found in string.")
    def cleanupprevious_document(self,viewer):
        try:
            # Stop all timers
            viewer.scroll_timer.stop()
            viewer.priority_timer.stop()
            if hasattr(viewer, 'scroll_layout'):
                while viewer.scroll_layout.count():
                    item = viewer.scroll_layout.takeAt(0)
                    widget = item.widget()
                    if widget:
                        widget.setParent(None)
                        widget.deleteLater()
            viewer.active_views.clear()
            viewer.active_scenes.clear()
            viewer.page_cache.clear()
            viewer.page_widgets.clear()
            viewer.zones_data_by_page = {}
            viewer.zones_data = []
            viewer.zones_added.clear()

            # Clear text viewer content
            if hasattr(viewer, 'text_display') and viewer.text_display:
                from richtexteditor import  RichTextEditor
                try:
                    viewer.text_display.html_editor.clear()
                    rich_txt_obj = RichTextEditor()
                    rich_txt_obj.text_editor.setHtml("")
                except Exception:
                    pass

            # Clear zone extractor and zone-related data
            viewer.zone_extractor = None
            viewer.zones_data = []  # Clear zones data

            # Clear all zone tracking sets
            viewer.zones_added.clear()
            viewer.zone_history.clear()

            # Close PDF document
            if viewer.pdf_doc:
                viewer.pdf_doc.close()
                viewer.pdf_doc = None

            # Clear all graphics scenes and their items (including zones)
            for scene in viewer.active_scenes.values():
                if scene:
                    # Clear all items from scene (including zone rectangles)
                    scene.clear()
                    scene.deleteLater()

            # Clear all views
            for view in viewer.active_views.values():
                if view:
                    view.deleteLater()

            # Clear all data structures that exist in your code
            viewer.page_cache.clear()
            viewer.active_scenes.clear()
            viewer.active_views.clear()

            # Clear and delete page widgets
            for widget in viewer.page_widgets:
                widget.clear_content()  # This should clear any zone graphics
                widget.deleteLater()
            viewer.page_widgets.clear()

            # Clear page positions if it exists
            if hasattr(viewer, 'page_positions'):
                viewer.page_positions.clear()

            if hasattr(viewer, 'page_layout') and viewer.page_layout is not None:
                try:
                    while viewer.page_layout.count():
                        child = viewer.page_layout.takeAt(0)
                        if child.widget():
                            child.widget().deleteLater()
                except RuntimeError:
                    # Layout already deleted, skip
                    pass

            # Reset state flags
            viewer.document_ready = False
            viewer.creation_mode = False
            viewer.last_scroll_position = 0

            # if hasattr(viewer, 'zone_refresh_timer'):
            #     viewer.zone_refresh_timer.stop()

            viewer.batches_submitted.clear()
            viewer.current_batch_index = 0
            viewer.full_doc = None

            viewer.zones_data_by_page = {}
            viewer.zones_data = []
            viewer.zones_added.clear()
            viewer.active_scenes.clear()
            viewer.active_views.clear()
            viewer.page_cache.clear()

            for view in getattr(viewer, "page_widgets", []):
                view.deleteLater()
            viewer.page_widgets = []

            if hasattr(viewer, "page_layout"):
                while viewer.page_layout.count():
                    item = viewer.page_layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()

            # Clear text display
            # self.text_display.clear()
            if viewer.pdf_doc:
                viewer.pdf_doc.close()
                viewer.pdf_doc = None

            viewer.doc_path = None
            viewer.document_ready = False
            viewer.last_scroll_position = 0

            # Reset status labels
            viewer.page_info_label.setText("No document")
            viewer.performance_label.setText("Ready")
            viewer.memory_info_label.setText("Memory: 0/0")

            # Clear any additional collections that might exist (defensive programming)
            # These are the ones you mentioned - clear them if they exist
            if hasattr(viewer, 'page_views'):
                viewer.page_views.clear()
            if hasattr(viewer, 'page_scenes'):
                viewer.page_scenes.clear()
            if hasattr(viewer, 'graphics_views'):
                viewer.graphics_views.clear()
            if hasattr(viewer, 'rendered_pages'):
                viewer.rendered_pages.clear()
            # Clear document path
            viewer.doc_path = None
            # Force garbage collection
            import gc
            gc.collect()
            logging.info("Previous document cleaned up completely")
        except Exception as e:
            logging.warning(f"Cleanup error: {e}")

    def replace_sequence_number(self, viewer, selected_zones):
        """replace_sequence_number"""
        try:
            if len(selected_zones) < 2 or len(selected_zones) > 2:
                QMessageBox.warning(viewer, "replace_sequence_number Error",
                                    "Select only 2 zones to replace sequence no.")
                return

            # Get the page number and ensure all zones are on the same page
            page_num = selected_zones[0].zone_data.get("page", 1)
            for zone in selected_zones[1:]:
                if zone.zone_data.get("page", 1) != page_num:
                    QMessageBox.warning(viewer, "replace_sequence_number Error",
                                        "All zones must be on the same page to replace sequence no.")
                    return

            page_number = selected_zones[0].zone_data.get("page")
            zones_data = viewer.zones_data_by_page.get(page_number, [])
            first_zone_sequence_no = selected_zones[0].zone_data.get('sequence_number')
            second_zone_sequence_no = selected_zones[1].zone_data.get('sequence_number')

            # Get block IDs to identify zones in the list
            first_zone_block_id = selected_zones[0].zone_data.get("block_id")
            second_zone_block_id = selected_zones[1].zone_data.get("block_id")

            # Find and update sequence numbers in the zones_data list
            for zone in zones_data:
                if zone.get("block_id") == first_zone_block_id:
                    zone["sequence_number"] = second_zone_sequence_no
                elif zone.get("block_id") == second_zone_block_id:
                    zone["sequence_number"] = first_zone_sequence_no

            scene = self.pdf_viewer.active_scenes.get(page_number)
            if scene:
                for item in scene.items():
                    if isinstance(item, ResizableZone):
                        scene.removeItem(item)
                        if hasattr(item, 'sequence_circle') and item.sequence_circle:
                            scene.removeItem(item.sequence_circle)
                            item.sequence_circle = None

                        if hasattr(item, 'sequence_text') and item.sequence_text:
                            scene.removeItem(item.sequence_text)
                            item.sequence_text = None
            self.addzones_to_scene_fast(viewer, scene, page_number, viewer.zoom_factor)
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(viewer, "Merge Error", f"Failed to merge zones:\n{str(e)}")


class FlashMessage(QWidget):
    _instances = []  # Hold references so it doesn't get destroyed

    def __init__(self, message, msg_type="success", duration=5000, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        # Colors
        color = "#d4edda" if msg_type == 'success' else "#f8d7da"
        border_color = "#28a745" if msg_type == 'success' else "#dc3545"
        text_color = "#155724" if msg_type == 'success' else "#721c24"

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {color};
                border: 2px solid {border_color};
                color: {text_color};
                border-radius: 8px;
            }}
            QLabel {{
                padding: 10px 20px;
                font-family: Arial;
                font-size: 10pt;
            }}
        """)

        self.label = QLabel(message)
        self.label.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        # Opacity effect
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.effect.setOpacity(0)

        self.fade_anim = QPropertyAnimation(self.effect, b"opacity")
        self.fade_anim.setDuration(500)

        # Auto-hide
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.fade_out)

        # Show and position
        self._duration = duration
        self.show_message()

        # Keep reference to prevent garbage collection
        FlashMessage._instances.append(self)

    def show_message(self):
        self.adjustSize()

        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.right() - self.width() - 1
        y = screen.bottom() - self.height() - 30
        self.move(x, y)

        self.show()

        # Fade in
        self.fade_anim.stop()
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.start()

        self.timer.start(self._duration)

    def fade_out(self):
        self.fade_anim.stop()
        self.fade_anim.setStartValue(1.0)
        self.fade_anim.setEndValue(0.0)
        self.fade_anim.setDuration(500)
        self.fade_anim.finished.connect(self.cleanup)
        self.fade_anim.start()

    def cleanup(self):
        self.hide()
        if self in FlashMessage._instances:
            FlashMessage._instances.remove(self)
        self.deleteLater()


