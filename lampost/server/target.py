from lampost.di.resource import Injected, module_inject
from lampost.gameops.target import target_gen

sm = Injected('session_manager')
um = Injected('user_manager')
module_inject(__name__)


@target_gen
def logged_in(key_type, target_key, *_):
    if key_type == 'primary':
        session = sm.player_session(target_key)
        if session:
            yield session.player


logged_in.absent_msg = "Player {target} is not logged in."


@target_gen
def player_id(key_type, target_key, *_):
    if key_type == 'primary':
        target_id = um.name_to_id(target_key)
        if um.player_exists(target_id):
            yield target_id
    elif key_type == 'abbrev':
        for abbrev_id in um.player_abbrev(target_key):
            yield abbrev_id


player_id.absent_msg = "Player {target} does not exist"
