import random
import string

from lampost.di.resource import Injected, module_inject
from lampost.db.exceptions import DataError
from lampost.di.config import ConfigVal
from lampost.server.link import link_module
from lampost.util.encrypt import make_hash
from lampost.util.lputil import ClientError

db = Injected('datastore')
ev = Injected('dispatcher')
um = Injected('user_manager')
sm = Injected('session_manager')
perm = Injected('perm')
email = Injected('email_sender')
edit_update = Injected('edit_update_service')
friend_service = Injected('friend_service')
module_inject(__name__)
link_module(__name__)

lampost_title = ConfigVal('lampost_title')


def get_account(session, player, user_id, **_):
    if session.user.dbo_id != user_id:
        perm.check_perm(player, 'admin')
    return db.load_object(user_id, "user").edit_dto


def create_account(session, account_name, password, email=None, **_):
    account_name = account_name.lower()
    if db.get_index("ix:user:name", account_name) or db.object_exists('player', account_name) or \
                    account_name in perm.system_accounts or db.object_exists('area', account_name):
        raise DataError("InUse: {}".format(account_name))
    user = um.create_user(account_name, password, email.lower())
    session.connect_user(user)
    return {'user_id': user.dbo_id}


def update_account(session, player, user_id, user_update, **_):
    if session.user.dbo_id != user_id:
        perm.check_perm(player, 'admin')

    user = db.load_object(user_id, "user")
    if not user:
        raise ClientError(user_id + " does not exist!")

    um.check_name(user_update['user_name'], user)
    if user_update['password']:
        user_update['password'] = make_hash(user_update['password'])
    else:
        user_update['password'] = user.password
    user_update['email'] = user_update['email'].lower()
    db.update_object(user, user_update)
    edit_update.publish_edit('update', user)


def delete_account(session, password, **_):
    user = session.user
    if user.player_ids:
        um.validate_password(user, password)
        ev.dispatch('player_logout', session)
        um.delete_user(user)


def create_player(user_id, player_name, player_data, **_):
    user = db.load_object(user_id, "user")
    if not user:
        raise DataError("User {0} does not exist".format(user_id))
    player_name = player_name.lower()
    if (player_name != user.user_name and db.get_index("ix:user:user_name", player_name)) \
            or db.object_exists('player', player_name) or db.object_exists('area', player_name) \
            or player_name in perm.system_accounts:
        raise DataError(player_name.capitalize() + " is in use.")
    player_data['dbo_id'] = player_name
    player = db.create_object("player", player_data)
    um.attach_player(user, player)


def get_players(user_id, **_):
    user = db.load_object(user_id, "user")
    if not user:
        raise ClientError("User {} does not exist".format(user_id))
    return _player_list(user.player_ids)


def delete_player(session, player_id, password, **_):
    user = session.user
    um.validate_password(user, password)
    if not player_id in user.player_ids:
        raise ClientError("Player {} longer associated with user".format(player_id))
    um.delete_player(user, player_id)
    return _player_list(user.player_ids)


def update_display(session, displays, **_):
    session.user.displays = displays
    db.save_object(session.user)


def send_name(info, **_):
    user_email = info.lower()
    user_id = db.get_index("ix:user:email", user_email)
    if not user_id:
        raise DataError("User Email Not Found")
    user = db.load_object(user_id, "user")
    email_msg = "Your {} account name is {}.\nThe players on this account are {}." \
        .format(lampost_title.value, user.user_name,
                    ','.join([player_id.capitalize() for player_id in user.player_ids]))
    email.send_targeted_email('Account/Player Names', email_msg, [user])


def temp_password(info, **_):
    info = info.lower()
    user_id = db.get_index("ix:user:user_name", info)
    if not user_id:
        player = db.load_object(info, "player")
        if player:
            user_id = player.user_id
        else:
            raise DataError("Unknown name or account {}".format(info))
    user = db.load_object(user_id, "user")
    if not user.email:
        raise DataError("No Email On File For {}".format(info))
    temp_pw = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(12))
    email_msg = "Your {} temporary password is {}.\nYou will be asked to change it after you log in." \
        .format(lampost_title.value, temp_pw)
    user.password = make_hash(temp_pw)
    user.password_reset = True
    db.save_object(user)
    email.send_targeted_email('Your {} temporary password.'.format(lampost_title.value), email_msg, [user])


def set_password(session, password, **_):
    user = session.user
    user.password = make_hash(password)
    user.password_reset = False
    db.save_object(user)


def notifies(session, notifies, **_):
    user = session.user
    user.notifies = notifies
    db.save_object(user)
    friend_service.update_notifies(user.dbo_id, user.notifies)


def _player_list(player_ids):
    players = []
    for player_id in player_ids:
        player = db.load_object(player_id, "player")
        players.append({'name': player.name, 'dbo_id': player.dbo_id})
    return players
