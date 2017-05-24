from lampost.di.resource import Injected, module_inject
from lampost.gameops.target import target_gen

sm = Injected('session_manager')
um = Injected('user_manager')
db = Injected('datastore')
module_inject(__name__)


@target_gen
def player_online(key_type, target_key, entity, *_):
    if key_type == 'primary':
        session = sm.player_session(target_key)
        if session and session.player != entity:
            yield session.player


player_online.absent_msg = "Player {target} is not logged in."


@target_gen
def player_db(key_type, target_key, entity, *_):
    if key_type == 'primary':
        target_id = um.name_to_id(target_key)
        player = db.load_object(target_id, 'player')
        if player and player != entity:
            yield player


player_db.absent_msg = "Player {target} does not exist"
