from lampost.db import redisstore, permissions, dbconfig
from lampost.di import resource, config
from lampost.user import manage
from lampost.user.model import User
from lampost.util import json
from lampost.util.encrypt import make_hash

log = resource.get_resource('log').factory('setup')
json.select_json()


def init_db(args):
    db = resource.register('datastore', redisstore.RedisStore(args.db_host, args.db_port, args.db_num, args.db_pw))
    if args.flush:
        db_num = db.pool.connection_kwargs['db']
        if db_num == args.db_num:
            log.info("Flushing database {}", db_num)
            db.redis.flushdb()
        else:
            print("Error:  DB Numbers do not match")
            return


def import_config(args):
    db = resource.get_resource('datastore')
    db_config = db.load_object(args.config_id, 'config')
    if db_config:
        raise RuntimeError("Error:  This instance is already set up")

    config_yaml = config.load_yaml(args.config_dir)
    db_config = dbconfig.create(args.config_id, config_yaml, True)
    config.activate(db_config.section_values)


def create_root_user(args, player_data):
    db = resource.get_resource('datastore')
    user_dto = {'dbo_id': db.db_counter('user_id'),
                'user_name': args.imm_account,
                'password': make_hash(args.imm_password)}
    user = db.create_object(User, user_dto)
    player = manage.create_player(user, player_data)
    permissions.update_immortal_list(player)
