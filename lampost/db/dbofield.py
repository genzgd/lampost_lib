from threading import local

import collections

from lampost.di.app import on_app_start
from lampost.di.resource import Injected, module_inject
from lampost.meta.auto import AutoField, TemplateField
from lampost.db.registry import get_dbo_class

log = Injected('log')
db = Injected('datastore')
module_inject(__name__)

# This is used to collect child references and temporary template keys while calculating save values,
# rather than attempting to pass this collection recursively
op_status = local()


@on_app_start
def set_base_oid():
    OID.base_oid = db.db_counter('base_oid')


class OID:
    base_oid = 0
    next_oid = 0
    required = False

    @classmethod
    def _force_value(cls, instance):
        try:
            return instance.__dict__['_oid']
        except KeyError:
            cls.next_oid += 1
            return '{}${}'.format(hex(cls.base_oid)[2:], hex(cls.next_oid)[2:])

    @classmethod
    def __get__(cls, instance, owner):
        if instance is None:
            return
        return cls._force_value(instance)

    @classmethod
    def hydrate(cls, instance, dto_repr):
        if dto_repr is None:
            cls._force_value(instance)
        else:
            instance.__dict__['_oid'] = dto_repr

    @classmethod
    def save_value(cls, instance):
        return cls._force_value(instance)

    @classmethod
    def dto_value(cls, instance):
        return cls._force_value(instance)

    @classmethod
    def merge_hidden(cls, instance, dto_repr):
        return dto_repr if dto_repr else cls._force_value(instance)

    @staticmethod
    def capture_oids(instance):
        pass


def oid_class(cls):
    cls.add_dbo_fields({'_oid' : OID})
    return cls


class DBOField(AutoField):
    def __init__(self, default=None, dbo_class_id=None, required=False, editable=True):
        super().__init__(default)
        self.required = required
        self.editable = editable
        self.dbo_class_id = dbo_class_id
        self.cmp_default = json_default(default)

    def _meta_init(self, field):
        self.field = field
        if self.dbo_class_id:
            self._hydrate_func = get_hydrate_func(load_any, self.default, self.dbo_class_id)
            self.dto_value = value_transform(to_dto_repr, self.default, field, for_json=True)
            self.cmp_value = value_transform(to_save_repr, self.default, field)
            self._save_value = value_transform(to_save_repr, self.default, field, for_json=True)
            self.capture_oids = value_exec(capture_oid, self.default, field)
            self.merge_hidden = value_exec(merge_hidden, self.default, field)
        else:
            self._hydrate_func = from_json_func(self.default)
            self.cmp_value = raw_field(field)
            self.dto_value = self._save_value = to_json_func(self.default, field)
            self.merge_hidden = lambda instance, dto_repr:  dto_repr if dto_repr is not None or self.editable else self.save_value(instance)

    def save_value(self, instance):
        value = self._save_value(instance)
        self.check_default(value, instance)
        return value

    def hydrate(self, instance, dto_repr):
        value = self._hydrate_func(instance, dto_repr)
        setattr(instance, self.field, value)
        return value

    @staticmethod
    def capture_oids(instance):
        pass

    def check_default(self, value, instance):
        if hasattr(self.default, 'save_value'):
            if value == self.default.save_value:
                raise KeyError
        elif value == self.cmp_default:
            raise KeyError


class DBOTField:
    """
    This class always passes access to the template.  It also provides a blueprint to auto generate the appropriate
    DBO fields in the Template class.

    Fields that are initialized in the Template but whose values can be overridden by the instance should be declared
    as a DBOField in the template class and a DBOCField field in the instance class with identical names
    """

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        return getattr(instance.template, self.field)

    def __set__(self, instance, value):
        log.error("Illegally setting value {} of DBOTField {}", value, self.field, stack_info=True)

    def _meta_init(self, field):
        self.field = field


class DBOCField(DBOField, TemplateField):
    """
    This class should be used in cloneable objects or templates.  It will pass access to the original object if
    its value is not overridden in the child object.
    """

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        super().__init__(*args, **kwargs)

    def check_default(self, value, instance):
        if self.field not in instance.__dict__:
            raise KeyError
        try:
            template_value = getattr(instance.template, self.field)
            if hasattr(template_value, 'cmp_value'):
                if value == template_value.cmp_value:
                    raise KeyError
            elif value == template_value:
                raise KeyError
        except AttributeError:
            pass
        super().check_default(value, instance)


