import inspect
import logging

from logging import LogRecord, Logger, basicConfig

_old_formatting = set()

class LogFmtRecord(LogRecord):
    def getMessage(self):
        msg = self.msg
        if self.args:
            if self.name in _old_formatting:
                msg = msg % self.args
            elif isinstance(self.args, dict):
                msg = msg.format(self.args)
            else:
                msg = msg.format(*(self.args))
        return msg


class LoggerFmt(Logger):
    def makeRecord(self, name, level, fn, lno, msg, args, exc_info, func=None, extra=None, sinfo=None):
        rv = LogFmtRecord(name, level, fn, lno, msg, args, exc_info, func, sinfo)
        if extra is not None:
            for key in extra:
                if (key in ["message", "asctime"]) or (key in rv.__dict__):
                    raise KeyError("Attempt to overwrite %r in LogRecord" % key)
                rv.__dict__[key] = extra[key]
        return rv


class LogFactory():
    def factory(self, consumer):
        if inspect.isclass(consumer):
            consumer = consumer.__qualname__
        if inspect.ismodule(consumer):
            consumer = consumer.__name__
        logger = logging.getLogger(consumer)
        logger.debug_enabled = lambda: logger.getEffectiveLevel() <= logging.DEBUG
        return logger

    def set_level(self, log_level):
        basicConfig(level=log_level)


logging.setLoggerClass(LoggerFmt)
log_format = '{asctime: <20}  {levelname: <8} {name: <26}  {message}'
root_logger = None


def init_config(args):
    global root_logger
    log_level = getattr(logging, args.log_level.upper())
    kwargs = {'format': log_format}
    if args.log_file:
        kwargs.update({'filename': args.log_file, 'filemode': args.log_mode})
    logging.basicConfig(level=log_level, style="{", **kwargs)
    root_logger = logging.getLogger('root')


def get_logger(logger_name, old_formatting=True):
    if old_formatting:
        _old_formatting.add(logger_name)
    return logging.getLogger(logger_name)

def logged(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as error:
            root_logger.exception("Unhandled exception", func.__name__, error)
    return wrapper
