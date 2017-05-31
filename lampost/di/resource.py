import logging
import sys
import itertools

from collections import defaultdict

log = logging.getLogger(__name__)

_registry = {}
_consumer_map = defaultdict(list)


def register(name, service):
    if name in _registry:
        raise KeyError("service {} already registered".format(name))
    _registry[name] = service
    for cls, local_name in _consumer_map.get(name, []):
        _inject(cls, name, service, local_name)
    if name in _consumer_map:
        del _consumer_map[name]
    return service


def inject(cls, name, local_name=None):
    service = _registry.get(name, None)
    if service:
        _inject(cls, name, service, local_name)
        return
    _consumer_map[name].append((cls, local_name))


def module_inject(module_name):
    module = sys.modules[module_name]
    for name, value in module.__dict__.copy().items():
        if hasattr(value, '_lp_injected'):
            inject(module, value._lp_injected, name)
            del _pending_injects[value._id]


def get_resource(name):
    return _registry[name]


def validate_injected():
    for p_inject in _pending_injects.values():
        raise TypeError(
            "Injected {} in {} never triggered.  Did you miss a module_inject?".format(p_inject[0], p_inject[1]))
    for name, consumers in _consumer_map.items():
        for consumer in consumers:
            raise TypeError("{} dependency not found for consumer {}".format(name, getattr(consumer, '__name__', consumer)))


def _inject(cls, name, service, local_name):
    if not local_name:
        local_name = name
    if hasattr(service, 'factory'):
        setattr(cls, local_name, service.factory(cls))
    else:
        setattr(cls, local_name, service)


_pending_injects = {}
_inject_id = itertools.count()


class Injected:
    def __init__(self, name):
        self._lp_injected = name
        self._id = next(_inject_id)
        try:
            module = sys._getframe(1).f_globals['__name__']
        except Exception:
            # Checking frames may not work in some environments?
            module = 'Unknown'
        _pending_injects[self._id] = (name, module)

    def __call__(self, *args, **kwargs):
        log.error("Injected object {} called directly before injection".format(self._lp_injected))

    def __get__(self, instance, owner=None):
        log.error("Injected object {} __get__ method called directly before injection".format(self._lp_injected))
