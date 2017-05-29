from tornado.httpserver import HTTPServer
from tornado.web import Application, URLSpec, StaticFileHandler

from lampost.di.resource import Injected, module_inject

log = Injected('log')
module_inject(__name__)

service_root = '/'

_handlers = []


def add_route(url_regex, handler, **kwargs):
    add_raw_route(service_root + url_regex, handler, **kwargs)


def add_raw_route(url_regex, handler, **kwargs):
    _handlers.append(URLSpec(url_regex, handler, kwargs))


def add_routes(routes):
    for route in routes:
        try:
            add_route(route.url_regex, route.handler, **route.init_args)
        except AttributeError:
            add_route(*route)


def start_service(port, interface):
    application = Application(_handlers, websocket_ping_interval=30)
    log.info("Starting web server on port {}", port)
    http_server = HTTPServer(application)
    http_server.listen(port, interface)


class NoCacheStaticHandler(StaticFileHandler):
    def set_extra_headers(self, path):
        self.set_header('Cache-control', 'private, no-cache, no-store, must-revalidate')
        self.set_header('Expires', '-1')
        self.set_header('Pragma', 'no-cache')

    def data_received(self, chunk):
        pass
