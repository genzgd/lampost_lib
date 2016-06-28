from lampost.di.resource import Injected, module_inject
from lampost.gameops.target import target_gen, make_gen

sm = Injected('session_manager')
module_inject(__name__)


def recursive_targets(key_type, target_list, target_key):
    for target in target_list:
        try:
            if target_key in getattr(target.target_keys, key_type):
                yield target
        except AttributeError:
            pass
        for sub_target in recursive_targets(key_type, getattr(target, 'target_providers', ()), target_key):
            yield sub_target


@target_gen
def self(key_type, target_key, entity, *_):
    if target_key == 'self' or target_key in getattr(entity.target_keys, key_type):
        yield entity


@target_gen
def func_owner(key_type, target_key, entity, action, *_):
    return recursive_targets(key_type, [action.__self__], target_key)


@target_gen
def action_owner(key_type, target_key, entity, action, *_):
    try:
        if target_key in getattr(action.owner.target_keys, key_type):
            yield action.owner
    except AttributeError:
        pass


@target_gen
def func_providers(key_type, target_key, entity, action, *_):
    for target in action.__self__.target_providers:
        try:
            if target_key in getattr(target.target_keys, key_type):
                yield target
        except AttributeError:
            pass


@target_gen
def action(key_type, target_key, entity, action):
    return recursive_targets(key_type, [action], target_key)


@target_gen
def equip(key_type, target_key, entity, *_):
    return recursive_targets(key_type, [equip for equip in entity.inven if getattr(equip, 'current_slot', None)], target_key)
equip.absent_msg = "You don't have `{target}' equipped."


@target_gen
def inven(key_type, target_key, entity, *_):
    return recursive_targets(key_type, [equip for equip in entity.inven if not getattr(equip, 'current_slot', None)],
                             target_key)
inven.absent_msg = "You don't have `{target}'."


@target_gen
def env(key_type, target_key, entity, *_):
    for extra in entity.env.extras:
        try:
            if target_key in getattr(extra.target_keys, key_type):
                yield extra
        except AttributeError:
            pass
        for target in recursive_targets(key_type, getattr(extra, 'target_providers', ()), target_key):
            yield target


@target_gen
def feature(key_type, target_key, entity, *_):
    return recursive_targets(key_type, [feature for feature in entity.env.features], target_key)


@target_gen
def env_living(key_type, target_key, entity, *_):
    return recursive_targets(key_type, [living for living in entity.env.denizens],  target_key)


@target_gen
def env_items(key_type, target_key, entity, *_):
    return recursive_targets(key_type, [item for item in entity.env.inven], target_key)


@target_gen
def env_default(key_type, target_key, entity, *_):
    if not target_key:
        yield entity.env


make_gen('self feature env_living env_items equip inven', 'std')

make_gen('std env_default', 'default')


@target_gen
def logged_in(key_type, target_key, *_):
    session = sm.player_session(" ".join(target_key))
    if session:
        yield session.player
logged_in.absent_msg = "That player is not logged in."

