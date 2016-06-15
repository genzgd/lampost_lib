import inspect
import itertools
import logging

from lampost.util.classes import cls_name, subclasses

log = logging.getLogger(__name__)

_dbo_registry = {}
_mixed_registry = {}
_instance_registry = {}


def set_dbo_class(class_id, dbo_class):
    old_class = _dbo_registry.get(class_id)
    if old_class:
        log.info("Overriding {} with {} as {}", cls_name(old_class), cls_name(dbo_class), class_id)
    else:
        log.info("Registering {} as {}", cls_name(dbo_class), class_id)
    _dbo_registry[class_id] = dbo_class


def set_instance_class(template_id, instance_class):
    _instance_registry[template_id] = instance_class


def get_dbo_class(class_id):
    try:
        return _dbo_registry[class_id]
    except KeyError:
        log.exception("No class found in registry for dbo class id: {}", class_id)


def get_mixed_type(class_id, mixins):
    main_class = get_dbo_class(class_id)
    if not mixins:
        return main_class
    mixin_key = frozenset(itertools.chain(mixins, (class_id,)))
    try:
        return _mixed_registry[mixin_key]
    except KeyError:
        mixin_bases = (main_class,) + tuple(_dbo_registry[mixin] for mixin in mixins)
        mixin_class = type("_".join(mixin_key), mixin_bases, {'mixins': mixins})
        _mixed_registry[mixin_key] = mixin_class
        return mixin_class


def dbo_types(cls):
    return {subclass for subclass in subclasses(cls) if hasattr(subclass, 'dbo_key_type')}


def implementors(base_class):
    return [(key, value) for key, value in _dbo_registry.items() if base_class != value and base_class in inspect.getmro(value)]


def instance_implementors(base_class):
    return [(key, value) for key, value in _instance_registry.items() if base_class != value and base_class in inspect.getmro(value)]