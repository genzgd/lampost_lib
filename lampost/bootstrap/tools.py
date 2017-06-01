import logging

from lampost.di import resource, config
from lampost.db.redisstore import RedisStore
from lampost.db import dbconfig
from lampost.util.logging import LogFactory
from lampost.util import json

resource.register('log', LogFactory())
json.select_json()
log = logging.getLogger(__name__)


def reload_config(args):
    db = RedisStore(args.db_host, args.db_port, args.db_num, args.db_pw)
    resource.register('datastore', db)
    config_id = args.config_id
    existing = db.load_object(config_id, dbconfig.Config)
    if not existing:
        print("Existing configuration does not exist, try lampost_setup")
        return
    db.delete_object(existing)

    try:
        config_yaml = config.load_yaml(args.config_dir)
        if not config_yaml:
            print("No yaml found.  Confirm config/working directory?")
            return
        db_config = dbconfig.create(config_id, config_yaml, True)
    except Exception:
        log.exception("Failed to create configuration from yaml")
        db.save_object(existing)
        print("Exception creating configuration from yaml.")
        return
    config.activate(db_config.section_values)
    print('Config {} successfully reloaded from yaml files'.format(config_id))
