from lampost.di.resource import Injected, module_inject
from lampost.db.registry import get_dbo_class
from lampost.db.exceptions import DataError

from lampost.server.link import LinkRouter, NoRouteError, link_route
from lampost.util.lputil import PermError

log = Injected('log')
db = Injected('datastore')
perm = Injected('perm')
edit_update = Injected('edit_update_service')
module_inject(__name__)


def _reload_holders(holders, session):
    for holder_key in holders:
        holder = db.load_cached(holder_key)
        if holder:
            holder.reload()
        else:
            holder = db.load_object(holder_key)
        if holder:
            db.save_object(holder)
            edit_update.publish_edit('update', holder, session, True)


def _edit_dto(dbo, player):
    dto = dbo.edit_dto
    dto['can_write'] = dbo.can_write(player)
    dto['can_read'] = dbo.can_read(player)
    return dto


class Editor(LinkRouter):
    parent_type = None
    children_types = None

    def __init__(self, key_type, imm_level='builder', create_level=None):
        super().__init__('editor/{}'.format(key_type), imm_level)
        self.key_type = key_type
        self.dbo_class = get_dbo_class(key_type)
        self.imm_level = imm_level
        self.create_level = create_level if create_level else imm_level
        if hasattr(self.dbo_class, 'dbo_children_types'):
            self.children_types = self.dbo_class.dbo_children_types

    def _all_holders(self, dbo_id):
        dbo_key = '{}:{}'.format(self.key_type, dbo_id)
        all_dbo_keys = {dbo_key}
        all_holders = db.dbo_holders(dbo_key, 1)
        if self.children_types:
            for child_type in self.children_types:
                child_keys = db.fetch_set_keys("{}_{}s:{}".format(self.key_type, child_type, dbo_id))
                all_dbo_keys.update(child_keys)
                for child_id in child_keys:
                    all_holders.update(db.dbo_holders('{}:{}'.format(child_type, child_id)))
        return all_holders - all_dbo_keys

    def list(self, player, **_):
        return [_edit_dto(obj, player) for obj in db.load_object_set(self.key_type) if obj.can_read(player)]

    def create(self, session, player, obj_def, **_):
        if not self._permissions(player)['add']:
            raise PermError
        obj_def['owner_id'] = player.dbo_id
        self._pre_create(obj_def, session)
        new_obj = db.create_object(self.key_type, obj_def)
        self._post_create(new_obj, session)
        return edit_update.publish_edit('create', new_obj, session)

    def delete_obj(self, session, player, dbo_id, **_):
        del_obj = db.load_object(dbo_id, self.key_type)
        if not del_obj:
            raise DataError('Gone: Object with key {} does not exist'.format(dbo_id))
        perm.check_perm(player, del_obj)
        self._pre_delete(del_obj, session)
        del_holders = self._all_holders(dbo_id)
        db.delete_object(del_obj)
        self._post_delete(del_obj, session)
        _reload_holders(del_holders, session)
        edit_update.publish_edit('delete', del_obj, session)

    def update(self, session, player, obj_def, **_):
        existing_obj = db.load_object(obj_def['dbo_id'], self.key_type)
        if not existing_obj:
            raise DataError("GONE:  Object with key {} no longer exists.".format(obj_def['dbo.id']))
        perm.check_perm(player, existing_obj)
        self._pre_update(obj_def, existing_obj, session)
        if hasattr(existing_obj, 'change_owner') and obj_def['owner_id'] != existing_obj.owner_id:
            existing_obj.change_owner(obj_def['owner_id'])
        update_holders = db.dbo_holders(existing_obj.dbo_key, 1)
        db.update_object(existing_obj, obj_def)
        self._post_update(existing_obj, session)
        _reload_holders(update_holders, session)
        return edit_update.publish_edit('update', existing_obj, session)

    def metadata(self, player, **_):
        return {'perms': self._permissions(player), 'parent_type': self.parent_type,
                'children_types': self.children_types,
                'new_object': self.dbo_class.new_dto()}

    def test_delete(self, dbo_id, **_):
        return list(self._all_holders(dbo_id))

    def _pre_delete(self, del_obj, session):
        pass

    def _post_delete(self, del_obj, session):
        pass

    def _pre_create(self, obj_def, session):
        pass

    def _post_create(self, new_obj, session):
        pass

    def _pre_update(self, obj_def, existing_obj, session):
        pass

    def _post_update(self, existing_obj, session):
        pass

    def _permissions(self, player):
        return {'add': perm.has_perm(player, self.create_level)}


class ChildrenEditor(Editor):
    def __init__(self, key_type, imm_level='builder'):
        super().__init__(key_type, imm_level)
        self.parent_type = self.dbo_class.dbo_parent_type

    def _pre_create(self, obj_def, session):
        parent_id = obj_def['dbo_id'].split(':')[0]
        parent = db.load_object(parent_id, self.parent_type)
        perm.check_perm(session.player, parent)

    def child_list(self, player, parent_id, **_):
        parent = db.load_object(parent_id, self.parent_type)
        if not parent:
            raise NoRouteError(parent_id)
        if not parent.can_read(player):
            return []
        set_key = '{}_{}s:{}'.format(self.parent_type, self.key_type, parent_id)
        can_write = parent.can_write(player)
        child_list = []
        for child in db.load_object_set(self.key_type, set_key):
            child_dto = child.edit_dto
            child_dto['can_write'] = can_write
            child_list.append(child_dto)
        return child_list
