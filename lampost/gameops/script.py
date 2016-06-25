import inspect
import bisect

from collections import defaultdict

from lampost.di.app import on_app_start
from lampost.di.resource import Injected, module_inject
from lampost.meta.auto import AutoField
from lampost.db.dbo import ChildDBO, DBOFacet, CoreDBO
from lampost.db.dbofield import DBOField, DBOLField, DBOCField

log = Injected('log')
ev = Injected('dispatcher')
module_inject(__name__)

script_cache = {}
builders = {}


@on_app_start
def _start():
    ev.register('maintenance', lambda: script_cache.clear())


def script_builder(cls):
    builders[cls.name] = cls
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
        return self.create_chain(instance)

    def create_chain(self, instance):
        shadow_funcs = []
        original_inserted = False
        for shadow in instance.shadow_chains.get(self.func_name, []):
            shadow_locals = {}
            exec(shadow.code, self.func.__globals__, shadow_locals)
            shadow_func = next(iter(shadow_locals.values()))
            if shadow.priority == 0:
                original_inserted = True
            elif shadow.priority > 0 and not original_inserted:
                shadow_funcs.append(self.func)
                original_inserted = True
            shadow_funcs.append(shadow_func)
        if not original_inserted:
            shadow_funcs.append(self.func)

        if len(shadow_funcs) == 1:
            bound_chain = shadow_funcs[0].__get__(instance)
        else:
            bound_chain = create_chain(shadow_funcs).__get__(instance)

        instance.__dict__[self.func_name] = bound_chain
        return bound_chain


class UserScript(DBOFacet):
    title = DBOField('', required=True)
    builder = DBOField('', required=True)
    metadata = DBOField({})
    text = DBOField('', required=True)
    script_hash = DBOField('')
    approved = DBOField(False)

    _code = AutoField()


    @property
    def code(self):
        if self.approved:
            self._code, err_str = compile_script(self.script_hash, self.text, self.dbo_id)
            if err_str:
                log.warn("Error compiling UserScript {}: {}", self.dbo_id, err_str)
        else:
            self._code = None
        return self._code


class ScriptRef(CoreDBO):
    class_id = 'script_ref'

    func_name = DBOField('', required=True)
    script = DBOLField(dbo_class_id='script', required=True)
    build_args = DBOField({})

    @property
    def builder(self):
        return builders[self.script.builder]

    @property
    def code(self):
        return self.script.code

    def build(self, target):
        if self.script.approved:
            try:
                self.builder.build(target, self)
            except Exception:
                log.exception("Failed to build user script {}", self.dto_value)
        else:
            log.info("Referencing unapproved script {}", self.script.dbo_id)


class Scriptable(DBOFacet):
    script_refs = DBOCField([], 'script_ref')
    shadow_chains = AutoField(defaultdict(list))

    def _on_loaded(self):
        self._prepare_scripts()

    def _on_reload(self):
        self.shadow_chains = defaultdict(list)
        self._prepare_scripts()

    def _prepare_scripts(self):
        for script_ref in self.script_refs:
            script_ref.build(self)
        try:
            self.load_scripts()
        except Exception:
            log.exception("Exception on user defined 'load_scripts'")

    @Shadow
    def load_scripts(self, *args, **kwargs):
        pass


class ScriptShadow:
    def __init__(self, code, priority=0):
        self.code = code
        self.priority = priority

    def __cmp__(self, other):
        if self.priority < other.priority:
            return -1
        if self.priority > other.priority:
            return 1
        return 0


@script_builder
class ShadowBuilder:
    name = "shadow"

    @staticmethod
    def build(target, s_ref):
        func_shadows = target.shadow_chains[s_ref.func_name]
        shadow = ScriptShadow(s_ref.code, s_ref.build_args['priority'])
        bisect.insort(func_shadows, shadow)
