import inspect

from lampost.di.resource import Injected, module_inject

perm = Injected('perm')
module_inject(__name__)

admin_ops = {}


def admin_op(func):
    a_spec = inspect.getargspec(func)
    if a_spec.defaults:
        params = [''] * (len(a_spec.args) - len(a_spec.defaults)) + list(a_spec.defaults)
    else:
        params = [''] * len(a_spec.args)
    admin_ops[func.__name__] = {'func': func, 'dto': {'name': func.__name__, 'args': a_spec.args, 'params': params}}
    return func


def admin_operation(name, params=None, **_):
    if params is None:
        params = []
    if name == 'list':
        return [op['dto'] for op in admin_ops.values()]
    op = admin_ops[name]
    return op['func'](*params)
