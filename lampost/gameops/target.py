import math
import inspect

from itertools import chain
from collections import Iterable

target_generators = {}


def _gen_keys(target_id):
    parts = target_id.lower().split()
    prefix_count = len(parts)
    for x in range(1, int(math.pow(2, prefix_count))):
        next_prefix = []
        for y in range(prefix_count):
            if int(math.pow(2, y)) & x:
                next_prefix.append(parts[y])
        yield ' '.join(next_prefix)


def _abbrev_keys(parts, key_ix):
    part = parts[key_ix]
    for pl in range(2, max(len(part), 5)):
        sub = parts[:key_ix] + [part[:pl]] + parts[key_ix + 1:]
        yield ' '.join(sub)
        if key_ix < len(sub) - 1:
            for target in _abbrev_keys(sub, key_ix + 1):
                yield target


class TargetKeys:
    def __init__(self, initial_id=None):
        self.primary = set()
        self.add(initial_id)

    def add(self, target_id):
        if target_id:
            self.primary.update(_gen_keys(target_id))

    @property
    def abbrev(self):
        for key in self.primary:
            parts = key.split()
            for ix in range(len(parts) - 1, -1, -1):
                for target in _abbrev_keys(parts, ix):
                    yield target


def target_gen(func):
    args = inspect.getargspec(func)[0]
    if len(args) == 1 and args[0] == 'match':
        target_generators[func.__name__] = func
    else:
        target_generators[func.__name__] = func,
    return func


def recursive_targets(key_type, target_list, target_key):
    for target in target_list:
        try:
            if target_key in getattr(target.target_keys, key_type):
                yield target
        except AttributeError:
            pass
        for sub_target in recursive_targets(key_type, getattr(target, 'target_providers', ()), target_key):
            yield sub_target


@target_gen
def extra(match):
    if match.remaining:
        if match.target or match.targets:
            match.obj = match.remaining
        else:
            match.target = match.remaining
    else:
        return "'{command}' what? Or whom?"


@target_gen
def opt_extra(match):
    if match.target or match.targets:
        match.obj = match.remaining
    else:
        match.target = match.remaining


@target_gen
def no_args(match):
    if match.remaining:
        match.target = match.remaining
        return "'{target}' does not make sense with '{verb}'."


@target_gen
def target_str(match):
    if match.target_str:
        match.target = match.target_str
    else:
        return "'{command}' what?  Or whom?"


@target_gen
def self(key_type, target_key, entity, *_):
    if target_key == 'self' or target_key in getattr(entity.target_keys, key_type):
        yield entity


@target_gen
def action_owner(key_type, target_key, entity, action, *_):
    return recursive_targets(key_type, (action.__self__,), target_key)


@target_gen
def action_default(key_type, target_key, entity, action, *_):
    if not target_key:
        try:
            yield action.__self__
        except AttributeError:
            yield action


@target_gen
def action(key_type, target_key, entity, action):
    return recursive_targets(key_type, [action], target_key)


@target_gen
def func_providers(key_type, target_key, entity, action, *_):
    for target in action.__self__.target_providers:
        try:
            if target_key in getattr(target.target_keys, key_type):
                yield target
        except AttributeError:
            pass


@target_gen
def self_default(key_type, target_key, entity, *_):
    if not target_key:
        yield entity


def make_gen(target_class, cache_key=None):
    if hasattr(target_class, 'split'):
        try:
            return target_generators[target_class]
        except KeyError:
            pass
        generator = tuple(
            chain.from_iterable(target_generators[target_type] for target_type in target_class.split(' ')))
        target_generators[cache_key if cache_key else target_class] = generator
        return generator

    if isinstance(target_class, Iterable):
        return target_class
    return target_class,
