from lampost.di.app import on_app_start
from lampost.di.resource import Injected, module_inject
from lampost.di.config import config_section

ev = Injected('dispatcher')
module_inject(__name__)


@on_app_start
def _start():
    ev.register('session_connect', _add_client_config)


def _add_client_config(session):
    session.append({'client_config': config_section('client')})
