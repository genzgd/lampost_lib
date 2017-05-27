import glob
import logging
from collections import defaultdict

import yaml

from weakref import WeakSet

from lampost.util.funcs import optional_arg_decorator

log = logging.getLogger(__name__)

_section_map = defaultdict(dict)
_value_map = {}
_section_value_map = {}
_change_funcs = set()
_config_values = WeakSet()

activated = False


@optional_arg_decorator
def on_config_change(func, priority=1000):
    _change_funcs.add((func, priority))
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


def config_section(section_key):
    return _section_map.get(section_key, {})


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


def update_values():
    for config_value in _config_values:
        config_value.update()


def refresh_config():
    for func, priority in sorted(_change_funcs, key= lambda f: f[1]):
        func()


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
    global activated
    _section_value_map.clear()
    _value_map.clear()
    _section_map.clear()
    for full_key, value in all_values.items():
        _section_value_map[full_key] = value
        section_key, value_key = tuple(full_key.split(':'))
        _section_map[section_key][value_key] = value
        if value_key in _value_map:
            log.warn("Duplicate value for {} found in section {}", value_key, section_key)
        else:
            _value_map[value_key] = value
    update_values()
    activated = True
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
