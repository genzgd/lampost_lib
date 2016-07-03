class Registration:
    def __init__(self, event_type, callback, owner=None, priority=0):
        self.event_type = event_type
        self.callback = callback
        self.owner = owner if owner else getattr(callback, '__self__', self)
        self.priority = priority

    def cancel(self):
        pass


class PulseRegistration(Registration):
    kwargs = {}

    def __init__(self, freq, callback, owner=None, priority=0, repeat=True, kwargs=None):
        super().__init__('pulse_i', callback, owner, priority)
        self.freq = freq
        self.repeat = repeat
        if kwargs:
            self.kwargs = kwargs

    def cancel(self):
        self.freq = 0
