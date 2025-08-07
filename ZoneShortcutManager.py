import configparser
import json
from PyQt5.QtWidgets import QShortcut
from PyQt5.QtGui import QKeySequence
from PyQt5.QtCore import QObject
from configParser import config_parser
from pdf_utils import FlashMessage


class ZoneShortcutManager(QObject):

    def __init__(self, viewer):
        super().__init__()
        self.viewer = viewer
        self.shortcuts = []
        self.pdf_utils = viewer.pdf_utils_obj if hasattr(viewer, 'pdf_utils_obj') else None
        self.register_shortcuts()

    def register_shortcuts(self):
        self._bind("Delete", self.delete_selected_zones)
        self._bind("M", self.merge_selected_zones)
        self._bind("ctrl+s", self.save_text)
        self._bind("S", self.replace_sequence_number)
        self._register_dynamic_shortcuts()

    def replace_sequence_number(self):
        selected_items = self.viewer.get_selected_zones()
        if len(selected_items) < 2:
            return
        if self.pdf_utils:
            self.pdf_utils.replace_sequence_number(self.viewer, selected_items)

    def _bind(self, key, handler):
        shortcut = QShortcut(QKeySequence(key), self.viewer)
        shortcut.activated.connect(handler)
        self.shortcuts.append(shortcut)

    def delete_selected_zones(self):
        selected_items = self.viewer.get_selected_zones()
        for item in selected_items:
            if hasattr(item, 'delete_zone'):
                item.delete_zone()
        #self.viewer.pdf_utils_obj.remove_zones(self.viewer.current_page)
        #self.viewer.pdf_utils_obj.addzones_to_scene_fast(self.viewer, None, self.viewer.current_page, None,True)




    def save_text(self):
        results = []
        if self.viewer.current_text_viewer == "text_viewer":
            text_viewer = self.viewer.rich_text_editor
            text_viewer.handle_text_change()
        if self.viewer.current_text_viewer == "html_viewer":
            self.viewer.text_display.detect_and_update_zone_changes()

        flash = FlashMessage("Zone saved successfully!", "success")
        flash.show_message()



    def merge_selected_zones(self):
        selected_items = self.viewer.get_selected_zones()
        if len(selected_items) < 2:
            print("Select at least two zones to merge.")
            return
        if self.pdf_utils:
            self.pdf_utils.mergezones(self.viewer, selected_items)

    def change_type(self, new_type):
        selected_items = self.viewer.get_selected_zones()
        for item in selected_items:
            if hasattr(item, 'change_zone_type'):
                item.change_zone_type(new_type)

    def _register_dynamic_shortcuts(self):
        """Register shortcuts dynamically from INI file"""
        try:
            zone_json_str = config_parser.zones_type
            zone_mappings = json.loads(zone_json_str)
            for mapping in zone_mappings:
                zone_type = mapping.get("type")
                shortcut_key = mapping.get("shortcut_key")
                self._register_zone_shortcut(shortcut_key, zone_type)

        except (configparser.NoSectionError, configparser.NoOptionError, json.JSONDecodeError) as e:
            print(f"Error loading shortcuts from INI: {e}")

    def _register_zone_shortcut(self, key, zone_type):
        """Register a single zone type shortcut"""
        # Create a lambda that captures the zone_type value
        callback = lambda zt=zone_type: self.change_type(zt)
        self._bind(key, callback)

