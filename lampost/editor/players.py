from lampost.di.app import on_app_start
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


@on_app_start
def _start():
    ev.register('imm_update', _imm_update)


class EditorImmortal:
    def __init__(self, player):
        self.edit_dto = {'dbo_key_type': 'immortal', 'dbo_id': player.dbo_id, 'imm_level': player.imm_level}

    def can_write(self, *_):
        return False

    def can_read(self, *_):
        return False


def _imm_update(player, old_level, session=None):
    immortal = EditorImmortal(player)
    if not old_level and player.imm_level:
        update_type = 'create'
    elif old_level and not player.imm_level:
        update_type = 'delete'
    else:
        update_type = 'update'
    edit_update.publish_edit(update_type, immortal, session)


class PlayerEditor(Editor):
    def __init__(self):
        super().__init__('player', 'admin')

    def metadata(self, **_):
        return {'perms': {'add': False, 'refresh': True}}

    def _pre_delete(self, target_player, session):
        if target_player.imm_level >= perm.perm_level('supreme'):
            raise DataError("Cannot delete root user.")
        if target_player.session:
            raise DataError("Player is logged in.")
        check_player_perm(target_player, session.player)

    def _post_delete(self, target_player, session):
        um.player_cleanup(target_player.dbo_id)
        user = db.load_object(target_player.user_id, 'user')
        if not user:
            log.warn("Removed player without user")
            return
        user.player_ids.remove(target_player.dbo_id)
        if not user.player_ids:
            db.delete_object(user)
            edit_update.publish_edit('delete', user, session, True)
        else:
            db.save_object(user)
            edit_update.publish_edit('update', user, session, True)

    def _pre_update(self, player_update, target_player, *_):
        if player_update['imm_level'] != target_player.imm_level:
            if target_player.session:
                raise DataError("Please promote (or demote} {} in game".format(target_player.name))

    def _post_update(self, target_player, *_):
        perm.update_immortal_list(target_player)


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
    def __init__(self):
        super().__init__('user', 'admin')

    def _pre_delete(self, user, *_):
        if user.imm_level:
            raise DataError("Please remove all immortals from this account before deleting.")
        for player_id in user.player_ids:
            player = db.load_object(player_id, 'player')
            if player and player.session:
                raise DataError("{} is logged in.".format(player.name))

    def _post_delete(self, user, session):
        for player_id in user.player_ids:
            player = db.load_object(player_id, 'player')
            if player:
                db.delete_object(player)
                edit_update.publish_edit('delete', player, session, True)

    def _pre_update(self, user_update, target_user, session):
        if user_update['password']:
            if target_user.dbo_id == session.player.user_id:
                raise DataError("Please change your password through the normal UI.")
            user_update['password'] = make_hash(user_update['password'])
            user_update['password_reset'] = False
        else:
            user_update['password'] = target_user.password

    def metadata(self, **_):
        return {'perms': {'add': False, 'refresh': True}}
