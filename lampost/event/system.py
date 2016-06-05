from tornado.ioloop import PeriodicCallback

from lampost.di.app import on_app_start
from lampost.di.config import on_config_change, config_value
from lampost.di.resource import Injected, module_inject
from lampost.event.dispatcher import PulseDispatcher

log = Injected('log')
db = Injected('datastore')
module_inject(__name__)

dispatcher = PulseDispatcher()

pulse_lc = None
maintenance_lc = None


@on_app_start
def _start():
    dispatcher.current_pulse = db.load_value('event_pulse', 0)
    dispatcher.register_p(lambda: db.save_value('event_pulse', dispatcher.current_pulse), 100)
    _start_heartbeat()


@on_config_change
def _start_heartbeat():
    global pulse_lc, maintenance_lc
    pulse_interval = config_value('pulse_interval')
    maintenance_interval = config_value('maintenance_interval')
    dispatcher.pulses_per_second = 1 / pulse_interval
    if pulse_lc:
        pulse_lc.stop()
    pulse_lc = PeriodicCallback(dispatcher.pulse, pulse_interval * 1000)
    pulse_lc.start()
    log.info("Pulse Event heartbeat started at {} seconds", pulse_interval)

    if maintenance_lc:
        maintenance_lc.stop()
    maintenance_lc = PeriodicCallback(lambda: dispatcher.dispatch('maintenance'), 60 * maintenance_interval * 1000)
    maintenance_lc.start()
    log.info("Maintenance Event heartbeat started at {} minutes", maintenance_interval)

