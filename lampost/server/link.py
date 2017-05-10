import sys

from collections import namedtuple

from tornado.websocket import WebSocketHandler

from lampost.di.app import on_app_start
from lampost.di.resource import Injected, module_inject
from lampost.util.lputil import ClientError

log = Injected('log')
perm = Injected('perm')
ev = Injected('dispatcher')
json_decode = Injected('json_decode')
json_encode = Injected('json_encode')
module_inject(__name__)

_routes = {}
_route_modules = []


@on_app_start
def _add_routes():
    for module_name, root_path in _route_modules:
        module = sys.modules[module_name]
        root_path = root_path or module_name.split('.')[-1]
        for name, prop in module.__dict__.items():
            if not name.startswith('_') and hasattr(prop, '__call__') and getattr(prop, '__module__') == module_name:
                route_path = '{}/{}'.format(root_path, name)
                _routes[route_path] = LinkRoute(prop, None)


def link_route(path, perm_level=None):
    def wrapper(handler):
        if path in _routes:
            log.warn("Overwriting route for path {}", path)
        _routes[path] = LinkRoute(handler, perm_level)

    return wrapper


def link_module(name, path=None):
    _route_modules.append((name, path))


class LinkHandler(WebSocketHandler):
    def __init__(self, application, request, **kwargs):
        super().__init__(application, request, **kwargs)
        self.session = None
        self._req_map = {}

    def on_open(self):
        pass

    def on_message(self, message):
        cmd = json_decode(message)
        req_id = cmd.get('req_id', None)
        path = cmd.get('path', None)
        try:
            route = _routes.get(path)
            if not route:
                raise ClientError(client_message="No route for {}".format(path), http_status=404)
            session = self.session
            player = session and session.player
            perm.check_perm(player, route.perm_level)
            cmd['session'] = session
            cmd['player'] = player
            cmd['socket'] = self
            data = route.handler(**cmd)
            if data is not None or req_id is not None:
                response = {'req_id': req_id}
                if data is None:
                    response['http_status'] = 204
                else:
                    response['http_status'] = 200
                    response['data'] = data
                self.write_message(json_encode(response))
        except Exception as e:
            error_response = {'req_id': req_id}
            if isinstance(e, ClientError):
                error_response['http_status'] = e.http_status
                error_response['client_message'] = e.client_message
            else:
                error_response['status'] = 500
                log.exception('Link Handler Exception', e)
            if req_id is not None:
                self.write_message(json_encode(error_response))

    def on_close(self):
        if self.session:
            self.session.link_failed("Client Connection Close")

    def data_received(self, chunk):
        log.info("Unexpected stream receive")


LinkRoute = namedtuple('LinkRoute', 'handler perm_level')
