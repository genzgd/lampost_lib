from lampost.di.app import on_app_start
from lampost.di.config import ConfigVal
from lampost.di.resource import Injected, module_inject
from lampost.gameops.action import ActionError
from lampost.user.core import User

db = Injected('datastore')
ev = Injected('dispatcher')
sm = Injected('session_manager')
um = Injected('user_manager')
email = Injected('email_sender')
perm = Injected('perm')
module_inject(__name__)

_REQUEST_KEY = "friend_requests"
_FRIEND_EMAIL_KEY = "friend_email_notifies"
_ALL_EMAIL_KEY = "all_email_notifies"

lampost_title = ConfigVal('lampost_title')


@on_app_start
def _start():
    ev.register('player_attach', _check_friends)
    ev.register('player_deleted', _delete_player)


def friend_request(source, target):
    req_key = ':'.join([source.dbo_id, target.dbo_id])
    if db.set_key_exists(_REQUEST_KEY, req_key):
        raise ActionError("You already have a friend request to {} outstanding.".format(target.name))
    ev.dispatch('player_message', 'friend_req', {'friend_id': source.dbo_id, 'friend_name': source.name},
                target.dbo_id, source.dbo_id)
    db.add_set_key(_REQUEST_KEY, req_key)


def remove_request(source_id, target_id):
    db.delete_set_key('friend_requests', ':'.join([source_id, target_id]))


def add_friend(source_id, target_id):
    db.add_set_key(friend_key(source_id), target_id)
    db.add_set_key(friend_key(target_id), source_id)


def del_friend(friend_one_id, friend_two_id):
    db.delete_set_key(friend_key(friend_one_id), friend_two_id)
    db.delete_set_key(friend_key(friend_two_id), friend_one_id)


def friend_list(player_id):
    return ' '.join([um.id_to_name(friend_id) for friend_id in db.fetch_set_keys(friend_key(player_id))])


def is_friend(player_id, friend_id):
    return db.set_key_exists(friend_key(player_id), friend_id)


def update_notifies(user_id, notifies):
    if 'friendEmail' in notifies:
        db.add_set_key(_FRIEND_EMAIL_KEY, user_id)
    else:
        db.delete_set_key(_FRIEND_EMAIL_KEY, user_id)
    if 'allEmail' in notifies:
        db.add_set_key(_ALL_EMAIL_KEY, user_id)
    else:
        db.delete_set_key(_ALL_EMAIL_KEY, user_id)


def _check_friends(player):
    logged_in_players = sm.logged_in_players()
    friends = set(db.fetch_set_keys(friend_key(player.dbo_id)))
    logged_in_friends = logged_in_players.intersection(friends)
    for friend_id in logged_in_friends:
        sm.player_session(friend_id).append({'friend_login': {'name': player.name}})
    notify_user_ids = {db.get_index('ix:player:user', player_id) for player_id in
                       friends.difference(logged_in_friends)}
    notify_user_ids = notify_user_ids.intersection(db.fetch_set_keys(_FRIEND_EMAIL_KEY))
    notify_user_ids = notify_user_ids.union(db.fetch_set_keys(_ALL_EMAIL_KEY))
    logged_in_user_ids = {sm.player_session(player_id).player.user_id for player_id in logged_in_players}
    notify_user_ids = notify_user_ids.difference(logged_in_user_ids)

    users = [db.load_object(user_id, User) for user_id in notify_user_ids]
    if users:
        email.send_targeted_email("{} Login".format(player.name),
                                  "Your friend {} just logged into {}.".format(player.name, lampost_title.value), users)


def _delete_player(player_id):
    for friend_id in db.fetch_set_keys(friend_key(player_id)):
        del_friend(player_id, friend_id)


def friend_key(player_id):
    return 'friends:{}'.format(player_id)
