from lampost.di.resource import Injected, module_inject
from lampost.meta.auto import AutoField
from lampost.meta.core import CoreMeta
from lampost.util.classes import call_mro

ev = Injected('dispatcher')
module_inject(__name__)


class Attachable(metaclass=CoreMeta):
    attached = AutoField(False)

    def attach(self):
        if not self.attached:
            call_mro(self, '_on_attach')
            self.attached = True

    def detach(self):
        ev.detach_events(self)
        call_mro(self, '_on_detach')
        self.attached = False
