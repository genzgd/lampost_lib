from collections import defaultdict
from random import randint

from lampost.di.resource import Injected, module_inject
from lampost.event.registration import Registration, PulseRegistration

log = Injected('log')
module_inject(__name__)


class Dispatcher:
    def __init__(self):
        self._owner_map = defaultdict(set)
        self._registrations = defaultdict(set)

    def register(self, event_type, callback, owner=None, priority=0):
        return self._add_registration(Registration(event_type, callback, owner, priority))

    def unregister(self, registration):
        registration.cancel()
        owner_registrations = self._owner_map[registration.owner]
        owner_registrations.remove(registration)
        if not owner_registrations:
            del self._owner_map[registration.owner]
        event_registrations = self._registrations.get(registration.event_type)
        event_registrations.remove(registration)
        if not event_registrations:
            del self._registrations[registration.event_type]
        registration.owner = None
        registration.callback = None

    def unregister_type(self, owner, event_type):
        for registration in self._owner_map[owner].copy():
            if registration.event_type == event_type:
                self.unregister(registration)

    def dispatch(self, event_type, *args, **kwargs):
        sorted_events = sorted(self._registrations.get(event_type, []), key=lambda reg: reg.priority)
        for registration in sorted_events:
            try:
                registration.callback(*args, **kwargs)
            except Exception:
                log.exception("Dispatch Error", exc_info=True)

    def detach_events(self, owner):
        if owner in self._owner_map:
            for registration in self._owner_map[owner].copy():
                self.unregister(registration)

    def _add_registration(self, registration):
        self._registrations[registration.event_type].add(registration)
        self._owner_map[registration.owner].add(registration)
        return registration


class PulseDispatcher(Dispatcher):
    def __init__(self, pulses_per_second=10, start_pulse=0):
        super().__init__()
        self._pulse_map = defaultdict(set)
        self.pulses_per_second = pulses_per_second
        self.current_pulse = start_pulse

    def register_p(self, callback, pulses=0, seconds=0, randomize=0, priority=0, repeat=True, kwargs=None):
        if seconds:
            pulses = int(seconds * self.pulses_per_second)
            randomize = int(randomize * self.pulses_per_second)
        if randomize:
            randomize = randint(0, randomize)
        registration = PulseRegistration(pulses, callback, priority=priority, repeat=repeat, kwargs=kwargs)
        self._add_pulse(self.current_pulse + randomize, registration)
        return self._add_registration(registration)

    def register_once(self, *args, **kwargs):
        return self.register_p(repeat=False, *args, **kwargs)

    def future_pulse(self, seconds):
        return self.current_pulse + int(self.pulses_per_second * seconds)

    def seconds_to_pulse(self, seconds):
        return int(self.pulses_per_second * seconds)

    def pulse(self):
        self.dispatch('pulse')
        for reg in sorted(self._pulse_map[self.current_pulse], key=lambda reg: reg.priority):
            if reg.freq:
                try:
                    reg.callback(**reg.kwargs)
                except Exception:
                    log.exception('Pulse Error')
            if reg.repeat:
                self._add_pulse(self.current_pulse, reg)
        del self._pulse_map[self.current_pulse]
        self.current_pulse += 1

    def _add_pulse(self, start, event):
        self._pulse_map[start + event.freq].add(event)
