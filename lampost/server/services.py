from lampost.di.app import on_app_start
from lampost.di.resource import Injected, module_inject, get_resource
from lampost.server.link import add_link_route

log = Injected('log')
sm = Injected('session_manager')
ev = Injected('dispatcher')
perm = Injected('perm')
module_inject(__name__)


def register_service(session, service_id, data=None, **_):
    client_service = get_resource(service_id)
    if client_service:
        client_service.register(session, data)
    else:
        log.warn("Attempting registration for missing service {}", service_id)


def unregister_service(session, service_id, **_):
    get_resource(service_id).unregister(session)


class ClientService():
    def __init__(self):
        self.sessions = set()
        on_app_start(self._start)

    def _start(self):
        ev.register('session_disconnect', self.unregister)

    def register(self, session, data=None):
        self.sessions.add(session)

    def unregister(self, session):
        try:
            self.sessions.remove(session)
        except KeyError:
            pass

    def _session_dispatch(self, event):
        for session in self.sessions:
            session.append(event)


class PlayerListService(ClientService):

    def _start(self):
        super()._start()
        ev.register('player_list', self._process_list)

    def register(self, session, data=None):
        super().register(session, data)
        session.append({'player_list': sm.player_info_map()})

    def _process_list(self, player_list):
        self._session_dispatch({'player_list': player_list})


class AnyLoginService(ClientService):

    def _start(self):
        super()._start()
        ev.register('player_attach', self._process_login)

    def _process_login(self, player):
        self._session_dispatch({'any_login': {'name': player.name}})


class EditUpdateService(ClientService):

    def _start(self):
        super()._start()
        ev.register('publish_edit', self.publish_edit)

    def publish_edit(self, edit_type, edit_obj, source_session=None, local=False):
        edit_dto = edit_obj.edit_dto
        if source_session:
            local_dto = edit_dto.copy()
            local_dto['can_write'] = perm.has_perm(source_session.player, edit_obj)
        else:
            local_dto = None
        edit_update  = {'edit_update': {'edit_type': edit_type}}

        for session in self.sessions:
            if session == source_session:
                if local:
                    event = edit_update.copy()
                    local_dto['local'] = True
                    event['edit_update']['model'] = local_dto
                    session.append(event)
            else:
                event = edit_update.copy()
                event_dto = edit_dto.copy()
                event_dto['can_write'] = perm.has_perm(session.player, edit_obj)
                event['edit_update']['model'] = event_dto
                session.append(event)

        return local_dto
