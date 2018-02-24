from lampost.di.resource import Injected, module_inject
from lampost.meta.core import CoreMeta
from lampost.util.classes import call_mro, cls_name
from lampost.db import dbofield
from lampost.db.registry import set_dbo_class, get_dbo_class
from lampost.db.dbofield import DBOField

log = Injected('log')
perm = Injected('perm')
db = Injected('datastore')
module_inject(__name__)


class DBOAspect(metaclass=CoreMeta):
    dbo_fields = {}

    @classmethod
    def _cls_init(cls, class_name, bases, new_attrs):
        if 'class_id' in new_attrs:
            # Override any existing class id reference with this child class
            set_dbo_class(cls.class_id, cls)

        cls._update(bases, 'dbo_fields')
        cls._update_dbo_fields(new_attrs)

    @classmethod
    def _update_dbo_fields(cls, new_attrs):
        for name, attr in new_attrs.items():
            if hasattr(attr, 'hydrate'):
                old_attr = cls.dbo_fields.get(name)
                if old_attr == attr:
                    log.warn("Overriding duplicate attr {} in class {}", name, cls.__name__)
                else:
                    if old_attr and old_attr.default != attr.default:
                        log.info("Overriding default value of attr {} in class {}", name, cls.__name__)
                    cls.dbo_fields[name] = attr

    @classmethod
    def add_dbo_fields(cls, new_fields):
        cls._meta_init_attrs(new_fields)
        cls._update_dbo_fields(new_fields)
        for name, dbo_field in new_fields.items():
            setattr(cls, name, dbo_field)


class CoreDBO(DBOAspect):
    dbo_owner = None

    def on_loaded(self):
        call_mro(self, '_on_loaded')

    def hydrate(self, dto):
        missing_fields = []
        for field, dbo_field in self.dbo_fields.items():
            if field in dto:
                dbo_value = dbo_field.hydrate(self, dto[field])
            else:
                dbo_value = None
                try:
                    delattr(self, field)
                except AttributeError:
                    pass
            if not dbo_value and dbo_field.required:
                missing_fields.append(field)
        if missing_fields:
            log.warn("Missing required fields {} in class {} dto {}", ', '.join(missing_fields),
                     cls_name(self.__class__), dto)
            return None
        self.on_loaded()
        return self

    def clone(self):
        clone = self.__class__()
        if hasattr(self, 'dbo_id'):
            setattr(clone, 'dbo_id', self.dbo_id)
        clone.template = self
        clone.on_loaded()
        return clone

    def reload(self):
        call_mro(self, '_pre_update')
        self.hydrate(self.save_value)

    def update(self, dto=None):
        call_mro(self, 'pre_update')
        self.hydrate(dto if dto else self.save_value)
        db.save_object(self)

    @property
    def save_value(self):
        save_value = {}
        for field, dbo_field in self.dbo_fields.items():
            try:
                save_value[field] = dbo_field.save_value(self)
            except KeyError:
                continue
        if hasattr(self, 'template_key'):
            save_value['tk'] = self.template_key
        return save_value

    def describe(self):
        return self._describe([], 0)

    @property
    def dto_value(self):
        return {field: dbo_field.dto_value(self) for field, dbo_field in self.dbo_fields.items()}

    @property
    def cmp_value(self):
        cmp_value = {field: dbo_field.cmp_value(self) for field, dbo_field in self.dbo_fields.items()}
        return self.metafields(cmp_value, ['dbo_key_type', 'class_id', 'template_key'])

    @property
    def edit_dto(self):
        return self.metafields(self.dto_value, ['class_id'])

    def metafields(self, dto_repr, field_names):
        for metafield in field_names:
            try:
                dto_repr[metafield] = getattr(self, metafield)
            except AttributeError:
                pass
        return dto_repr

    def _describe(self, display, level):
        if level > 2:
            return

        def append(value, key):
            display.append(4 * level * "&nbsp;" + key + ":" + (16 - len(key)) * "&nbsp;" + str(value))

        for attr in ['class_id', 'dbo_key_type', 'dbo_id', 'template_key']:
            if hasattr(self, attr):
                append(getattr(self, attr), attr)
        for field, dbo_field in sorted(self.dbo_fields.items(), key=lambda field_value: field_value[0]):
            try:
                append(dbo_field.dto_value(self), field)
            except KeyError:
                pass

        return display


class SystemDBO(DBOAspect):
    def can_read(self, immortal):
        return True

    def can_write(self, immortal):
        return perm.is_supreme(immortal) or immortal.imm_level > getattr(self, 'imm_level', 0)


