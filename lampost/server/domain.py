from lampost.db.dbo import KeyDBO, SystemDBO
from lampost.db.dbofield import DBOField
from lampost.di.resource import Injected, module_inject

perm = Injected('perm')
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