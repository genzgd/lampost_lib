import html

from tornado.web import RequestHandler

from lampost.util.lputil import ClientError, Blank

log = Injected('log')
perm = Injected('perm')

json_encode = Injected('json_encode')


class LinkError(Exception):
    def __init__(self, error_code):
        self.error_code = error_code


class SessionHandler(RequestHandler):
    def _handle_request_exception(self, e):
        if isinstance(e, LinkError):
            self._return({'link_status': e.error_code})
            return
        if isinstance(e, ClientError):
            self.set_status(e.http_status)
            self.write(e.client_message)
        else:
            self.set_status(500)
            log.exception("Handler Exception", e)
        self.finish()

    def _content(self):
        return Blank(**self.raw)

    def _return(self, result):
        if result is None:
            self.set_status(204)
        else:
            self.set_header('Content-Type', 'application/json')
            self.write(json_encode(result))
        self.finish()

    def data_received(self, chunk):
        log.info("Unexpected stream receive")

    def prepare(self):
        self.session = sm.get_session(self.request.headers.get('X-Lampost-Session'))
        if not self.session:
            raise LinkError('session_not_found')
        self.player = self.session.player

    def post(self, *args):
        self.raw = json_decode(self.request.body.decode())
        self.main(*args)
        if not self._finished:
            self._return(self.session.pull_output())

    def main(self, *_):
        pass


class MethodHandler(SessionHandler):
    def main(self, path, *args):
        if path.startswith('_') or hasattr(SessionHandler, path):
            self.send_error(404)
            return
        method = getattr(self, path, None)
        if method:
            self._return(method(*args))
        else:
            self.send_error(404)


class Action(SessionHandler):
    def main(self):
        player = self.session.player
        if not player:
            raise LinkError("no_login")
        player.parse(html.escape(self.raw['action'].strip(), False))


