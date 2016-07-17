import re

from tornado.httpserver import HTTPServer
from tornado.web import Application, URLSpec

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
    application = Application(_handlers, log_function=_app_log)
    log.info("Starting web server on port {}", port)
    http_server = HTTPServer(application)
    http_server.listen(port, interface)


def _app_log(handler):
    if log.debug_enabled():
        log.debug('{} {} {}', handler.get_status(), handler._request_summary(),
              1000.0 * handler.request.request_time())
