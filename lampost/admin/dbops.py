import time

from lampost.admin.ops import admin_op
from lampost.db import dbconfig
from lampost.db.exceptions import DataError
from lampost.db.registry import get_dbo_class, _dbo_registry, get_mixed_type
from lampost.di.config import load_yaml, activate
from lampost.di.resource import Injected, module_inject

log = Injected('log')
db = Injected('datastore')
perm = Injected('perm')
module_inject(__name__)


@admin_op
def rebuild_indexes(class_id):
    dbo_cls = get_dbo_class(class_id)
    if not dbo_cls:
        raise DataError("Class not found")
    for ix_name in dbo_cls.dbo_indexes:
        db.delete_key('ix:{}:{}'.format(dbo_cls.dbo_key_type, ix_name))
    for dbo_id in db.fetch_set_keys(dbo_cls.dbo_set_key):
        try:
            dbo_key = '{}:{}'.format(dbo_cls.dbo_key_type, dbo_id)
            dbo_dict = db.load_value(dbo_key)
            for ix_name in dbo_cls.dbo_indexes:
                ix_value = dbo_dict.get(ix_name)
                if ix_value is not None and ix_value != '':
                    db.set_index('ix:{}:{}'.format(dbo_cls.dbo_key_type, ix_name), ix_value, dbo_id)
        except (ValueError, TypeError):
            log.warn("Missing dbo object {} from set key {}", dbo_id, dbo_cls.dbo_set_key)


@admin_op
def purge_invalid(confirm='no'):

    start_time = time.time()
    total = 0
    purged = 0

    execute = confirm == 'confirm'

    def purge(purge_cls, set_key=None):
        nonlocal purged, total

        for dbo_id in db.fetch_set_keys(set_key):
            total += 1
            dbo_key = ':'.join((purge_cls.dbo_key_type, dbo_id))
            dbo_dict = db.load_value(dbo_key)
            if dbo_dict is None:
                purged += 1
                log.warn("Missing value for key {}", dbo_key)
                if execute:
                    db.delete_set_key(set_key, dbo_id)
            else:
                dbo = get_mixed_type(purge_cls.dbo_key_type, dbo_dict.get('mixins'))()
                dbo.dbo_id = dbo_id
                if not dbo.hydrate(dbo_dict):
                    purged += 1
                    if execute:
                        db.delete_object(dbo)
                for child_type in getattr(dbo_cls, 'dbo_children_types', ()):
                    purge(get_dbo_class(child_type), '{}_{}s:{}'.format(dbo_key_type, child_type, dbo_id))

    for dbo_cls in _dbo_registry.values():
        dbo_key_type = getattr(dbo_cls, 'dbo_key_type', None)
        if dbo_key_type and not hasattr(dbo_cls, 'dbo_parent_type'):
            purge(dbo_cls, dbo_cls.dbo_set_key)

    return "{} of {} objects purged in {} seconds".format(purged, total, time.time() - start_time)


@admin_op
def rebuild_owner_refs():
    # Yes, we're abusing the keys command.  If we required a later version of Redis (2.8) we could use SCAN
    for owned_key in db.redis.keys('owned:*'):
        db.delete_key(owned_key)
    for dbo_cls in _dbo_registry.values():
        dbo_key_type = getattr(dbo_cls, 'dbo_key_type', None)
        if not dbo_key_type:
            continue
        owner_field = dbo_cls.dbo_fields.get('owner_id', None)
        if not owner_field:
            continue
        for dbo in db.load_object_set(dbo_cls):
            if dbo.owner_id in perm.immortals:
                dbo.db_created()
            else:
                log.warn("owner id {} not found, setting owner of {} to default {}", dbo.owner_id, dbo.dbo_id,
                         owner_field.default)
                dbo.change_owner()


@admin_op
def rebuild_immortal_list():
    db.delete_key('immortals')
    for player in db.load_object_set('player'):
        if player.imm_level:
            db.set_db_hash('immortals', player.dbo_id, player.imm_level)


@admin_op
def rebuild_all_fks():
    start_time = time.time()
    updated = 0

    def update(update_cls, set_key=None):
        nonlocal updated
        for dbo in db.load_object_set(update_cls, set_key):
            db.save_object(dbo)
            updated += 1
            for child_type in getattr(dbo_cls, 'dbo_children_types', ()):
                update(get_dbo_class(child_type), '{}_{}s:{}'.format(dbo_key_type, child_type, dbo.dbo_id))

    for holder_key in db.redis.keys('*:holders'):
        db.delete_key(holder_key)
    for ref_key in db.redis.keys('*:refs'):
        db.delete_key(ref_key)
    for dbo_cls in _dbo_registry.values():
        dbo_key_type = getattr(dbo_cls, 'dbo_key_type', None)
        if dbo_key_type and not hasattr(dbo_cls, 'dbo_parent_type'):
            update(dbo_cls)

    return "{} objects updated in {} seconds".format(updated, time.time() - start_time)


@admin_op
def restore_db_from_yaml(config_id='lampost', path='conf', force="no"):
    yaml_config = load_yaml(path)
    existing = db.load_object(config_id, 'config')
    if existing:
        if force != 'yes':
            return "Object exists and force is not 'yes'"
        db.delete_object(existing)
    try:
        db_config = dbconfig.create(config_id, yaml_config, True)
    except Exception as exp:
        log.exception("Failed to create configuration from yaml", exc_info=True)
        db.save_object(existing)
        return "Exception creating configuration from yaml."
    activate(db_config.section_values)
    return 'Config {} successfully loaded from yaml files'.format(config_id)

