from lampost.di.app import on_app_start
from lampost.di.resource import Injected, module_inject
from lampost.util.lputil import timestamp

log = Injected('log')
db = Injected('datastore')
ev = Injected('dispatcher')
sm = Injected('session_manager')
um = Injected('user_manager')
module_inject(__name__)


@on_app_start
def _start():
    ev.register("player_deleted", _remove_player_messages)
    ev.register("player_connect", _player_connect)
    ev.register("player_message", add_message)


def get_messages(player_id):
    return db.get_all_db_hash(_message_key(player_id))


def add_message(msg_type, content, player_id, source_id=None):
    msg_id = db.db_counter("message_id")
    message = {'msg_type': msg_type, 'msg_id': msg_id, 'content': content, 'source': um.id_to_name(source_id)}
    timestamp(message)
    db.set_db_hash(_message_key(player_id), msg_id, message)
    try:
        sm.player_session(player_id).append({'new_message': message})
    except AttributeError:
        pass


def remove_message(player_id, msg_id):
    db.remove_db_hash(_message_key(player_id), msg_id)


def block_messages(player_id, source_id):
    if is_blocked(player_id, source_id):
        return
    db.add_set_key(_block_key(player_id), source_id)
    add_message('system', "{} has blocked messages from you.".format(um.id_to_name(player_id)), source_id)


def unblock_messages(player_id, source_id):
    db.delete_set_key(_block_key(player_id), source_id)
    add_message('system', "{} has unblocked messages from you.".format(um.id_to_name(player_id)), source_id)


def is_blocked(player_id, source_id):
    if source_id:
        return db.set_key_exists(_block_key(player_id), source_id)
    return False


def block_list(player_id):
    return ' '.join([um.id_to_name(block_id) for block_id in db.fetch_set_keys(_block_key(player_id))])


def _remove_player_messages(player_id):
    db.delete_key(_message_key(player_id))
    db.delete_key(_block_key(player_id))


def _player_connect(player, connect):
    connect['messages'] = get_messages(player.dbo_id)


def _message_key(player_id):
    return "messages:{}".format(player_id)


def _block_key(player_id):
    return "blocks:{}".format(player_id)
