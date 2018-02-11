from importlib import import_module

from lampost.event.dispatcher import PulseDispatcher
from lampost.util import json
from lampost.di import resource, config, app
from lampost.db import redisstore, permissions, dbconfig
from lampost.server import user as user_manager

log = resource.get_resource('log').factory('setup')


def new_setup(args):
    json.select_json()

    db = resource.register('datastore', redisstore.RedisStore(args.db_host, args.db_port, args.db_num, args.db_pw))
    if args.flush:
        db_num = db.pool.connection_kwargs['db']
        if db_num == args.db_num:
            log.info("Flushing database {}", db_num)
            db.redis.flushdb()
        else:
            print("Error:  DB Numbers do not match")
            return

    db_config = db.load_object(args.config_id, 'config')
    if db_config:
        print("Error:  This instance is already set up")
        return

    # Load config yaml files and create the database configuration
    config_yaml = config.load_yaml(args.config_dir)
    db_config = dbconfig.create(args.config_id, config_yaml, True)
    config.activate(db_config.section_values)

    # Initialize core services needed by the reset of the setup process
    resource.register('dispatcher', PulseDispatcher())
    resource.register('perm', permissions)
    um = resource.register('user_manager', user_manager)
    resource.register('edit_update_service', SetupEditUpdate)
    app_setup = import_module('{}.newsetup'.format(args.app_id))

    first_player = app_setup.first_time_setup(args, db)
    user = um.create_user(args.imm_account, args.imm_password)
    player = um.attach_player(user, first_player)
    db.set_db_hash('immortals', player.dbo_id, player.imm_level)


class SetupEditUpdate:
    @classmethod
    def publish_edit(cls, edit_type, edit_obj, *_):
        log.info('Edit:  type: {}  obj: "{}"', edit_type, edit_obj.dbo_key)
