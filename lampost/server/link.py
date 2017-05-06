from tornado.websocket import WebSocketHandler

from lampost.di.resource import Injected, module_inject
from lampost.util.lputil import ClientError

log = Injected('log')
perm = Injected('perm')
ev = Injected('dispatcher')
json_decode = Injected('json_decode')
json_encode = Injected('json_encode')
module_inject(__name__)


class LinkHandler(WebSocketHandler):
    def __init__(self, application, request, **kwargs):
        super().__init__(application, request, **kwargs)
        self.session = None
        self._req_map = {}

    def on_open(self):
        pass

    def on_message(self, message):
        command = json_decode(message)
        req_id = command.get('req_id', None)
        try:
            ev.dispatch(command['id'], socket=self, **command)
        except Exception as e:
            error_response = {'req_id': req_id}
            if isinstance(e, ClientError):
                error_response['status'] = e.http_status
                error_response['client_message'] = e.client_message
            else:
                error_response['status'] = 500
                log.exception('Link Handler Exception', e)
            if req_id:
                self.write_message(json_encode(error_response))

    def on_close(self):
        if self.session:
            self.session.link_failed("Client Connection Close")

    def data_received(self, chunk):
        log.info("Unexpected stream receive")


class LinkListener:
    def __init__(self, command_id, handler, perm_level=None):
        self.handler = handler
        self.perm_level = perm_level
        ev.register(command_id, self._handle)

    def _handle(self, socket, req_id=None, **command):
        session = socket.session
        player = session and session.player
        perm.check_perm(player, self.perm_level)
        response = self.handler(socket, session, player, **command)
        if response:
            try:
                response['req_id'] = req_id
            except TypeError:
                response = {'req_id': req_id, 'response': response}
            socket.write_message(json_encode(response))