class DBOLField(DBOField):
    """
    This class should be used for database references where the value is used only for a short time, such
    as initializing the holder.  It 'lazy loads' the database object when the descriptor __get__ is called,
    so no database access is made if the field is never 'read', and the database object will be freed from the
    db cache on garbage collection if any reads have since gone out of scope

    Sets are not supported to simplify transforms to JSON
    """

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        try:
            value = instance.__dict__[self.field]
        except KeyError:
            value = self._get_default(instance)
        return self._hydrate_func(instance, value)

    def __set__(self, instance, value):
        if value == self.default:
            instance.__dict__.pop(self.field, None)
        else:
            instance.__dict__[self.field] = self._set_value(value)

    def hydrate(self, instance, dto_repr):
        instance.__dict__[self.field] = dto_repr
        return dto_repr

    def cmp_value(self, instance):
        return instance.__dict__.get(self.field, self.default)

    def dto_value(self, instance):
        return instance.__dict__.get(self.field, self.default)

    def _save_value(self, instance):
        return self._save_ref(instance, instance.__dict__.get(self.field, self.default))

    def _meta_init(self, field):
        self.field = field
        self._hydrate_func = get_hydrate_func(load_keyed, self.default, self.dbo_class_id)
        self._save_ref = get_hydrate_func(save_keyed, self.default, self.dbo_class_id)
        self._set_value = set_transform(to_dto_repr, self.default, self.dbo_class_id)


def raw_field(field):
    return lambda instance: getattr(instance, field)


def get_hydrate_func(load_func, default, class_id):
    if isinstance(default, set):
        return lambda instance, dto_repr_list: {dbo for dbo in (load_func(class_id, instance, dto_repr) for
                                                                dto_repr in dto_repr_list) if dbo is not None}
    if isinstance(default, collections.Sequence):
        field_class = default.__class__
        return lambda instance, dto_repr_list: field_class(dbo for dbo in (load_func(class_id, instance, dto_repr) for
                                                                dto_repr in dto_repr_list) if dbo is not None)
    if isinstance(default, dict):
        return lambda instance, dto_repr_dict: {key: dbo for key, dbo in ((key, load_func(class_id, instance, dto_repr))
                                                                          for key, dto_repr in dto_repr_dict.items()) if
                                                dbo is not None}
    return lambda instance, dto_repr: load_func(class_id, instance, dto_repr)


def from_json_func(default):
    def _identity(instance, dto_repr):
        return dto_repr
    if default is None or isinstance(default, (collections.Mapping, str)):
        return _identity
    if isinstance(default, collections.Sequence):
        field_class = default.__class__
        return lambda instance, dto_repr: field_class(value for value in dto_repr)
    return _identity


def to_json_func(default, field):
    if default is None or isinstance(default, (collections.Mapping, str)):
        return raw_field(field)
    if isinstance(default, collections.MutableSequence):
        return lambda instance: [value for value in getattr(instance, field)]
    return raw_field(field)


def json_default(default):
    if isinstance(default, collections.MutableSequence):
        return [value for value in default]
    return default


def value_transform(trans_func, default, field, for_json=False):
    if isinstance(default, dict):
        return lambda instance, *exec_args: {key: res for key, res in ((key, trans_func(value, *exec_args)) \
            for key, value in getattr(instance, field).items()) if res is not None}
    if isinstance(default, collections.MutableSequence):
        field_class = [] if for_json else default.__class__
        return lambda instance, *exec_args: field_class(res for res in (trans_func(value, *exec_args) \
            for value in getattr(instance, field)) if res is not None)
    return lambda instance, *exec_args: trans_func(getattr(instance, field), *exec_args)


def value_exec(exec_func, default, field):
    if isinstance(default, dict):
        def _exec_values(instance, *exec_args):
            for instance in getattr(instance, field).values():
                exec_func(instance, *exec_args)
        return _exec_values
    if isinstance(default, collections.MutableSequence):
        def _exec_items(instance, *exec_args):
            for value in getattr(instance, field):
                exec_func(value, *exec_args)
        return _exec_items
    return lambda instance, *exec_args: exec_func(getattr(instance, field), *exec_args)


def capture_oid(dbo):
    if not hasattr(dbo, 'dbo_id'):
        try:
            op_status.update_refs[dbo.__dict__['_oid']] = dbo
        except KeyError:
            pass
        dbo.capture_oids()


