import bisect

from collections import defaultdict

from lampost.di.app import on_app_start
from lampost.di.resource import Injected, module_inject
from lampost.meta.auto import AutoField
from lampost.db.dbo import DBOAspect, CoreDBO
from lampost.db.dbofield import DBOField, DBOLField, DBOCField

log = Injected('log')
ev = Injected('dispatcher')
script_globals = {}
module_inject(__name__)

script_cache = {}
builders = set()


@on_app_start
def _start():
    ev.register('maintenance', lambda: script_cache.clear())
    script_globals['log'] = log


def script_builder(cls):
    builders.add(cls)
    return cls


def create_chain(funcs):
    def chained(self, *args, **kwargs):
        try:
            last_return = None
            for func in funcs:
                last_return = func(self, *args, last_return=last_return, **kwargs)
            return last_return
        except Exception:
            log.exception("Exception in user defined script")

    chained._user_def = True
    return chained


def compile_script(script_hash, script_text, script_id):
    try:
        return script_cache[script_hash], None
    except KeyError:
        pass
    try:
        code = compile(script_text, '{}_shadow'.format(script_id), 'exec')
        script_cache[script_hash] = code
        return code, None
    except SyntaxError as err:
        err_str = "Syntax Error: {}  text:{}  line: {}  offset: {}".format(err.msg, err.text, err.lineno, err.offset)
    except BaseException as err:
        err_str = "Script Error: {}".format(err)
    return None, err_str


class Shadow:
    def __init__(self, func):
        self.func = func
        self.func_name = func.__name__

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        try:
            return instance.__dict__[self.func_name]
        except KeyError:
            pass
        return self._create_chain(instance)

    def _create_chain(self, instance):
        shadow_funcs = []
        original_inserted = False
        for shadow in instance.shadow_chains.get(self.func_name, []):
            if shadow.priority == 0:
                original_inserted = True
            elif shadow.priority > 0 and not original_inserted:
                shadow_funcs.append(self.func)
                original_inserted = True
            shadow_funcs.append(shadow.func)
        if not original_inserted:
            shadow_funcs.append(self.func)

        if len(shadow_funcs) == 1:
            bound_chain = shadow_funcs[0].__get__(instance)
        else:
            bound_chain = create_chain(shadow_funcs).__get__(instance)

        instance.__dict__[self.func_name] = bound_chain
        return bound_chain


class UserScript(DBOAspect):
    title = DBOField('', required=True)
    builder = DBOField('', required=True)
    metadata = DBOField({})
    text = DBOField('', required=True)
    script_hash = DBOField('')
    approved = DBOField(False)

    _script_func = AutoField()

    @property
    def script_func(self):
        if not self.approved:
            self._script_func = None
            return None
        if self._script_func:
            return self._script_func
        code, err_str = compile_script(self.script_hash, self.text, self.dbo_id)
        if err_str:
            log.warn("Error compiling UserScript {}: {}", self.dbo_id, err_str)
            return None
        my_globals = script_globals if isinstance(script_globals, dict) else {}
        script_locals = {}
        exec(code, my_globals, script_locals)
        self._script_func = next(iter(script_locals.values()))
        self._script_func._user_def = True
        return self._script_func


class ScriptRef(CoreDBO):
    class_id = 'script_ref'

    func_name = DBOField('')
    script = DBOLField(dbo_class_id='script', required=True)
    build_args = DBOField({})

    @property
    def script_func(self):
        return self.script.script_func

    def build(self, target):
        if not self.script:
            return
        if not self.script.approved:
            log.info("Referencing unapproved script {}", self.script.dbo_id)
            return
        if not self.script.script_func:
            return
        try:
            builder = builders[self.script.builder]
            builder.build(target, self)
        except Exception:
            log.exception("Failed to build user script {}", self.dto_value)


class Scriptable(DBOAspect):
    script_refs = DBOCField([], 'script_ref')
    shadow_chains = AutoField(defaultdict(list))

    def _on_loaded(self):
        for script_ref in self.script_refs:
            script_ref.build(self)
        try:
            self.load_scripts()
        except Exception:
            log.exception("Exception on user defined 'load_scripts'")

    def _pre_reload(self):
        user_methods = {name for name, value in self.__dict__.items() if hasattr(value, '_user_def')}
        for name in user_methods:
            del self.__dict__[name]
        self.shadow_chains = defaultdict(list)

    @Shadow
    def load_scripts(self, *args, **kwargs):
        pass


class ScriptShadow:
    def __init__(self, func, priority=0):
        self.func = func
        self.priority = priority

    def __lt__(self, other):
        return self.priority < other.priority


@script_builder
class ShadowBuilder:
    dto = {'name': 'shadow', 'meta_default': {'cls_type': None, 'cls_shadow': None}}

    @staticmethod
    def build(target, s_ref):
        func_shadows = target.shadow_chains[s_ref.func_name]
        shadow = ScriptShadow(s_ref.script_func, s_ref.build_args['priority'])
        bisect.insort(func_shadows, shadow)
