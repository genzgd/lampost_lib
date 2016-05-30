from lampost.di.resource import Injected, module_inject
from lampost.di.config import m_configured

ev = Injected('dispatcher')
module_inject(__name__)

client_displays = {}


def _on_configured():
    client_displays.clear()
    for display in default_displays:
        client_displays[display['name']] = display['value']

m_configured(__name__, 'default_displays')


def _post_init():
    ev.register('session_connect', set_displays)


def set_displays(session):
    session.append({'client_config': {'default_displays': client_displays}})

