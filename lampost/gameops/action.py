import inspect
import itertools
from collections import defaultdict

from lampost.di.resource import Injected, module_inject
from lampost.gameops import target
from lampost.gameops.script import script_builder
from lampost.meta.auto import AutoField
from lampost.meta.core import CoreMeta
from lampost.util.lputil import ClientError

log = Injected('log')
module_inject(__name__)


def action_verbs(action):
    verbs = getattr(action, 'verbs', ())
    if isinstance(verbs, str):
        return verbs,
    return verbs


def make_action(action, verbs=None, msg_class=None, target_class=None, obj_class=None, **kw_args):

    if verbs:
        action.verbs = verbs
    if msg_class:
        action.msg_class = msg_class

    match_args = getattr(action, 'match_args', None)
    if not match_args:
        try:
            match_args = inspect.getargspec(action)[0]
        except TypeError:
            match_args = inspect.getargspec(action.__call__)[0]
        try:
            match_args.remove('self')
        except ValueError:
            pass
        action.match_args = match_args

    if target_class:
        action.target_class = target.make_gen(target_class)
    elif not hasattr(action, 'target_class'):
        if not match_args or len(match_args) == 1 and match_args[0] == 'source':
            action.target_class = target.make_gen('no_args')
        else:
            action.target_class = target.make_gen('default')

    if obj_class:
        action.obj_class = target.make_gen(obj_class)

    for arg_name, value in kw_args.items():
        setattr(action, arg_name, value)

    if hasattr(action, 'prep') and not hasattr(action, 'obj_class'):
        action.obj_class = target.make_gen('default')
    if hasattr(action, 'obj_class') and not hasattr(action, 'prep'):
        action.prep = '_implicit_'
    return action


def obj_action(**kwargs):
    def decorator(func):
        if 'verbs' not in kwargs:
            kwargs['verbs'] = func.__name__
        if 'target_class' not in kwargs:
            kwargs['target_class'] = 'action_owner'
        make_action(func, **kwargs)
        return func
    return decorator


def find_actions(verb, action_set):
    for action in action_set:
        try:
            if verb in action.verbs:
                yield action
        except AttributeError:
            pass
        for sub_action in find_actions(verb, getattr(action, 'action_providers', [])):
            yield sub_action


def action_handler(func):
    def wrapper(self, *args, **kwargs):
        try:
            func(self, *args, **kwargs)
        except ClientError as client_error:
            self.display_line(client_error.client_message, client_error.display)
    return wrapper


class ActionError(ClientError):
    def __init__(self, msg=None, display=None):
        super().__init__(msg, display)


class ActionCache:
    def __init__(self):
        self._primary_map = defaultdict(list)
        self._abbrev_map = defaultdict(list)

    def primary(self, verb):
        return self._primary_map.get(verb, ())

    def abbrev(self, abbrev):
        return self._abbrev_map.get(abbrev, ())

    def all_actions(self):
        action_map = defaultdict(list)
        for verb, actions in self._primary_map.items():
            for action in actions:
                action_map[action].append(verb)
        return action_map

    def add(self, provider):
        try:
            for action in provider:
                self._add_action(action)
        except TypeError:
            self._add_action(provider)

    def remove(self, provider):
        try:
            for action in provider:
                self._remove_action(action)
        except TypeError:
            self._remove_action(provider)

    def refresh(self, provider):
        self._primary_map.clear()
        self._abbrev_map.clear()
        self.add(provider)

    def add_unique(self, action):
        for verb in action_verbs(action):
            if verb in self._primary_map:
                log.error("Adding duplicate verb {} to unique action cache", verb)
            else:
                self._primary_map[verb] = (action,)
            if not ' ' in verb:
                for vl in range(1, len(verb)):
                    self._abbrev_map[verb[:vl]].append(action)

    def _add_action(self, action):
        for verb in action_verbs(action):
            self._primary_map[verb].append(action)
            if not ' ' in verb:
                for vi in range(1, len(verb)):
                    a_list = self._abbrev_map[verb[:vi]]
                    if action not in a_list:
                        a_list.append(action)
        for provider in getattr(action, 'action_providers', ()):
            self.add(provider)

    def _remove_action(self, action):
        for verb in action_verbs(action):
            try:
                self._primary_map[verb].remove(action)
            except ValueError:
                log.warn("Removing {} from ActionCache that did not exist", action)
            if ' ' not in verb:
                for vl in range(1, len(verb)):
                    try:
                        self._abbrev_map[verb[:vl]].remove(action)
                    except ValueError:
                        log.warn("Removing {} from ActionCache abbrev that did not exist", action)
        for provider in getattr(action, 'action_providers', ()):
            self.remove(provider)


class ActionProvider(metaclass=CoreMeta):
    instance_providers = AutoField([])

    @classmethod
    def _mixin_init(cls, name, bases, new_attrs):
        cls._update_set(bases, 'class_providers')
        cls.class_providers.update({func.__name__ for func in new_attrs.values() if hasattr(func, 'verbs')})

    @property
    def action_providers(self):
        return itertools.chain((getattr(self, func_name) for func_name in self.class_providers), self.instance_providers)

    def _pre_reload(self):
        self.instance_providers = []


@script_builder
class ActionScriptBuilder:
    dto = {'name': 'action', 'meta_default': {'action_args': ['source'], 'target_class': ['action_owner'], 'verbs': []}}

    @staticmethod
    def build(target, s_ref):
        action = obj_action(**s_ref.build_args)(s_ref.script_func)
        target_action = action.__get__(target)
        target.__dict__[s_ref.script_func.__name__] = target_action
        target.instance_providers.append(target_action)
