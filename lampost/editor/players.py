from lampost.server.handlers import SessionHandler
from lampost.di.resource import Injected, module_inject
from lampost.db.exceptions import DataError
from lampost.editor.editor import Editor
from lampost.util.encrypt import make_hash

log = Injected('log')
ev = Injected('dispatcher')
db = Injected('datastore')
perm = Injected('perm')
um = Injected('user_manager')
edit_update = Injected('edit_update_service')
module_inject(__name__)


def _post_init():
    ev.register('imm_level_change', imm_level_change)


class EditorImmortal():
    def __init__(self, player):
        self.edit_dto = {'dbo_key_type': 'immortal', 'dbo_id': player.dbo_id, 'imm_level': player.imm_level}

    def can_write(self, *_):
        return False

    def can_read(self, *_):
        return False


def imm_level_change(player, old_level, session=None):
    immortal = EditorImmortal(player)
    if not old_level and player.imm_level:
        update_type = 'create'
    elif old_level and not player.imm_level:
        update_type = 'delete'
    else:
        update_type = 'update'
    edit_update.publish_edit(update_type, immortal, session)


class ImmortalsList(SessionHandler):
    def main(self):
        self._return([{'dbo_id': key, 'name': key, 'imm_level': value, 'dbo_key_type': 'immortal'} for key, value in
                      perm.immortals.items()])


class PlayerEditor(Editor):
    def initialize(self):
        super().initialize('player', 'admin')

    def metadata(self):
        return {'perms': {'add': False, 'refresh': True}}

    def _pre_delete(self, player):
        if player.imm_level >= perm.perm_level('supreme'):
            raise DataError("Cannot delete root user.")
        if player.session:
            raise DataError("Player is logged in.")
        check_player_perm(player, self.player)

    def _post_delete(self, player):
        um.player_cleanup(player.dbo_id)
        user = db.load_object(player.user_id, 'user')
        if not user:
            log.warn("Removed player without user")
            return
        user.player_ids.remove(player.dbo_id)
        if not user.player_ids:
            db.delete_object(user)
            edit_update.publish_edit('delete', user, self.session, True)
        else:
            db.save_object(user)
            edit_update.publish_edit('update', user, self.session, True)

    def _pre_update(self, old_player):
        if self.raw['imm_level'] != old_player.imm_level:
            if old_player.session:
                raise DataError("Please promote (or demote} {} in game".format(old_player.name))

    def _post_update(self, player):
        perm.update_immortal_list(player)


def check_player_perm(player, immortal):
    user = db.load_object(player.user_id, 'user')
    if not user:
        log.error("Missing user for player delete.")
        return
    if user.imm_level > 0:
        perm.check_perm(immortal, 'supreme')
    else:
        perm.check_perm(immortal, 'admin')


class UserEditor(Editor):
    def initialize(self):
        super().initialize('user', 'admin')

    def _pre_delete(self, user):
        if user.imm_level:
            raise DataError("Please remove all immortals from this account before deleting.")
        for player_id in user.player_ids:
            player = db.load_object(player_id, 'player')
            if player and player.session:
                raise DataError("{} is logged in.".format(player.name))

    def _post_delete(self, user):
        for player_id in user.player_ids:
            player = db.load_object(player_id, 'player')
            if player:
                db.delete_object(player)
                edit_update.publish_edit('delete', player, self.session, True)

    def _pre_update(self, old_user):
        if self.raw['password']:
            if old_user.dbo_id == self.player.user_id:
                raise DataError("Please change your password through the normal UI.")
            self.raw['password'] = make_hash(self.raw['password'])
            self.raw['password_reset'] = False
        else:
            self.raw['password'] = old_user.password

    def metadata(self):
        return {'perms': {'add': False, 'refresh': True}}
