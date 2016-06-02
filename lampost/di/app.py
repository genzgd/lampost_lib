from lampost.di import resource
from lampost.di import config
from lampost.util.funcs import optional_arg_decorator

_bootstrap_funcs = set()

app_started = False


@optional_arg_decorator
def on_app_start(func, priority=1000):
    _bootstrap_funcs.add((func, priority))
    return func


def start_app():
    global app_started
    if app_started:
        raise RuntimeError("start_app called after app started")
    if not config.activated:
        raise RuntimeError("start_app called before configuration activated")
    resource.validate_injected()
    exec_bootstraps()
    app_started = True


def exec_bootstraps():
    for func, _ in sorted(_bootstrap_funcs, key=lambda f: f[1]):
        func()