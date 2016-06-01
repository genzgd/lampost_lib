from lampost.server.services import ClientService
from lampost.gameops.action import make_action
from lampost.di.resource import Injected, module_inject
from lampost.di.config import config_value
from lampost.util.lputil import timestamp

ev = Injected('dispatcher')
db = Injected('datastore')
cs = Injected('channel_service')
module_inject(__name__)


class Channel():
    def __init__(self, channel_type, instance_id=None, general=False, aliases=()):
        if instance_id == 'next':
            instance_id = db.db_counter('channel')
        make_action(self, (channel_type,) + aliases)
        self.id = "{}_{}".format(channel_type, instance_id) if instance_id else channel_type
        cs.register_channel(self.id, general)

    def __call__(self, source, command, **_):
        space_ix = command.find(" ")
        if space_ix == -1:
            return source.display_line("Say what?")
        self.send_msg(source.name + ":" + command[space_ix:])

    def send_msg(self, msg):
        cs.dispatch_message(self.id, msg)

    def disband(self):
        cs.unregister_channel(self.id)

    def remove_sub(self, player):
        player.diminish_soul(self)
        player.active_channels.remove(self.id)
        if player.session:
            cs.remove_sub(player.session, self.id)

    def add_sub(self, player):
        player.enhance_soul(self)
        player.active_channels.add(self.id)
        cs.add_sub(player.session, self.id)


class ChannelService(ClientService):

    def _post_init(self):
        super()._post_init()
        self.all_channels = db.fetch_set_keys('all_channels')
        self.general_channels = db.fetch_set_keys('general_channels')
        ev.register('maintenance', self._prune_channels)
        ev.register('session_connect', self._session_connect)
        ev.register('player_connect', self._player_connect)
        ev.register('player_logout', self._player_logout)

    def register_channel(self, channel_id, general=False):
        db.add_set_key('all_channels', channel_id)
        self.all_channels.add(channel_id)
        if general:
            db.add_set_key('general_channels', channel_id)
            self.general_channels.add(channel_id)

    def unregister_channel(self, channel_id):
        db.delete_set_key('all_channels', channel_id)
        self.all_channels.discard(channel_id)
        self.general_channels.discard(channel_id)

    def dispatch_message(self, channel_id, text):
        message = {'id': channel_id, 'text': text}
        timestamp(message)
        for session in self.sessions:
            if channel_id in session.channel_ids:
                session.append({'channel': message})
        db.add_db_list(channel_key(channel_id), {'text': text, 'timestamp': message['timestamp']})

    def add_sub(self, session, channel_id):
        session.channel_ids.add(channel_id)
        session.append({'channel_subscribe': {'id': channel_id, 'messages': db.get_db_list(channel_key(channel_id))}})

    def remove_sub(self, session, channel_id):
        session.channel_ids.remove(channel_id)
        session.append({'channel_unsubscribe': channel_id})

    def _session_connect(self, session, *_):
        self.register(session, None)
        if not hasattr(session, 'channel_ids'):
            session.channel_ids = set()
        for channel_id in session.channel_ids.copy():
            if channel_id not in self.general_channels:
                self.remove_sub(session, channel_id)
        for channel_id in self.general_channels:
            self.add_sub(session, channel_id)

    def _player_connect(self, player, *_):
        for channel_id in player.active_channels:
            if channel_id not in player.session.channel_ids:
                self.add_sub(player.session, channel_id)
        for channel_id in player.session.channel_ids.copy():
            if channel_id not in player.active_channels:
                self.remove_sub(player.session, channel_id)

    def _player_logout(self, session):
        self._session_connect(session)

    def _prune_channels(self):
        for channel_id in self.all_channels:
            db.trim_db_list(channel_key(channel_id), 0, config_value('max_channel_history'))


def channel_key(channel_id):
    return 'channel:{}'.format(channel_id)
