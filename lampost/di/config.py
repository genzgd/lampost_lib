import glob
import sys
import logging
from weakref import WeakSet

import yaml

from collections import defaultdict

log = logging.getLogger(__name__)

_consumer_map = defaultdict(set)
_value_map = {}
_section_value_map = {}
_config_funcs = set()


def on_configured(func):
    _config_funcs.add(func)
    return func


def m_configured(module_name, *config_properties):
    _register(sys.modules[module_name], *config_properties)


def configured(*config_properties):
    def wrapper(cls):
        original_init = cls.__init__

        def init_and_register(self, *args, **kwargs):
            _register(self, *config_properties)
            original_init(self, *args, **kwargs)

        cls.__init__ = init_and_register
        return cls

    return wrapper


def _register(cls, *config_properties):
    _consumer_map[cls].update(config_properties)
    if _value_map:
        inject_config(cls, config_properties)


def config_value(property_name, default=None):
    if ':' in property_name:
        try:
            return _section_value_map[property_name]
        except KeyError:
            pass
    try:
        return _value_map[property_name]
    except KeyError:
        pass
    if default is not None:
        return default
    l
    


def inject_config(consumer, properties):
    for prop in properties:
        try:
            if ':' in prop:
                property_name, value = prop.split(':')[1], _section_value_map[prop]
            else:
                property_name, value = prop, _value_map[prop]
        except KeyError:
            log.error("No value found for configuration value {} in consumer {}", prop, consumer.__name__)
            continue
        try:
            old_value = getattr(consumer, property_name)
            if old_value == value:
                return
            log.info("Updating config {} from {} to {} in {}.", property_name, old_value, value, consumer.__name__)
        except AttributeError:
            log.info("Setting config {}: {} in {}.", property_name, value, consumer.__name__)
        setattr(consumer, property_name, value)
    if hasattr(consumer, '_on_configured'):
        consumer._on_configured()


def update_all():
    for consumer, properties in _consumer_map.items():
        inject_config(consumer, properties)
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
    update_all()
    return _value_map


_config_values = WeakSet()


class ConfigVal:
    def on_update(self, *_):
        pass

    def __init__(self, config_key, default=None, on_update=None):
        _config_values.add(self)
        if on_update is not None:
            self.on_update = on_update
        self.config_key = config_key
        self.old_value = default
        self.value = default
        self.update()

    def update(self):
        try:
            self.value = config_value(self.config_key)
            if self.old_value != self.value:
                self.on_update(self.value, self.old_value)
                self.old_value = self.value
        except KeyError:
            pass

    def __eq__(self, other):
        if isinstance(other, ConfigVal):
            return id(self) == id(other)
        return self.value == other

    def __hash__(self):
        return id(self)

    def __str__(self):
        return str(self)

    def __cmp__(self, other):
        return self.value.__cmp__(other)

    def __float__(self):
        return self.value.__float__()

    def __int__(self):
        return self.value.__int__()

    def __add__(self, other):
        result = self.value.__add__(other)
        if result == NotImplemented and hasattr(self.value, "__float__"):
            return self.value.__float__().__add__(other)
        return result

    def __radd__(self, other):
        return other + self.value

    def __coerce__(self, other):
        return self.value.__coerce__(other)

    def __sub__(self, other):
        result = self.value.__sub__(other)
        if result == NotImplemented and hasattr(self.value, "__float__"):
            return self.value.__float__().__sub__(other)
        return result

    def __rsub__(self, other):
        return other - self.value

    def __mul__(self, other):
        result = self.value.__mul__(other)
        if result == NotImplemented and hasattr(self.value, "__float__"):
            return self.value.__float__().__mul__(other)
        return result

    def __rmul__(self, other):
        return other * self.value

    def __truediv__(self, other):
        try:
            return self.value / other
        except NotImplementedError:
            return float(self.value) / other

    def __floordiv__(self, other):
        try:
            return self.value // other
        except NotImplementedError:
            return float(self.value) // other


