import logging
import sys
import inspect
from collections import defaultdict

log = logging.getLogger(__name__)

_registry = {}
_consumer_map = defaultdict(list)
_methods = {}
_registered_modules = []


def register(name, service, export_methods=False):
    if name in _registry:
        raise KeyError("service {} already registered".format(name))
    _registry[name] = service
    if service not in _registered_modules:
        _registered_modules.append(service)
    if export_methods:
        _methods[name] = {}
        if inspect.ismodule(service):
            for attr, value in service.__dict__.items():
                if not attr.startswith('_') and not _registry.get(attr) and hasattr(value, '__call__'):
                    _methods[name][attr] = value
        else:
            for attr, value in service.__class__.__dict__.items():
                if not attr.startswith('_') and not _registry.get(attr) and hasattr(value, '__call__'):
                    _methods[name][attr] = value.__get__(service, service.__class__)
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


def requires(*resources):
    def wrapper(cls):
        for name in resources:
            inject(cls, name)
        return cls
    return wrapper


def m_requires(module_name, *resources):
    module = sys.modules[module_name]
    for name in resources:
        inject(module, name)
    if module not in _registered_modules:
        _registered_modules.append(module)


def module_inject(module_name, priority=1000):
    module = sys.modules[module_name]
    for name, value in module.__dict__.copy().items():
        if hasattr(value, '_lp_injected'):
            inject(module, value._lp_injected, name)
            _pending_injects.discard(value)
    if module not in _registered_modules:
        module._init_priority = getattr(module, '_init_priority', priority)
        _registered_modules.append(module)


def get_resource(name):
    return _registry[name]


def context_post_init():
    for p_inject in _pending_injects:
        raise TypeError("Inject {} never triggered.  Did you miss a module_inject?".format(p_inject._lp_injected))
    for name, consumers in _consumer_map.items():
        for consumer in consumers:
            raise TypeError("{} dependency not found for consumer {}", name, getattr(consumer, '__name__', consumer))
    for module in sorted(_registered_modules, key=_priority_sort):
        if hasattr(module, '_post_init'):
            module._post_init()


def _priority_sort(module):
    try:
        return getattr(module, '_init_priority')
    except AttributeError:
        if inspect.isclass(module):
            return 1000
        return 2000


def _inject(cls, name, service, local_name):
    if not local_name:
        local_name = name
    if hasattr(service, 'factory'):
        setattr(cls, local_name, service.factory(cls))
    else:
        setattr(cls, local_name, service)
    for attr, value in _methods.get(name, {}).items():
        if not getattr(cls, attr, None):
            setattr(cls, attr, value)


_pending_injects = set()


class Injected:
    def __init__(self, name):
        self._lp_injected = name
        _pending_injects.add(self)

    def __call__(self, *args, **kwargs):
        log.error("Injected object {} called directly before injection".format(self._lp_injected))
