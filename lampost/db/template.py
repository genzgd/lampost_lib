import inspect
import logging
from weakref import WeakSet

from lampost.db.dbo import CoreDBO
from lampost.meta.auto import AutoField
from lampost.meta.core import CoreMeta
from lampost.db.registry import get_dbo_class, set_instance_class
from lampost.db.dbofield import DBOField, DBOTField, DBOCField, oid_class
from lampost.util.classes import call_mro

log = logging.getLogger(__name__)


class Template(metaclass=CoreMeta):
    instance_cls = None
    _instances = AutoField(WeakSet())

    def _on_loaded(self):
        for instance in self._instances:
            instance.on_loaded()

    def _on_db_deleted(self):
        for instance in self._instances:
            call_mro('_on_db_deleted', instance)

    def create_instance(self, dbo_owner):
        instance = self.get_instance(dbo_owner)
        instance.on_loaded()
        self.config_instance(instance)
        return instance

    def get_instance(self, dbo_owner):
        instance = self.instance_cls()
        instance.template = self
        instance.template_key = self.dbo_key
        instance.dbo_owner = dbo_owner
        self._instances.add(instance)
        return instance

    def config_instance(self, instance):
        pass


@oid_class
class TemplateInstance(CoreDBO):
    template = None

    @classmethod
    def _mixin_init(cls, *_):
        template_id = getattr(cls, "template_id", None)
        if not template_id:
            return
        set_instance_class(template_id, cls)
        template_cls = get_dbo_class(template_id)
        old_class = getattr(template_cls, 'instance_cls', None)
        if old_class:
            log.info("Overriding existing instance class {} with {} for template {}", old_class.__name__, cls.__name__,
                     template_id)
        else:
            log.info("Initializing instance class {} for template {}", cls.__name__, template_id)
        new_dbo_fields = {name: DBOField(*field.args, **field.kwargs) for name, field in inspect.getmembers(cls)
                          if isinstance(field, (DBOTField, DBOCField))}
        template_cls.add_dbo_fields(new_dbo_fields)
        template_cls.instance_cls = cls
        cls.template_cls = template_cls
