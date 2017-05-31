from lampost.di.resource import Injected, module_inject

ev = Injected('dispatcher')
edit_update = Injected('edit_update_service')
module_inject(__name__)


def register():
    ev.register('imm_update', imm_update)


def imm_update(player, old_level, session=None):
    immortal = EditorImmortal(player)
    if not old_level and player.imm_level:
        update_type = 'create'
    elif old_level and not player.imm_level:
        update_type = 'delete'
    else:
        update_type = 'update'
    edit_update.publish_edit(update_type, immortal, session)


class EditorImmortal:
    def __init__(self, player):
        self.edit_dto = {'dbo_key_type': 'immortal', 'dbo_id': player.dbo_id, 'imm_level': player.imm_level}

    def can_write(self, *_):
        return False

    def can_read(self, *_):
        return False
