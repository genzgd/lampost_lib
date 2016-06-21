import inspect
import itertools
from collections import defaultdict

from lampost.di.resource import Injected, module_inject
from lampost.gameops import target_gen
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


def make_action(action, verbs=None, msg_class=None, target_class=None, prep=None,
                obj_msg_class=None, obj_target_class=None, **kw_args):
    if verbs:
        action.verbs = verbs

    if msg_class:
        action.msg_class = msg_class

    if target_class:
        action.target_class = target_gen.make(target_class)
    elif not hasattr(action, 'target_class'):
        try:
            args, var_args, var_kwargs, defaults = inspect.getargspec(action)
        except TypeError:
            args, var_args, var_kwargs, defaults = inspect.getargspec(action.__call__)
        target_args = len(args) - len([arg for arg in args if arg in {'self', 'source', 'command', 'args', 'verb'}])
        if target_args:
            action.target_class = target_gen.defaults
        elif not args or len(args) == 1 and args[0] == 'source':
            action.target_class = 'no_args'

    if prep:
        action.prep = prep
        if obj_target_class:
            action.obj_target_class = target_gen.make(obj_target_class)
        elif not hasattr(action, 'obj_target_class'):
            action.obj_target_class = target_gen.defaults
        if obj_msg_class:
            action.obj_msg_class = obj_msg_class
    for arg_name, value in kw_args.items():
        setattr(action, arg_name, value)
    return action


def obj_action(**kwargs):
    def decorator(func):
        if 'verbs' not in kwargs:
            kwargs['verbs'] = func.__name__
        if 'target_class' not in kwargs:
            kwargs['target_class'] = 'func_owner'
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


class InstanceAction:
    def __init__(self, func, owner, verbs=None):
        self.func = func
        self.owner = owner
        make_action(self, verbs, target_class="action_owner")

    def __call__(self, **kwargs):
        kwargs['owner'] = self.owner
        return self.func(**kwargs)


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

    def _on_reload(self):
        self.instance_providers = []

    def dynamic_action(self, func, verbs=None):
        if not verbs:
            verbs = func.__name__
        action = InstanceAction(func, self, verbs)
        self.instance_providers.append(action)
