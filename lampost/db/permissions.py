from lampost.di.app import on_app_start
from lampost.di.config import config_value, on_config_change
from lampost.di.resource import Injected, module_inject
from lampost.util.lputil import PermError

db = Injected('datastore')
module_inject(__name__)

system_accounts = []
imm_levels = {}


@on_app_start(priority=500)
@on_config_change
def _init():
    global imm_levels
    global _level_to_name
    global immortals
    global system_accounts
    imm_levels = config_value('imm_levels')
    system_accounts = config_value('system_accounts')
    _level_to_name = {level: name for name, level in imm_levels.items()}
    system_level = config_value('system_level')
    immortals = db.get_all_hash('immortals')
    immortals.update({account: system_level for account in system_accounts})


def perm_name(num_level):
    return _level_to_name.get(num_level, 'player')


def update_immortal_list(player):
    if player.imm_level:
        db.set_db_hash('immortals', player.dbo_id, player.imm_level)
        immortals[player.dbo_id] = player.imm_level
    else:
        db.delete_index('immortals', player.dbo_id)
        try:
            del immortals[player.dbo_id]
        except KeyError:
            pass


def has_perm(immortal, action):
    try:
        check_perm(immortal, action)
        return True
    except PermError:
        return False


def check_perm(immortal, action):
    if immortal.imm_level >= imm_levels['supreme']:
        return
    if isinstance(action, int):
        perm_required = action
    elif action in imm_levels:
        perm_required = imm_levels[action]
    elif hasattr(action, 'can_write'):
        if action.can_write(immortal):
            return
        raise PermError
    else:
        imm_level = getattr(action, 'imm_level', 0)
        perm_required = imm_levels.get(imm_level, imm_level)
    if immortal.imm_level < perm_required:
        raise PermError


def perm_level(label):
    return imm_levels.get(label, imm_levels['admin'])


def perm_to_level(label):
    return imm_levels.get(label)


def is_supreme(immortal):
    return immortal.imm_level >= imm_levels['supreme']
