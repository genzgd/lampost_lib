import glob
import logging
from weakref import WeakSet

import yaml


log = logging.getLogger(__name__)

_value_map = {}
_section_value_map = {}
_config_funcs = set()
_config_values = WeakSet()


def on_configured(func):
    _config_funcs.add(func)
    return func


def config_value(key, default=None):
    if ':' in key:
        try:
            return _section_value_map[key]
        except KeyError:
            pass
    try:
        return _value_map[key]
    except KeyError:
        pass
    if default is None:
        log.error("No value found for config key {}", key)
    return default


def _find_value(key):
    if ':' in key:
        try:
            return _section_value_map[key]
        except KeyError:
            pass
    try:
        return _value_map[key]
    except KeyError:
        pass


def update_all():
    for config_value in _config_values:
        config_value.update()
    for config_func in _config_funcs:
        config_func()


def load_yaml(path):
    all_config = []

    for file_name in glob.glob("{}/*yaml".format(path)):
        with open(file_name, 'r') as yf:
            log.info("Processing config file {}", file_name)
            try:
                yaml_load = yaml.load(yf)
                all_config.append(yaml_load)
            except yaml.YAMLError:
                log.exception("Error parsing {}", yf)

    return all_config


def activate(all_values):
    _section_value_map.clear()
    _value_map.clear()
    for section_key, value in all_values.items():
        _section_value_map[section_key] = value
        value_key = section_key.split(':')[1]
        if value_key in _value_map:
            log.warn("Duplicate value for {} found in section {}", value_key, section_key.split(':')[0])
        else:
            _value_map[value_key] = value
    return _value_map


class ConfigVal:
    def __init__(self, config_key, default=None, on_update=lambda *x: None):
        _config_values.add(self)
        self.on_update = on_update
        self.config_key = config_key
        self.old_value = default
        self.value = default
        self.update()

    def update(self):
        try:
            self.value = _find_value(self.config_key)
            if self.old_value != self.value:
                self.on_update(self.value, self.old_value)
                self.old_value = self.value
        except KeyError:
            pass