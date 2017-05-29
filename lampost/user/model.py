from lampost.db.dbo import KeyDBO, SystemDBO
from lampost.db.dbofield import AutoField, DBOField
from lampost.di.resource import Injected, module_inject
from lampost.event.attach import Attachable

log = Injected('log')
perm = Injected('perm')
ev = Injected('dispatcher')
module_inject(__name__)


class User(KeyDBO, SystemDBO):
    dbo_key_type = "user"
    dbo_set_key = "users"
    dbo_indexes = "user_name", "email"

    user_name = DBOField('')
    password = DBOField()
    password_reset = DBOField(False)
    email = DBOField('')
    notes = DBOField('')

    player_ids = DBOField([])
    displays = DBOField({})
    notifies = DBOField([])

    @property
    def edit_dto(self):
        dto = super().edit_dto
        dto['password'] = ''
        return dto

    @property
    def imm_level(self):
        if self.player_ids:
            return max([perm.immortals.get(player_id, 0) for player_id in self.player_ids])
        return 0


class Player(KeyDBO, SystemDBO, Attachable):
    dbo_key_type = "player"
    dbo_set_key = "players"

    session = AutoField()

    user_id = DBOField(0)
    created = DBOField(0)
    imm_level = DBOField(0)
    last_login = DBOField(0)
    last_logout = DBOField(0)
    age = DBOField(0)

    @property
    def edit_dto(self):
        dto = super().edit_dto
        dto['logged_in'] = "Yes" if self.session else "No"
        return dto

    @property
    def name(self):
        return self.dbo_id.capitalize()

    @property
    def location(self):
        return "Online" if self.session else "Offline"

    def _on_attach(self):
        ev.register_p(self.autosave, seconds=20)
        self.active_channels = set()
        self.last_tell = None

    def _on_detach(self):
        self.session = None

    def check_logout(self):
        pass

    def display_line(self, text, display='default'):
        if text and self.session:
            self.session.display_line({'text': text, 'display': display})

    def output(self, output):
        if self.session:
            self.session.append(output)

    def receive_broadcast(self, broadcast):
        self.display_line(broadcast.translate(self), broadcast.display)
