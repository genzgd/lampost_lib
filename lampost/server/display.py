from lampost.di.app import on_app_start
from lampost.di.resource import Injected, module_inject
from lampost.di.config import on_config_change, config_value

ev = Injected('dispatcher')
module_inject(__name__)

client_displays = {}


@on_app_start
def _start():
    ev.register('session_connect', set_displays)
    _set_displays()


@on_config_change
def _set_displays():
    client_displays.clear()
    for display in config_value('default_displays'):
        client_displays[display['name']] = display['value']


def set_displays(session):
    session.append({'client_config': {'default_displays': client_displays}})