class OwnerDBO(DBOAspect):
    owner_id = DBOField('lampost')
    read_access = DBOField(0)
    write_access = DBOField(0)

    @property
    def imm_level(self):
        try:
            return perm.immortals[self.owner_id] + 1
        except KeyError:
            return perm.perm_to_level('admin')

    def _on_db_created(self):
        log.info("{} created new object {}", self.owner_id, self.dbo_key)
        db.add_set_key('owned:{}'.format(self.owner_id), self.dbo_key)

    def _on_db_deleted(self):
        db.delete_set_key('owned:{}'.format(self.owner_id), self.dbo_key)

    def can_read(self, immortal):
        return immortal.imm_level >= self.read_access

    def can_write(self, immortal):
        if perm.is_supreme(immortal) or immortal.dbo_id == self.owner_id:
            return True
        if self.write_access:
            return immortal.imm_level >= self.write_access
        return immortal.imm_level >= self.imm_level

    def change_owner(self, new_owner=None):
        self._on_db_deleted()
        self.owner_id = new_owner or 'lampost'
        self._on_db_created()


class KeyDBO(CoreDBO):
    dbo_id = None
    dbo_key_type = None
    dbo_key_sort = None
    dbo_indexes = ()
    dbo_children_types = ()

    dbo_ts = DBOField(0)

    @classmethod
    def _mixin_init(cls, name, bases, new_attrs):
        if 'dbo_key_type' in new_attrs:
            # Override or set the class_id to the database key if present
            cls.class_id = cls.dbo_key_type
            set_dbo_class(cls.class_id, cls)

    @classmethod
    def new_dto(cls):
        new_dbo = cls()
        dto = new_dbo.dto_value
        dto['can_write'] = True
        return new_dbo.metafields(dto, ['class_id', 'dbo_key_type', 'dbo_parent_type', 'dbo_children_types'])

    @property
    def dbo_key(self):
        return ":".join([self.dbo_key_type, self.dbo_id])

    @property
    def edit_dto(self):
        return self.metafields(self.dto_value, ['dbo_id', 'dbo_key', 'class_id',  'dbo_key_type', 'imm_level'])

    @property
    def save_value(self):
        dbofield.save_value_refs.current = []
        save_value = super().save_value
        if getattr(self, 'class_id', self.dbo_key_type) != self.dbo_key_type:
            save_value['class_id'] = self.class_id
        return save_value

    def db_created(self):
        call_mro(self, '_on_db_created')

    def db_deleted(self):
        call_mro(self, '_on_db_deleted')

    def autosave(self):
        db.save_object(self, autosave=True)

    def to_db_value(self):
        return self.save_value, dbofield.save_value_refs.current


class ParentDBO(KeyDBO, OwnerDBO):

    @property
    def edit_dto(self):
        dto = self.dto_value
        for child_type in self.dbo_children_types:
            dto['{}_list'.format(child_type)] = self.dbo_child_keys(child_type)
        return self.metafields(dto, ['dbo_id', 'dbo_key', 'class_id', 'dbo_key_type', 'dbo_children_types'])

    def dbo_child_keys(self, child_type):
        child_class = get_dbo_class(child_type)
        return sorted(db.fetch_set_keys("{}_{}s:{}".format(self.dbo_key_type, child_type, self.dbo_id)),
                      key=child_class.dbo_key_sort)


class ChildDBO(KeyDBO):
    dbo_parent_type = None

    @property
    def parent_id(self):
        return self.dbo_id.split(':')[0]

    @property
    def child_id(self):
        return self.dbo_id.split(':')[1]

    @property
    def parent_dbo(self):
        return db.load_object(self.parent_id, self.dbo_parent_type)

    @property
    def dbo_set_key(self):
        return "{}_{}s:{}".format(self.dbo_parent_type, self.dbo_key_type, self.parent_id)

    @property
    def edit_dto(self):
        return self.metafields(self.dto_value, ['dbo_id', 'dbo_key', 'class_id',  'dbo_key_type', 'dbo_parent_type'])

    @property
    def imm_level(self):
        return self.parent_dbo.imm_level

    def can_read(self, immortal):
        return self.parent_dbo.can_read(immortal)

    def can_write(self, immortal):
        return self.parent_dbo.can_write(immortal)


#  This class is here to catch possible errors in 'untyped' collections
class Untyped():
    def hydrate(self, dto_repr):
        # This should never get called, as 'untyped' fields should always hold
        # templates or actual dbo_references with saved class_ids.
        log.warn("Attempting to hydrate invalid dto {}", dto_repr)


set_dbo_class('untyped', Untyped)
