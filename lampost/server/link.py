import sys
import inspect

from collections import namedtuple
from datetime import datetime

from tornado.websocket import WebSocketHandler

from lampost.di.resource import Injected, module_inject
from lampost.util.lputil import ClientError

log = Injected('log')
perm = Injected('perm')
ev = Injected('dispatcher')
json_decode = Injected('json_decode')
json_encode = Injected('json_encode')
module_inject(__name__)

_routes = {}

LinkRoute = namedtuple('LinkRoute', 'handler imm_level')


def add_link_route(path, handler, imm_level=None):
    if path in _routes:
        log.warn("Overwriting route for path {}", path)
    _routes[path] = LinkRoute(handler, imm_level)
    log.info("Added route {}", path)


def add_link_object(path, route_obj, imm_level=None):
    if imm_level is None:
        imm_level = getattr(route_obj, 'imm_level', None)
    for name, method in inspect.getmembers(route_obj.__class__):
        if not name.startswith('_') and hasattr(method, '__call__'):
            route_path = '{}/{}'.format(path, name)
            add_link_route(route_path, getattr(route_obj, name), imm_level)


def add_link_module(module, root_path=None, imm_level=None):
    root_path = root_path or module.__name__.split('.')[-1]
    for name, handler in module.__dict__.items():
        if not name.startswith('_') and hasattr(handler, '__call__') \
                and getattr(handler, '__module__') == module.__name__:
            add_link_route('{}/{}'.format(root_path, name), handler, imm_level)


def link_route(path, imm_level=None):
    def wrapper(handler):
        add_link_route(path, handler, imm_level)
    return wrapper


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
                raise NoRouteError(path)
            session = self.session
            if session:
                session.activity_time = datetime.now()
            player = session and session.player
            perm.check_perm(player, route.imm_level)
            cmd['session'] = session
            cmd['player'] = player
            cmd['socket'] = self
            data = route.handler(**cmd)
            if req_id is None:
                if data is not None:
                    self.write_message(json_encode(data))
            else:
                response = {'req_id': req_id}
                if data is not None:
                    response['data'] = data
                self.write_message(json_encode(response))

        except Exception as e:
            error_response = {'req_id': req_id}
            if isinstance(e, ClientError):
                error_response['http_status'] = e.http_status
                error_response['client_message'] = e.client_message
            else:
                error_response['http_status'] = 500
                log.exception('Link Handler Exception', e)
            if req_id is not None:
                self.write_message(json_encode(error_response))

    def on_close(self):
        if self.session:
            self.session.link_failed("Client Connection Close")

    def data_received(self, chunk):
        log.info("Unexpected stream receive")


class NoRouteError(ClientError):
    http_status = 404

    def __init__(self, path):
        super().__init__("No route for {}".format(path))
