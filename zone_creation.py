# zone_type_mixin.py
import json
import logging

from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QColor, QPen, QBrush
import traceback

from PyQt5.QtWidgets import QGraphicsView, QMessageBox, QToolTip

from configParser import config_parser

class ZoneCreationGraphicsView(QGraphicsView):
    """Enhanced graphics view that supports zone creation by dragging"""

    def __init__(self, scene, viewer, page_number):
        super().__init__(scene)
        self.viewer = viewer
        self.creating_zone = False
        self.zone_start_pos = None
        self.zone_end_pos = None
        self.temp_zone_rect = None
        self.current_page_number = page_number  # pass page number during creation
        self.viewer = viewer
        self.viewer = viewer
        self.current_page_number = page_number
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.NoFrame)  # Op

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.viewer.creation_mode:
            # Check if the click was specifically on an existing zone rectangle
            item = self.itemAt(event.pos())
            is_zone_rect = False

            if item is not None:
                # Check if this item is a zone rectangle (has zone_data attribute or similar)
                # You may need to adjust this check based on your zone rectangle class
                if hasattr(item, 'zone_data') or hasattr(item, 'change_zone_type'):
                    is_zone_rect = True

            if is_zone_rect:
                # Click was on an existing zone rectangle, handle normally (highlight/resize)
                super().mousePressEvent(event)
                return

            # Click was on empty space or text (not a zone rectangle), start creating a new zone
            print("Starting zone creation")
            self.creating_zone = True
            self.zone_start_pos = self.mapToScene(event.pos())
            self.zone_end_pos = self.zone_start_pos
            event.accept()
        else:
            # Normal behavior for zone interaction
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.creating_zone and self.zone_start_pos:
            # Update the temporary zone rectangle
            self.zone_end_pos = self.mapToScene(event.pos())

            # Remove previous temporary rectangle
            if self.temp_zone_rect:
                self.scene().removeItem(self.temp_zone_rect)

            # Create new temporary rectangle
            rect = QRectF(self.zone_start_pos, self.zone_end_pos).normalized()
            if rect.width() > 5 and rect.height() > 5:  # Only show if minimum size
                self.temp_zone_rect = self.scene().addRect(
                    rect,
                    QPen(QColor(255, 0, 0, 128), 2),  # Red dashed border
                    QBrush(QColor(255, 0, 0, 30))  # Semi-transparent red fill
                )

            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.creating_zone and event.button() == Qt.LeftButton:
            # Finish creating the zone
            if self.zone_start_pos and self.zone_end_pos:
                rect = QRectF(self.zone_start_pos, self.zone_end_pos).normalized()

                # Remove temporary rectangle
                if self.temp_zone_rect:
                    self.scene().removeItem(self.temp_zone_rect)
                    self.temp_zone_rect = None

                # Only create zone if it's large enough
                if rect.width() > 10 and rect.height() > 10:
                    # self.viewer.create_zone(rect)
                    self.viewer.create_zone(rect, self.scene(), self.current_page_number)
            # Reset creation state
            self.creating_zone = False
            self.zone_start_pos = None
            self.zone_end_pos = None
            # self.viewer.toggle_creation_mode()  # Exit creation mode after creating one zone
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class ZoneType:
    def change_zone_type(self, new_type):
        try:
            logging.info(f"Changing zone type to: {new_type}")
            confi_object = config_parser
            zone_string = confi_object.zones_type
            zone_list = json.loads(zone_string)
            color = next((item["color"] for item in zone_list if item["type"] == new_type), None)
            if color:
                qcolor = QColor(color)
                self.setPen(QPen(qcolor, 2))
                self.zone_data["zone_color"] = color
                print("✅ Assigned color for", new_type, "→", color)
            else:
                fallback = QColor("gray")
                self.setPen(QPen(fallback, 2))
                self.zone_data["zone_color"] = fallback.name()

            # Update local zone_data
            # self.zone_data["type"] = new_type
            # self.setPen(QPen(color, 2))
            updated_id = self.zone_data.get("block_id")


            if self.viewer and hasattr(self.viewer, "zones_data"):
                for obj in self.viewer.zones_data:
                    if obj.get("block_id") == updated_id:
                        if new_type.endswith(".parent"):
                            obj["parent_zone"] = new_type
                        else:
                            obj["type"] = new_type
                            obj["zone_color"] = color
                        break


            if hasattr(self, "label_item"):
                self.label_item.setText(new_type)
            self.viewer.save_zones_to_json()
        except Exception as e:
            logging.error(f"❌ Error changing zone type: {e}")
            traceback.print_exc()


