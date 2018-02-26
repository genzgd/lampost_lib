from lampost.di.resource import Injected, module_inject
from lampost.meta.auto import AutoField
from lampost.meta.core import CoreMeta
from lampost.util.classes import call_mro

log = Injected('log')
ev = Injected('dispatcher')
module_inject(__name__)


class Attachable(metaclass=CoreMeta):
    attached = AutoField(False)

    def attach(self):
        if not self.attached:
            self.attached = True
            call_mro(self, '_on_attach')
        return self

    def detach(self):
        if self.attached:
            self._detach()
        else:
            log.warn("Detaching already detached obj: {}", self)

    def _detach(self):
        ev.detach_events(self)
        call_mro(self, '_on_detach')
        self.attached = False

    def _pre_reload(self):
        if self.attached:
            self._detach()

    def _on_db_deleted(self):
        if self.attached:
            self._detach()