def set_transform(trans_func, default, class_id):
    if isinstance(default, collections.MutableSequence):
        field_class = default.__class__
        return lambda values: field_class([trans_func(value, class_id) for value in values])
    if isinstance(default, collections.Mapping):
        return lambda value_dict: {key: trans_func(value, class_id) for key, value in value_dict}
    return lambda value: trans_func(value, class_id)


def to_dto_repr(dbo, class_id):
    if hasattr(dbo, 'dbo_id'):
        return dbo.dbo_key if class_id == 'untyped' else dbo.dbo_id
    try:
        dto_value = dbo.dto_value
    except AttributeError:
        return None
    if hasattr(dbo, 'template_key'):
        dto_value['tk'] = dbo.template_key
    elif getattr(dbo, 'class_id', class_id) != class_id:
        # If the object has a different class_id than field definition thinks it should have
        # we need to save the actual class_id
        dto_value['class_id'] = dbo.class_id
    return dto_value


def to_save_repr(dbo, class_id):
    if hasattr(dbo, 'dbo_id'):
        op_status.save_value_refs.append(dbo.dbo_key)
        return dbo.dbo_key if class_id == 'untyped' else dbo.dbo_id
    try:
        save_value = dbo.save_value
    except AttributeError:
        return None
    if hasattr(dbo, 'template_key'):
        save_value['tk'] = dbo.template_key
        op_status.save_value_refs.append(dbo.template_key)
    elif getattr(dbo, 'class_id', class_id) != class_id:
        # If the object has a different class_id than field definition thinks it should have
        # we need to save the actual class_id
        save_value['class_id'] = dbo.class_id
    return save_value


def merge_hidden(dbo, dto_repr):
    if hasattr(dbo, 'dbo_id'):
        return dto_repr
    return dbo.merge_hidden(dto_repr)


def to_dbo_key(dbo, class_id):
    try:
        return dbo.dbo_key if class_id == 'untyped' else dbo.dbo_id
    except AttributeError:
        return dbo


def load_keyed(class_id, dbo_owner, dbo_id):
    if dbo_id:
        return db.load_object(dbo_id, class_id if class_id != "untyped" else None)


def save_keyed(class_id, dbo_owner, dto_repr):
    if class_id == 'untyped':
        op_status.save_value_refs.append(dto_repr)
    else:
        op_status.save_value_refs.append('{}:{}'.format(class_id, dto_repr))
    return dto_repr


def load_any(class_id, dbo_owner, dto_repr):
    if not dto_repr:
        return None

    dbo_ref_id = None
    try:
        # The class_id passed in is what the field thinks it should hold
        # This can be overridden in the actual stored dictionary
        class_id = dto_repr['class_id']
    except TypeError:
        # A dto_repr is either a string or a dictionary.  If it's a string,
        # it must be reference, so capture the reference id
        dbo_ref_id = dto_repr
    except KeyError:
        pass

    dbo_class = get_dbo_class(class_id)
    if not dbo_class:
        log.error('Unable to load reference for {}', class_id)
        return None

    # If this class has a key_type, it should always be a reference and we should load it from the database
    # The dto_representation in this case should always be a dbo_id
    if hasattr(dbo_class, 'dbo_key_type'):
        return db.load_object(dbo_ref_id, dbo_class)

    # If we still have a dbo_ref_id, this must be part of an untyped collection, so the dbo_ref_id includes
    # both the class name and dbo_id and we should be able to load it
    if dbo_ref_id:
        return db.load_object(dbo_ref_id)

    # If we have an update reference, we already have the dbo object, and it just needs to be rehydrated
    if hasattr(op_status, 'update_refs'):
        orig_dbo = op_status.update_refs.get(dto_repr.get('_oid'))
        if orig_dbo:
            op_status.refs_used.add(orig_dbo)
            orig_dbo.hydrate(dto_repr)
            return orig_dbo

    # If this is a template, it should have a template key, so we load the template from the database using
    # the full key, then hydrate any non-template fields from the dictionary
    template_key = dto_repr.get('tk')
    if template_key:
        template = db.load_object(template_key)
        if template:
            instance = template.get_instance(dbo_owner).hydrate(dto_repr)
            template.config_instance(instance)
            return instance
        log.warn("Missing template for template_key {} owner {}", template_key, dbo_owner.dbo_id)
        return None

    # Finally, it's not a template and it is not a reference to an independent DB object, it must be a pure child
    # object of this class, just set the owner and hydrate it
    instance = dbo_class()
    instance.dbo_owner = dbo_owner
    return instance.hydrate(dto_repr)
