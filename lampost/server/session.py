import time
from datetime import datetime, timedelta
from os import urandom
from base64 import b64encode

from lampost.di.app import on_app_start
from lampost.di.resource import Injected, module_inject
from lampost.di.config import on_config_change, config_value
from lampost.event.zone import Attachable
from lampost.server.link import link_route
from lampost.util.lputil import ClientError

log = Injected('log')
ev = Injected('dispatcher')
um = Injected('user_manager')
json_encode = Injected('json_encode')
module_inject(__name__)

_session_map = {}
_player_info_map = {}
_player_session_map = {}
_link_status_reg = None
_broadcast_reg = None
_link_dead_prune = 0
_link_dead_interval = 0


@on_app_start
def _on_app_start():
    ev.register('player_logout', _player_logout)
    _config()


@on_config_change
def _on_config_change(self):
    ev.unregister(self._link_status_reg)
    ev.unregister(self._broadcast_reg)
    _config()


@link_route('app_connect')
def _app_connect(socket, session_id=None, player_id=None, **_):
    if session_id:
        session = _reconnect_session(session_id, player_id)
    else:
        session = _start_app_session()
    session.attach_socket(socket)
    session.flush()


@link_route('player_login')
def _player_login(session, user_name=None, password=None, **_):
    if not user_name or not password:
        session.append({'login_failure': 'Browser did not submit credentials, please retype'})
        return
    user_name = user_name.lower()
    try:
        user = um.validate_user(user_name, password)
    except ClientError as ce:
        session.append({'login_failure': ce.client_message})
        return
    session.connect_user(user)
    if len(user.player_ids) == 1:
        _start_player(session, user.player_ids[0])
    elif user_name != user.user_name:
        _start_player(session, user_name)
    else:
        client_data = {}
        ev.dispatch('user_connect', user, client_data)
        session.append({'user_login': client_data})


def get_session(session_id):
    return _session_map.get(session_id)


def player_session(player_id):
    return _player_session_map.get(player_id)


def player_info_map():
    return _player_info_map


def logged_in_players():
    return set(_player_session_map.keys())


def _config():
    global _link_status_reg, _broadcast_reg, _link_dead_interval, _link_dead_prune
    check_link_interval = config_value('check_link_interval', 60)
    log.info("Registering check link interval as {} seconds", check_link_interval)
    _link_status_reg = ev.register_p(_check_link_status, seconds=check_link_interval)
    _broadcast_reg = ev.register_p(_broadcast_status, seconds=config_value('broadcast_interval'))

    _link_dead_prune = timedelta(seconds=config_value('link_dead_prune'))
    _link_dead_interval = timedelta(seconds=config_value('link_dead_interval'))


def _start_app_session():
    session_id = _get_next_id()
    session = AppSession().attach()
    _session_map[session_id] = session
    session.append({'connect': session_id})
    ev.dispatch('session_connect', session)
    return session


def start_session():
    session_id = _get_next_id()
    session = ClientSession().attach()
    _session_map[session_id] = session
    return session_id, session


def _reconnect_session(session_id, player_id):
    session = get_session(session_id)
    if not session or not session.ld_time or not session.player or session.player.dbo_id != player_id:
        new_session = _start_app_session()
        new_session.append({'invalid_session': session_id})
        return new_session
    stale_output = session.pull_output()
    client_data = {}
    session.append({'connect': session_id})
    ev.dispatch('session_connect', session)
    session.append({'login': client_data})
    ev.dispatch('user_connect', session.user, client_data)
    ev.dispatch('player_connect', session.player, client_data)
    session.append_list(stale_output)
    session.player.display_line("-- Reconnecting Session --", 'system')
    session.player.parse("look")
    return session


