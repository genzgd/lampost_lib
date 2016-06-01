from lampost.di.resource import Injected, module_inject
from lampost.di.config import on_configured, config_value

ev = Injected('dispatcher')
module_inject(__name__)

client_displays = {}


@on_configured
def _on_configured():
    client_displays.clear()
    for display in config_value('default_displays'):
        client_displays[display['name']] = display['value']


def _post_init():
    ev.register('session_connect', set_displays)


def set_displays(session):
    session.append({'client_config': {'default_displays': client_displays}})

