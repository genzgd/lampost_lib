from tornado.web import RequestHandler

from lampost.di.config import config_value
from lampost.server.handlers import SessionHandler
from lampost.di.resource import Injected, module_inject
from lampost.util.lputil import ClientError

log = Injected('log')
sm = Injected('session_manager')
um = Injected('user_manager')
db = Injected('datastore')
json_encode = Injected('json_encode')
json_decode = Injected('json_decode')
perm = Injected('perm')
edit_update = Injected('edit_update_service')
module_inject(__name__)


def editor_login(session):
    edit_perms = []
    player = session.player
    for perm_level, tab_ids in config_value('editor_tabs').items():
        if perm.has_perm(player, perm_level):
            edit_perms.extend(tab_ids)
    session.append({'editor_login': {'edit_perms': edit_perms, 'playerId': player.dbo_id, 'imm_level': player.imm_level,
                                     'playerName': player.name}})
    edit_update.register(session)


class EditConnect(RequestHandler):
    def post(self):
        session_id = self.request.headers.get('X-Lampost-Session')
        session = sm.get_session(session_id)
        if not session:
            session_id, session = sm.start_edit_session()
            session.player = None
        if not session.player:
            content = json_decode(self.request.body.decode())
            game_session = sm.get_session(content.get('gameSessionId'))
            if game_session:
                if getattr(game_session, 'user', None) and game_session.user.dbo_id == content.get('userId'):
                    session.player = game_session.player
                else:
                    log.warn("Edit session connected with non-match user id")
        session.append({'connect': session_id})
        if session.player:
            editor_login(session)
        else:
            session.append({'connect_only': True})
        self.set_header("Content-Type", "application/json; charset=UTF-8")
        self.write(json_encode(session.pull_output()))


class EditLogin(SessionHandler):
    def main(self):
        content = self._content()
        user_name = content.userId.lower()
        try:
            user = um.validate_user(user_name, content.password)
        except ClientError:
            self.session.append({'login_failure': "Invalid user name or password."})
            return
        imm = None
        for player in (db.load_object(player_id, "player") for player_id in user.player_ids):
            if player.dbo_id == user_name:
                if player.imm_level:
                    imm = player
                    break
                self.session.append({'login_failure': '{} is not immortal.'.format(player.name)})
                return
            if player.imm_level and (not imm or player.imm_level > imm.imm_level):
                imm = player
        if imm:
            self.session.player = imm
            editor_login(self.session)
        else:
            self.session.append({'login_failure': 'No immortals on this account.'})


class EditLogout(SessionHandler):
    def main(self):
        edit_update.unregister(self.session)
        self.session.player = None
        self.session.append({'editor_logout': True})