def _start_player(session, player_id):
    old_session = player_session(player_id)
    if old_session:
        player = old_session.player
        old_session.player = None
        old_session.user = None
        old_session.append({'other_location': player_id})
        _connect_session(session, player, '-- Existing Session Logged Out --')
        player.parse('look')
    else:
        player = um.find_player(player_id)
        if not player:
            session.append('logout')
            return
        _connect_session(session, player, 'Welcome {}'.format(player.name))
        um.login_player(player)
    client_data = {}
    ev.dispatch('user_connect', session.user, client_data)
    ev.dispatch('player_connect', player, client_data)
    session.append({'login': client_data})
    _player_info_map[player.dbo_id] = session.player_info(session.activity_time)
    _broadcast_status()


def _connect_session(session, player, text):
    if player.user_id != session.user.dbo_id:
        raise ClientError("Player user does not match session user")
    _player_session_map[player.dbo_id] = session
    session.connect_player(player)
    session.display_line({'text': text, 'display': 'system'})


def _player_logout(session):
    session.user = None
    player = session.player
    if not player:
        return
    player.last_logout = int(time.time())
    um.logout_player(player)
    session.player = None
    del _player_info_map[player.dbo_id]
    del _player_session_map[player.dbo_id]
    session.append({'logout': 'logout'})
    _broadcast_status()


def _get_next_id():
    u_session_id = b64encode(bytes(urandom(16))).decode()
    while get_session(u_session_id):
        u_session_id = b64encode(bytes(urandom(16))).decode()
    return u_session_id


def _check_link_status():
    now = datetime.now()
    for session_id, session in _session_map.copy().items():
        if session.ld_time:
            if now - session.ld_time > _link_dead_prune:
                del _session_map[session_id]
                session.detach()
        elif not session.socket and now - session.attach_time > _link_dead_interval:
            session.link_failed("Timeout")


def _broadcast_status():
    now = datetime.now()
    for session in _player_session_map.values():
        if session.player:
            _player_info_map[session.player.dbo_id] = session.player_info(now)
    ev.dispatch('player_list', _player_info_map)


class ClientSession(Attachable):
    def _on_attach(self):
        self._pulse_reg = None
        self.attach_time = datetime.now()
        self.socket = None
        self.ld_time = None
        self._reset()

    def _on_detach(self):
        ev.dispatch('session_disconnect', self)

    def attach_socket(self, socket):
        self.attach_time = datetime.now()
        self.ld_time = None
        if self.socket:
            self.append({'link_status': 'cancel'})
            self.flush()
        self.socket = socket
        socket.session = self

    def append(self, data):
        self._output.append(data)
        self._schedule()

    def append_list(self, data):
        self._output += data
        self._schedule()

    def link_failed(self, reason):
        log.debug("Link failed {}", reason)
        self.ld_time = datetime.now()
        self.socket = None

    def pull_output(self):
        output = self._output
        if self._pulse_reg:
            ev.unregister(self._pulse_reg)
            self._pulse_reg = None
        self._reset()
        return output

    def flush(self):
        self.activity_time = datetime.now()
        if self.socket:
            self._output.append({'link_status': "good"})
            output = self.pull_output()
            self.socket.write_message(json_encode(output))

    def _schedule(self):
        if not self._pulse_reg:
            self._pulse_reg = ev.register("pulse", self.flush)

    def _reset(self):
        self._lines = []
        self._output = []
        self._status = None


class AppSession(ClientSession):
    def _on_attach(self):
        self.user = None
        self.player = None

    def _on_detach(self):
        ev.dispatch('player_logout', self)

    def connect_user(self, user):
        self.user = user
        self.activity_time = datetime.now()

    def connect_player(self, player):
        self.player = player
        player.session = self
        self.activity_time = datetime.now()

    def player_info(self, now):
        if self.ld_time:
            status = "Link Dead"
        else:
            idle = (now - self.activity_time).seconds
            if idle < 60:
                status = "Active"
            else:
                status = "Idle: " + str(idle // 60) + "m"
        return {'status': status, 'name': self.player.name, 'loc': self.player.location}

    def display_line(self, display_line):
        if not self._lines:
            self.append({'display': {'lines': self._lines}})
        self._lines.append(display_line)

    def update_status(self, status):
        try:
            self._status.update(status)
        except AttributeError:
            self._status = status
            self.append({'status': status})
