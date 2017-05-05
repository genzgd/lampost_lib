from lampost.di.resource import Injected, module_inject

from tornado.websocket import WebSocketHandler

log = Injected('log')
json_decode = Injected('json_decode')
json_encode = Injected('json_encode')
module_inject(__name__)

ev = Injected('dispatcher')


class LinkHandler(WebSocketHandler):
    def __init__(self, application, request, **kwargs):
        super().__init__(application, request, **kwargs)
        self.session = None
        self._req_map = {}

    def on_open(self):
        pass

    def on_message(self, message):
        command = json_decode(message)
        if 'req_id' in command:
            def resp(**response):
                response.req_id = command['req_id']
                self.write_message(json_encode(response))

            command['resp'] = resp
        ev.dispatch(command['id'], socket=self, session=self.session, player=self.session and self.session.player,
                    **command)

    def on_close(self):
        if self.session:
            self.session.link_failed("Client Connection Close")
