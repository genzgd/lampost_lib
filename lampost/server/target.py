from lampost.di.resource import Injected, module_inject
from lampost.gameops.target import target_gen

sm = Injected('session_manager')
module_inject(__name__)


@target_gen
def logged_in(key_type, target_key, *_):
    session = sm.player_session(target_key)
    if session:
        yield session.player
logged_in.absent_msg = "That player is not logged in."
