import os
import sys
from configparser import ConfigParser

thisfolder = os.path.dirname(os.path.abspath(sys.argv[0]))
initfile = os.path.join(thisfolder, 'config.ini')
config = ConfigParser()
config.read(initfile)

class ConfigManager:
    def __init__(self, app_name="MyApp"):
        self.zones_type = config['ZONE_TYPE']['zone_json']
        self.tag_mapping = config['ZONE_TYPE']['tag_mapping']

config_parser  = ConfigManager()