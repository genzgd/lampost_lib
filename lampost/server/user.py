from base64 import b64decode
import time

from lampost.di.resource import Injected, module_inject
from lampost.db.dbo import KeyDBO, SystemDBO
from lampost.db.dbofield import DBOField
from lampost.db.exceptions import DataError
from lampost.util.encrypt import make_hash, check_password
from lampost.util.lputil import ClientError

log = Injected('log')
perm = Injected('perm')
db = Injected('datastore')
ev = Injected('dispatcher')
edit_update = Injected('edit_update_service')
module_inject(__name__)


class User(KeyDBO, SystemDBO):
    dbo_key_type = "user"
    dbo_set_key = "users"
    dbo_indexes = "user_name", "email"

    user_name = DBOField('')
    password = DBOField()
    password_reset = DBOField(False)
    email = DBOField('')
    notes = DBOField('')

    player_ids = DBOField([])
    displays = DBOField({})
    notifies = DBOField([])

    @property
    def edit_dto(self):
        dto = super().edit_dto
        dto['password'] = ''
        return dto

    @property
    def imm_level(self):
        if self.player_ids:
            return max([perm.immortals.get(player_id, 0) for player_id in self.player_ids])
        return 0


class UserManager():
    def _post_init(self):
        ev.register("user_connect", self._user_connect)
        ev.register("player_connect", self._player_connect)

    def validate_user(self, user_name, password):
        user = self.find_user(user_name)
        if not user:
            raise ClientError()
        self.validate_password(user, password)
        return user

    def validate_password(self, user, password):
        if check_password(user.password, password):
            return
        salt, old_password = user.password.split('$')
        if check_password(b64decode(bytes(old_password, 'utf-8')), password, bytes(salt, 'utf-8')):
            db.warn("Using old password for account {}", user.user_name)
            user.password_reset = True
            db.save_object(user)
        else:
            raise ClientError("invalid_password")

    def find_user(self, user_name):
        user_name = user_name.lower()
        user_id = db.get_index("ix:user:user_name", user_name)
        if user_id:
            return db.load_object(user_id, User)
        player = db.load_object(user_name, "player")
        if player:
            return db.load_object(player.user_id, User)
        return None

    def delete_user(self, user):
        for player_id in user.player_ids:
            self._player_delete(player_id)
        db.delete_object(user)
        edit_update.publish_edit('delete', user)

    def delete_player(self, user, player_id):
        if user:
            self._player_delete(player_id)
            user.player_ids.remove(player_id)
            db.save_object(user)

    def attach_player(self, user, player):
        user.player_ids.append(player.dbo_id)
        db.set_index('ix:player:user', player.dbo_id, user.dbo_id)
        ev.dispatch('player_create', player, user)
        player.user_id = user.dbo_id
        db.save_object(player)
        db.save_object(user)
        return player

    def find_player(self, player_id):
        return db.load_object(player_id, "player")

    def create_user(self, user_name, password, email=""):
        user_raw = {'dbo_id': db.db_counter('user_id'), 'user_name': user_name,
                'email': email, 'password': make_hash(password),
                'notifies': ['friendSound', 'friendDesktop']}
        user = db.create_object(User, user_raw)
        edit_update.publish_edit('create', user)
        return user

    def check_name(self, account_name, user):
        account_name = account_name.lower()
        if user:
            if account_name == user.user_name.lower():
                return
            for player_id in user.player_ids:
                if account_name == player_id.lower():
                    return
        if self.player_exists(account_name) or db.get_index("ix:user:user_name", account_name):
            raise DataError("InUse: {}".format(account_name))

    def player_exists(self, player_id):
        return db.object_exists("player", player_id)

    def _user_connect(self, user, client_data):
        client_data.update({'user_id': user.dbo_id, 'player_ids': user.player_ids, 'displays': user.displays,
                            'password_reset': user.password_reset, 'notifies': user.notifies})

    def _player_connect(self, player, client_data):
        client_data['name'] = player.name
        if player.imm_level:
            client_data['imm_level'] = player.imm_level

    def login_player(self, player):
        ev.dispatch('player_attach', player)
        player.last_login = int(time.time())
        if not player.created:
            player.created = player.last_login
        player.attach()

    def logout_player(self, player):
        player.age += player.last_logout - player.last_login
        player.detach()
        db.save_object(player)
        db.evict_object(player)

    def id_to_name(self, player_id):
        try:
            return player_id.capitalize()
        except AttributeError:
            pass

    def name_to_id(self, player_name):
        return player_name.lower()

    def player_cleanup(self, player_id):
        db.delete_index('ix:player:user', player_id)
        for dbo_id in db.fetch_set_keys('owned:{}'.format(player_id)):
            dbo = db.load_object(dbo_id)
            if dbo and dbo.owner_id == player_id:
                dbo.change_owner()
                db.save_object(dbo)
                edit_update.publish_edit('update', dbo)
        ev.dispatch('player_deleted', player_id)

    def _player_delete(self, player_id):
        player = db.load_object(player_id, "player")
        if player:
            edit_update.publish_edit('delete', player)
            db.delete_object(player)
        else:
            log.warn("Attempting to delete player {} who does not exist.".format(player_id))
        self.player_cleanup(player_id)

