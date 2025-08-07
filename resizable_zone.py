import json
import traceback
import logging
import fitz
from PyQt5.QtGui import QColor, QBrush, QPen, QImage, QPixmap, QKeySequence
from PyQt5.QtWidgets import QGraphicsRectItem, QGraphicsItem, QMenu, QApplication, \
    QMessageBox, QToolTip, QShortcut, QMainWindow, QGraphicsItemGroup
from PyQt5.QtCore import Qt, QPointF, QRectF, QSizeF
from display_content import scroll_to_zone_id
from configParser import config_parser
from html_viewer import HtmlSourceViewer
from zone_creation import ZoneType

class ResizableZone(QGraphicsRectItem, ZoneType):

    def __init__(self, rect, zone_data, zoom_factor, zones_data, on_update=None, viewer=None, update_callback=None):
        super().__init__(rect)
        self.update_callback = update_callback

        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsFocusable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)

        self.zoom_factor = zoom_factor
        self.on_update = on_update
        self.zones_data = zones_data
        self.zone_data = zone_data
        self.viewer = viewer
        self.handle_radius = 4
        self.handles = {}
        self.selected_handle = None
        self.is_resizing = False
        self.drag_start_pos = None
        self.init_handles()
        fill_color = QColor(self.zone_data.get("zone_color", ""))
        fill_color.setAlpha(60)
        self.setBrush(QBrush(fill_color))
        self.setPen(QPen(Qt.black, 1))

    def init_handles(self):
        r = self.rect()
        # Positions of handles on the sides (centered)
        self.handles = {
            "left": QPointF(r.left(), r.center().y()),
            "right": QPointF(r.right(), r.center().y()),
            "top": QPointF(r.center().x(), r.top()),
            "bottom": QPointF(r.center().x(), r.bottom()),
        }

    def extract_text_from_zone(self):
        """Extract text from the current zone area"""
        try:
            if not self.viewer or not self.viewer.pdf_doc:
                return ""

            page_num = self.viewer.current_page + 1
            page = self.viewer.pdf_doc.load_page(page_num - 1)

            # Get current rectangle in scene coordinates
            scene_rect = self.mapRectToScene(self.rect())

            # # Convert scene coordinates to PDF coordinates
            x1 = scene_rect.left() / self.zoom_factor
            y1 = scene_rect.top() / self.zoom_factor
            x2 = scene_rect.right() / self.zoom_factor
            y2 = scene_rect.bottom() / self.zoom_factor

            rect = fitz.Rect(x1, min(y1, y2), x2, max(y1, y2))


            # Extract text from the defined rectangle
            text = page.get_text("text", clip=rect).strip()

            if text:
                import re
                text = re.sub(r'[ \t]+', ' ', text)
                text = re.sub(r'\n\s*\n', '\n\n', text)

            return text if text else "No text found in this zone"

        except Exception as e:
            #print(f"[Error] Failed to extract text from zone: {e}")
            traceback.print_exc()
            return f"Error extracting text: {str(e)}"

    def copy_text_to_clipboard(self):
        """Copy the zone's text to clipboard"""
        try:
            text = self.extract_text_from_zone()

            # Get the clipboard
            clipboard = QApplication.clipboard()
            clipboard.setText(text)

            # Show success message
            QMessageBox.information(
                None,
                "Text Copied",
                f"Copied {len(text)} characters to clipboard:\n\n{text[:100]}{'...' if len(text) > 100 else ''}"
            )

            #print(f"📋 Copied {len(text)} characters to clipboard")

        except Exception as e:
            #print(f"[Error] Failed to copy text: {e}")
            QMessageBox.critical(None, "Copy Error", f"Failed to copy text: {str(e)}")


    def contextMenuEvent(self, event):
        menu = QMenu()

        confi_object = config_parser
        # Add copy text option at the top
        copy_text_action = menu.addAction("📋 Copy Text")
        menu.addSeparator()  # Visual separator

        delete_action = menu.addAction("Delete Zone")
        merge_action = menu.addAction("Merge Selected Zones")
        undo_action = menu.addAction("Undo Last Action")

        zone_type_menu = menu.addMenu("Change Zone Type")
        zone_string = confi_object.zones_type
        zone_list = json.loads(zone_string)

        zone_type_actions = {}
        for zone_type in zone_list:
            zone_type = zone_type.get("type")
            action = zone_type_menu.addAction(zone_type)
            zone_type_actions[action] = zone_type

        action = menu.exec_(event.screenPos())

        if action == copy_text_action:
            print("📋 Copying zone text...")
            self.copy_text_to_clipboard()

        elif action == delete_action and self.viewer:
            print("🗑️ Deleting zone...")
            self.delete_zone()

        elif action == merge_action and self.viewer:
            #print("🔀 Merging selected zones...")
            self.viewer.merge_zones(self.viewer.get_selected_zones())

        elif action == undo_action and self.viewer:
           # print("↩️ Undo last action...")
            self.viewer.undo_last_action()

        elif action in zone_type_actions:
            new_type = zone_type_actions[action]
            self.change_selected_zones_type(new_type)
            if self.viewer:
                if hasattr(self.viewer, 'scene_obj') and self.viewer.scene_obj:
                    self.viewer.scene_obj.update()
                if hasattr(self.viewer, 'graphics_view') and self.viewer.graphics_view:
                    self.viewer.graphics_view.viewport().update()
            else:
                print("⚠️ Viewer not found during type change.")


    def change_selected_zones_type(self, new_type):
        selected_items = self.scene().selectedItems()
        for item in selected_items:
            if hasattr(item, 'change_zone_type'):
                item.change_zone_type(new_type)

        zones_data = self.viewer.zones_data_by_page.get(self.viewer.current_page, [])
        block_id = selected_items[0].zone_data.get("block_id", 1)
        if zones_data and self.viewer.current_text_viewer == "html_viewer":
            scrollbar = self.viewer.text_display.html_editor.verticalScrollBar()
            current_scroll_value = scrollbar.value()
            generated_html = self.viewer.text_display.generate_clean_html(zones_data)
            formatted_html = self.viewer.text_display.format_html(generated_html)
            self.viewer.text_display.html_editor.setText(formatted_html)
            scrollbar.setValue(current_scroll_value)
            self.viewer.text_display.scroll_to_zone_html(block_id)
        else:
            html_viewer = HtmlSourceViewer(self.viewer)
            generated_html = html_viewer.generate_clean_html(zones_data)
            formatted_html = html_viewer.format_html(generated_html)
            self.viewer.rich_text_editor.set_html(formatted_html)
            scroll_to_zone_id(self.viewer.rich_text_editor, block_id)

    def boundingRect(self):
        # Expand bounding rect to include handles
        extra = self.handle_radius + 2
        return self.rect().adjusted(-extra, -extra, extra, extra)

    def paint(self, painter, option, widget=None):
        # ✅ Use stored zone_color for fill (default fallback if missing)
        color_hex = self.zone_data.get("zone_color", "#DAF7A6")
        fill_color = QColor(color_hex)
        fill_color.setAlpha(60)  # translucent fill

        # ✅ Pen based on zone type (optional)
        pen = self.pen()
        painter.setPen(pen)
        painter.setBrush(QBrush(fill_color))
        painter.drawRect(self.rect())

        # Draw handles if selected
        if self.isSelected():
            painter.setPen(QPen(Qt.white, 1))
            painter.setBrush(QBrush(Qt.darkGreen))
            for pos in self.handles.values():
                side = self.handle_radius * 2
                top_left = QPointF(pos.x() - self.handle_radius, pos.y() - self.handle_radius)
                painter.drawRect(QRectF(top_left, QSizeF(side, side)))

    def hoverMoveEvent(self, event):
        """Change cursor to resize arrows on handle hover only; allow view cursor otherwise."""
        if not self.isSelected():
            self.unsetCursor()  # Important!
            return super().hoverMoveEvent(event)

        pos = event.pos()
        handle = self.is_on_handle(pos)

        if handle == "left" or handle == "right":
            self.setCursor(Qt.SizeHorCursor)
        elif handle == "top" or handle == "bottom":
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.unsetCursor()  # ✅ Crucial: Let view’s cursor (e.g. cross) be shown

        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        QToolTip.hideText()
        self.setCursor(Qt.ArrowCursor)
        super().hoverLeaveEvent(event)

    def is_on_handle(self, pos):
        """Check if position is on any handle"""
        if not self.isSelected():
            return None

        for handle_name, handle_pos in self.handles.items():
            handle_rect = QRectF(
                handle_pos.x() - self.handle_radius / 2,
                handle_pos.y() - self.handle_radius / 2,
                self.handle_radius,
                self.handle_radius
            )
            if handle_rect.contains(pos):
                return handle_name
        return None

    def mousePressEvent(self, event):
        if self.isSelected():
            handle = self.is_on_handle(event.pos())
            if handle:
                self.selected_handle = handle
                self.is_resizing = True
                self.drag_start_pos = event.pos()  # ✅ Only for resize
                event.accept()
                return

        block_id = self.zone_data.get("block_id")
        if self.viewer.current_text_viewer=="text_viewer":
            if block_id:
                scroll_to_zone_id(self.viewer.rich_text_editor, block_id)
        else:
            if block_id:
                self.viewer.text_display.scroll_to_zone_html(block_id)
        # Handle selection logic
        modifiers = event.modifiers()

        if modifiers & Qt.ControlModifier:
            # Ctrl+Click: Toggle selection without affecting others
            self.setSelected(not self.isSelected())
            event.accept()
            return
        else:
            # Normal click
            if not self.isSelected():
                # Clear other selections and select this item
                if self.scene():
                    self.scene().clearSelection()
                self.setSelected(True)
                event.accept()
                return
            else:
                # Item is already selected, allow dragging
                event.accept()
                return

    def mouseMoveEvent(self, event):
        if self.is_resizing and self.selected_handle:
            self.handle_resize(event)
            return
        event.ignore()  # Don’t move the zone

        # Handle normal dragging for selected items
        if self.isSelected() and self.drag_start_pos:
            # Calculate movement delta
            delta = event.pos() - self.drag_start_pos

            # Move all selected items together
            selected_items = [item for item in self.scene().selectedItems()
                              if isinstance(item, ResizableZone)]

            for item in selected_items:
                new_pos = item.pos() + delta
                item.setPos(new_pos)
                item.update_zone_data()

    def handle_resize(self, event):
        """Handle resizing when dragging handles"""
        pos = event.pos()
        r = self.rect()
        new_rect = QRectF(r)
        min_size = 20

        if self.selected_handle == "left":
            new_left = min(pos.x(), r.right() - min_size)
            new_rect.setLeft(new_left)
        elif self.selected_handle == "right":
            new_right = max(pos.x(), r.left() + min_size)
            new_rect.setRight(new_right)
        elif self.selected_handle == "top":
            new_top = min(pos.y(), r.bottom() - min_size)
            new_rect.setTop(new_top)
        elif self.selected_handle == "bottom":
            new_bottom = max(pos.y(), r.top() + min_size)
            new_rect.setBottom(new_bottom)

        if new_rect != r and new_rect.isValid():
            self.prepareGeometryChange()
            self.setRect(new_rect.normalized())
            self.init_handles()
            self.update()
            self.update_zone_data()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton:
            event.accept()
            return
        # Reset resize state
        self.selected_handle = None
        self.is_resizing = False
        self.drag_start_pos = None
        block_id = None

        if self.isSelected():
            selected_zone = self.viewer.get_selected_zones()
            zones_data = self.viewer.zones_data_by_page.get(self.viewer.current_page, [])
            zone_changed = False  # ✅ Track if any bbox changed

            for zone_item in selected_zone:
                block_id = zone_item.zone_data.get("block_id")
                old_bbox = tuple(zone_item.zone_data.get("bbox") or ())
                if not block_id:
                    continue

                updated_zone = zone_item.update_zone_data()
                new_bbox = (
                    updated_zone.get("x"),
                    updated_zone.get("y"),
                    updated_zone.get("x") + updated_zone.get("width"),
                    updated_zone.get("y") + updated_zone.get("height")
                )
                updated_zone["bbox"] = new_bbox

                # Compare bbox with small tolerance
                if tuple(map(float, new_bbox)) == tuple(map(float, old_bbox)):
                    continue  # skip update

                zone_changed = True
                updated_zone["text"] = zone_item.extract_text_from_zone()

                for item in zones_data:
                    if item.get("block_id") == block_id:
                        item.update({
                            "bbox": new_bbox,
                            "x": updated_zone.get("x"),
                            "y": updated_zone.get("y"),
                            "width": updated_zone.get("width"),
                            "height": updated_zone.get("height"),
                            "text": updated_zone.get("text")
                        })
                        break


            # ✅ Only update view if any zone changed
            if zone_changed:

                if zones_data and self.viewer.current_text_viewer == "html_viewer":
                    self.viewer.text_display.html_text = zones_data
                    scrollbar = self.viewer.text_display.html_editor.verticalScrollBar()
                    current_scroll_value = scrollbar.value()
                    generated_html = self.viewer.text_display.generate_clean_html(zones_data)
                    formatted_html = self.viewer.text_display.format_html(generated_html)
                    self.viewer.text_display.html_editor.setText(formatted_html)
                    scrollbar.setValue(current_scroll_value)
                    self.viewer.text_display.scroll_to_zone_html(block_id)
                else:
                    html_viewer = HtmlSourceViewer(self.viewer)
                    generated_html = html_viewer.generate_clean_html(zones_data)
                    formatted_html = html_viewer.format_html(generated_html)
                    self.viewer.rich_text_editor.set_html(formatted_html)
                    scroll_to_zone_id(self.viewer.rich_text_editor, block_id)

        event.accept()

    def update_zone_data(self):
        """Update the zone data based on current position and size"""
        if not self.viewer or not self.viewer.pdf_doc:
            return

        try:
            # Get current rectangle in scene coordinates
            scene_rect = self.mapRectToScene(self.rect())
            page_num = self.zone_data.get("page", 1)
            page = self.viewer.pdf_doc.load_page(page_num - 1)
            pdf_height = page.rect.height

            # Convert screen coordinates back to PDF coordinates
            x = scene_rect.left() / self.zoom_factor
            width = scene_rect.width() / self.zoom_factor
            height = scene_rect.height() / self.zoom_factor

            # Convert Y coordinate from screen space (top-left origin) back to PDF space (bottom-left origin)
            screen_y = scene_rect.top() / self.zoom_factor
            y = pdf_height - screen_y - height

            updated_zone = {
                "x": x,
                "y": y,
                "width": width,
                "height": height
            }

            if self.on_update:
                self.on_update()
            return updated_zone

        except Exception as e:
            print(f"[Error] Failed to update zone data: {e}")

    def delete_zone(self):
        try:
            scene = self.scene()
            if not scene:
                return

            selected_items = scene.selectedItems()
            zones_to_delete = [item for item in selected_items if isinstance(item, ResizableZone)]

            if not zones_to_delete:
                print("No zones selected for deletion")
                return

            if len(zones_to_delete) > 1:
                reply = QMessageBox.question(
                    None,
                    "Confirm Deletion",
                    f"Are you sure you want to delete {len(zones_to_delete)} zones?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    return

            for zone_item in zones_to_delete:
                block_id_to_remove = zone_item.zone_data.get("block_id")

                # ✅ Remove sequence circle group by block_id
                removed_circle = False
                for item in scene.items():
                    if isinstance(item, QGraphicsItemGroup) and item.data(0) == block_id_to_remove:
                        scene.removeItem(item)
                        removed_circle = True
                        break

                if not removed_circle:
                    print(f"⚠️ No sequence circle found for block_id: {block_id_to_remove}")

                # ✅ Remove the zone item
                if zone_item.scene():
                    scene.removeItem(zone_item)

                # ✅ Remove from viewer data
                current_page_zone = self.viewer.zones_data_by_page.get(self.viewer.current_page, [])
                if zone_item.zone_data in current_page_zone:
                    html_obj = self.pop_value_by_id(current_page_zone, block_id_to_remove)
                    self.viewer.zones_data_by_page[self.viewer.current_page] = html_obj

                    if html_obj and self.viewer.current_text_viewer == "html_viewer":
                        scrollbar = self.viewer.text_display.html_editor.verticalScrollBar()
                        scroll_val = scrollbar.value()
                        html = self.viewer.text_display.generate_clean_html(html_obj)
                        self.viewer.text_display.html_editor.setText(self.viewer.text_display.format_html(html))
                        scrollbar.setValue(scroll_val)
                    else:
                        html_viewer = HtmlSourceViewer(self.viewer)
                        html = html_viewer.generate_clean_html(html_obj)
                        self.viewer.rich_text_editor.set_html(html_viewer.format_html(html))

            self.viewer.save_zones_to_json()

            if self.on_update:
                self.on_update()

            scene.update()
            self.viewer.pdf_utils_obj.addzones_to_scene_fast(self.viewer, None, self.viewer.current_page, None, True)

        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(None, "Delete Error", f"Failed to delete zones: {str(e)}")

    def pop_value_by_id(self, zone_data, target_id):
        # target_id = target_id.replace("p", "")
        for i, item in enumerate(zone_data):
            if item.get('block_id') == target_id:
                zone_data.pop(i)
                break
        return zone_data

    def hoverEnterEvent(self, event):
        """Show tooltip with zone type on hover"""
        if self.zone_data and "type" in self.zone_data:
            zone_type = self.zone_data["type"]
            tooltip_text = zone_type
            QToolTip.showText(event.screenPos(), tooltip_text)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        QToolTip.hideText()
        super().hoverLeaveEvent(event)
