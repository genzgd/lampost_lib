from lampost.di.resource import Injected, module_inject
from lampost.gameops.target import target_gen

sm = Injected('session_manager')
um = Injected('user_manager')
module_inject(__name__)


@target_gen
def logged_in(match):
    if match.target_str:
        session = sm.player_session(match.target_str.lower().strip())
        if session:
            yield session.player
logged_in.absent_msg = "That player is not logged in."


@target_gen
def player(match):
    if not match.target_str:
        return


player.absentMsg = "That player does not exist"
