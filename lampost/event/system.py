from tornado.ioloop import PeriodicCallback

from lampost.di.config import m_configured
from lampost.di.resource import Injected, module_inject
from lampost.event.dispatcher import PulseDispatcher

log = Injected('log')
db = Injected('datastore')
module_inject(__name__)

dispatcher = PulseDispatcher()

pulse_lc = None
maintenance_lc = None


def _post_init():
    dispatcher.current_pulse = db.load_raw('event_pulse', 0)
    dispatcher.register_p(lambda: db.save_raw('event_pulse', dispatcher.current_pulse), 100)


def _on_configured():
    global pulse_lc, maintenance_lc
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


m_configured(__name__, 'pulse_interval', 'maintenance_interval')
