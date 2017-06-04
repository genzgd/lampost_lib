import os

from tornado.httpserver import HTTPServer
from tornado.web import Application, URLSpec, RequestHandler, HTTPError

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


class IndexHandler(RequestHandler):
    def initialize(self, index_file):
        self.index_file = index_file

    def set_extra_headers(self, path):
        self.set_header('Cache-control', 'private, no-cache, no-store, must-revalidate')
        self.set_header('Expires', '-1')
        self.set_header('Pragma', 'no-cache')

    def get(self):
        if not os.path.exists(self.index_file):
            raise HTTPError(404)
        with open(self.index_file, "rb") as file:
            remaining = None
            while True:
                chunk_size = 64 * 1024
                if remaining is not None and remaining < chunk_size:
                    chunk_size = remaining
                chunk = file.read(chunk_size)
                if chunk:
                    self.write(chunk)
                else:
                    return

    def data_received(self, chunk):
        pass

