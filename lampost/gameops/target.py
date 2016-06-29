import math
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
            yield from _abbrev_keys(sub, key_ix + 1)


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
                yield from _abbrev_keys(parts, ix)


def target_gen(func):
    target_generators[func.__name__] = func
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
def args(key_type, target_key, *_):
    if target_key:
        yield tuple(target_key.split(' '))


@target_gen
def self(key_type, target_key, entity, *_):
    if target_key == 'self' or target_key in getattr(entity.target_keys, key_type):
        yield entity


@target_gen
def func_owner(key_type, target_key, entity, action, *_):
    return recursive_targets(key_type, [action.__self__], target_key)


@target_gen
def action(key_type, target_key, entity, action):
    return recursive_targets(key_type, [action], target_key)


@target_gen
def action_owner(key_type, target_key, entity, action, *_):
    try:
        if target_key in getattr(action.owner.target_keys, key_type):
            yield action.owner
    except AttributeError:
        pass


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


_generator_cache = {}


def make_gen(target_class, cache_key=None):
    if hasattr(target_class, 'split'):
        try:
            return _generator_cache[target_class]
        except KeyError:
            pass
        gen_funcs = []
        for target_type in target_class.split(' '):
            if target_type in _generator_cache:
                gen_funcs.extend(_generator_cache[target_type])
            else:
                gen_funcs.append(target_generators[target_type])
        generator = tuple(gen_funcs)
        _generator_cache[cache_key if cache_key else target_class] = generator
        return generator

    if isinstance(target_class, Iterable):
        return target_class
    return target_class,
