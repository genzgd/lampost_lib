from tornado.web import RequestHandler

from lampost.di.config import config_value
from lampost.server.handlers import SessionHandler
from lampost.di.resource import Injected, module_inject
from lampost.util.lputil import ClientError

log = Injected('log')
sm = Injected('session_manager')
um = Injected('user_manager')
db = Injected('datastore')
perm = Injected('perm')
edit_update = Injected('edit_update_service')
module_inject(__name__)
route_module(__name__, 'editor')


def edit_connect(session, user_id, app_session_id=None, **_):
    if not session:
        session_id, session = sm.start_session()
        session.player = None
    if not session.player:
        app_session = sm.get_session(app_session_id)
        if app_session:
            if getattr(app_session, 'user', None) and app_session.user.dbo_id == user_id:
                session.player = app_session.player
            else:
                log.warn("Edit session connected with non-matching user id")
        session.append({'connect': session_id})
        if session.player:
            _editor_login(session)
        else:
            session.append({'connect_only': True})
        return session.pull_output()


def edit_login(session, user_id, password, **_):
    def main(self):
        user_name = user_id.lower()
        try:
            user = um.validate_user(user_name, password)
        except ClientError:
            self.session.append({'login_failure': "Invalid user name or password."})
            return
        imm = None
        for player in (db.load_object(player_id, "player") for player_id in user.player_ids):
            if player.dbo_id == user_name:
                if player.imm_level:
                    imm = player
                    break
                session.append({'login_failure': '{} is not immortal.'.format(player.name)})
                return
            if player.imm_level and (not imm or player.imm_level > imm.imm_level):
                imm = player
        if imm:
            session.player = imm
            _editor_login(self.session)
        else:
            session.append({'login_failure': 'No immortals on this account.'})


def edit_logout(session, **_):
    edit_update.unregister(session)
    session.player = None
    session.append({'editor_logout': True})


def _editor_login(session):
    edit_perms = []
    player = session.player
    for perm_level, tab_ids in config_value('editor_tabs').items():
        if perm.has_perm(player, perm_level):
            edit_perms.extend(tab_ids)
    session.append({'editor_login': {'edit_perms': edit_perms, 'playerId': player.dbo_id, 'imm_level': player.imm_level,
                                     'playerName': player.name}})
    edit_update.register(session)
