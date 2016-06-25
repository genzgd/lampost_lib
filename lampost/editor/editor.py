from lampost.di.resource import Injected, module_inject
from lampost.db.registry import get_dbo_class
from lampost.db.exceptions import DataError
from lampost.server.handlers import MethodHandler, SessionHandler
from lampost.util.lputil import PermError

log = Injected('log')
db = Injected('datastore')
perm = Injected('perm')
edit_update = Injected('edit_update_service')
module_inject(__name__)


class Editor(MethodHandler):
    parent_type = None
    children_types = None

    def _reload_holders(self, dbo):
        for holder_key in db.all_holders(dbo.dbo_key):
            holder = db.load_cached(holder_key)
            if holder:
                holder.reload()
            else:
                holder = db.load_object(holder_key)
            if holder:
                db.save_object(holder)
                edit_update.publish_edit('update', holder, self.session, True)

    def prepare(self):
        super().prepare()
        perm.check_perm(self.player, self)

    def initialize(self, key_type, imm_level='builder', create_level=None):
        self.key_type = key_type
        self.obj_class = get_dbo_class(key_type)
        self.imm_level = imm_level
        self.create_level = create_level if create_level else imm_level
        if hasattr(self.obj_class, 'dbo_children_types'):
            self.children_types = self.obj_class.dbo_children_types

    def list(self):
        return [self._edit_dto(obj) for obj in db.load_object_set(self.key_type) if obj.can_read(self.player)]

    def create(self):
        if not self._permissions()['add']:
            raise PermError
        self.raw['owner_id'] = self.session.player.dbo_id
        self._pre_create()
        new_obj = db.create_object(self.key_type, self.raw)
        self._post_create(new_obj)
        return edit_update.publish_edit('create', new_obj, self.session)

    def delete_obj(self):
        del_obj = db.load_object(self.raw['dbo_id'], self.key_type)
        if not del_obj:
            raise DataError('Gone: Object with key {} does not exist'.format(self.raw['dbo_id']))
        perm.check_perm(self.player, del_obj)
        self._pre_delete(del_obj)
        db.delete_object(del_obj)
        self._reload_holders(del_obj)
        self._post_delete(del_obj)
        edit_update.publish_edit('delete', del_obj, self.session)

    def update(self):
        existing_obj = db.load_object(self.raw['dbo_id'], self.key_type)
        if not existing_obj:
            raise DataError("GONE:  Object with key {} no longer exists.".format(self.raw['dbo.id']))
        perm.check_perm(self.player, existing_obj)
        self._pre_update(existing_obj)
        if hasattr(existing_obj, 'change_owner') and self.raw['owner_id'] != existing_obj.owner_id:
            existing_obj.change_owner(self.raw['owner_id'])
        db.update_object(existing_obj, self.raw)
        self._post_update(existing_obj)
        self._reload_holders(existing_obj)
        return edit_update.publish_edit('update', existing_obj, self.session)

    def metadata(self):
        return {'perms': self._permissions(), 'parent_type': self.parent_type, 'children_types': self.children_types,
                'new_object': self.obj_class.new_dto()}

    def test_delete(self):
        return list(db.fetch_set_keys('{}:{}:holders'.format(self.key_type, self.raw['dbo_id'])))

    def _edit_dto(self, dbo):
        dto = dbo.edit_dto
        dto['can_write'] = dbo.can_write(self.player)
        dto['can_read'] = dbo.can_read(self.player)
        return dto

    def _pre_delete(self, del_obj):
        pass

    def _post_delete(self, del_obj):
        pass

    def _pre_create(self):
        pass

    def _post_create(self, new_obj):
        pass

    def _pre_update(self, existing_obj):
        pass

    def _post_update(self, existing_obj):
        pass

    def _permissions(self):
        return {'add': perm.has_perm(self.player, self.create_level)}


class ChildList(SessionHandler):
    def initialize(self, key_type):
        self.key_type = key_type
        self.obj_class = get_dbo_class(key_type)
        self.parent_type = self.obj_class.dbo_parent_type

    def main(self, parent_id):
        parent = db.load_object(parent_id, self.parent_type)
        if not parent:
            self.send_error(404)
        if not parent.can_read(self.player):
            return []
        set_key = '{}_{}s:{}'.format(self.parent_type, self.key_type, parent_id)
        can_write = parent.can_write(self.player)
        child_list = []
        for child in db.load_object_set(self.key_type, set_key):
            child_dto = child.edit_dto
            child_dto['can_write'] = can_write
            child_list.append(child_dto)
        self._return(child_list)


class ChildrenEditor(Editor):
    def initialize(self, key_type, imm_level='builder'):
        super().initialize(key_type, imm_level)
        self.parent_type = self.obj_class.dbo_parent_type

    def _pre_create(self):
        parent_id = self.raw['dbo_id'].split(':')[0]
        parent = db.load_object(parent_id, self.parent_type)
        perm.check_perm(self.player, parent)
