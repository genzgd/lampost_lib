import itertools

from lampost.gameops import target_gen
from lampost.di.resource import Injected, module_inject
from lampost.gameops.action import action_verbs
from lampost.util.lputil import find_extra, ClientError

log = Injected('log')
mud_actions = Injected('mud_actions')
module_inject(__name__)

MISSING_VERB = "Unrecognized command '{verb}'.  Perhaps you should try 'help'?"
EXTRA_WORDS = "'{extra}' does not make sense with '{verb}'."
MISSING_TARGET = "'{command}' what? or whom?"
ABSENT_TARGET = "'{target}' is not here."
ABSENT_OBJECT = "'{object}' is not here."
MISSING_PREP = "'{prep}' missing from command."
INVALID_TARGET = "You can't {verb} {target}."
INVALID_OBJECT = "You can't {verb} {target} {prep} {object}."
INSUFFICIENT_QUANTITY = "Not enough there to {verb} {quantity}."
AMBIGUOUS_COMMAND = "Ambiguous command matches: {}"

match_keywords = ['source', 'target', 'obj', 'target_method', 'obj_method', 'quantity', 'prep',
                  'action', 'verb', 'args', 'command']
_keyword_set = set(match_keywords)


def primary_actions(entity, verb):
    return itertools.chain.from_iterable(cache.primary(verb) for cache in entity.current_actions)


def abbrev_actions(entity, verb):
    return itertools.chain.from_iterable(cache.abbrev(verb) for cache in entity.current_actions)


def has_action(entity, action, verb):
    return action in primary_actions(entity, verb)


def find_targets(key_type, entity, target_key, target_class, action=None):
    return itertools.chain.from_iterable([target_func(key_type, target_key, entity, action) for target_func in target_class])


class ActionMatch():
    target = None
    targets = []
    target_method = None
    target_methods = []
    target_index = 0
    quantity = None
    prep = None
    obj_key = None
    obj = None
    obj_method = None

    def __init__(self, action, verb, args):
        self.action = action
        self.verb = verb
        self.args = args


def match_filter(func):
    def wrapper(self):
        for match in reversed(self._matches):
            result = func(self, match)
            if result:
                self._reject(result, match)
    return wrapper


def capture_index(target_key):
    try:
        ix = int(target_key[-1])
        if ix > 0:
            return ix - 1, target_key[:-1]
    except (TypeError, IndexError):
        pass
    except ValueError:
        try:
            first_split = target_key[0].split('.')
            return int(first_split[0]) - 1, (first_split[1],) + target_key[1:]
        except (ValueError, IndexError):
            pass
    return 0, target_key


class Parse:
    _matches = []

    def __init__(self, entity, command):
        self._words = command.lower().split()
        self._entity = entity
        self._command = command
        self._last_reject = None
        self._last_reason = MISSING_VERB

    def _reject(self, last_reason, reject):
        self._matches.remove(reject)
        self._last_reject = reject
        self._last_reason = last_reason

    def _raise_error(self):
        reject_format = {'command': self._command, 'verb': self._command.split(' ')[0]}
        last_reason = self._last_reason
        reject = self._last_reject
        if reject:
            extra = find_extra(reject.verb, 0, self._command)
            if extra:
                extra = extra.strip()
            reject_format['quantity'] = reject.quantity
            reject_format['verb'] = reject.verb
            reject_format['extra'] = extra
            reject_format['prep'] = reject.prep
            if extra and reject.prep:
                prep_ix = extra.find(reject.prep)
                if prep_ix == -1:
                    reject_format['target'] = extra
                else:
                    reject_format['target'] = extra[:prep_ix].strip()
                reject_format['object'] = extra[prep_ix + len(reject.prep):]
            else:
                reject_format['target'] = extra
            if last_reason in (INVALID_TARGET, ABSENT_TARGET):
                if not reject_format['target']:
                    last_reason = MISSING_TARGET
                elif last_reason == ABSENT_TARGET:
                    try:
                        last_reason = reject.action.target_class[0].absent_msg
                    except (IndexError, AttributeError):
                        pass
        raise ParseError(last_reason.format(**reject_format))

    def parse(self):
        matches = []
        for verb_size in range(1, len(self._words) + 1):
            verb = ' '.join(self._words[:verb_size])
            args = tuple(self._words[verb_size:])
            matches.extend([ActionMatch(action, verb, args) for action in primary_actions(self._entity, verb)])
        self._matches = self._entity.filter_actions(matches)
        result = self._process_matches()
        if result:
            return result
        verb = self._words[0]
        args = tuple(self._words[1:])
        matches = [ActionMatch(action, verb, args) for action in abbrev_actions(self._entity, verb)]
        self._matches = self._entity.filter_actions(matches)
        result = self._process_matches()
        if result:
            return result
        self._raise_error()

    def _ambiguous(self):
        verbs = []
        for match in self._matches:
            for verb in action_verbs(match.action):
                if verb.startswith(match.verb):
                    verbs.append(verb)
                    break
        raise ParseError(AMBIGUOUS_COMMAND.format(', '.join(verbs)))

    def _process_matches(self):
        self.parse_targets()
        self.parse_objects()
        if not self._matches:
            return
        match = self._matches[0]
        if match.targets:
            target_index = match.target_index
            target_matches = [(match, target, ix) for ix, target in enumerate(match.targets)]
            all_targets = set(match.targets)
            for match in self._matches[1:]:
                if not match.targets or match.target_index != target_index:
                    self._ambiguous()
                target_matches.extend([(match, target, ix) for ix, target in enumerate(match.targets)])
                all_targets.update(match.targets)
            if target_index >= len(target_matches):
                self._reject(INVALID_TARGET, match)
                return
            if len(all_targets) != len(target_matches):
                self._ambiguous()
            match, match.target, method_ix = target_matches[target_index]
            if match.target_methods:
                match.target_method = match.target_methods[method_ix]
        elif len(self._matches) > 1:
            raise self._ambiguous()
        return match.action, {key: value for key, value in match.__dict__.items() if key in _keyword_set}

    @match_filter
    def parse_targets(self, match):
        action = match.action
        target_class = getattr(action, 'target_class', None)
        if not target_class:
            return
        if target_class == 'no_args':
            return EXTRA_WORDS if match.args else None
        target_key = match.args
        if hasattr(action, 'quantity'):
            try:
                match.quantity = int(match.args[0])
                target_key = match.args[1:]
            except (IndexError, ValueError):
                pass
        match.prep = getattr(action, 'prep', None)
        if match.prep:
            try:
                prep_loc = target_key.index(match.prep)
                match.obj_key = target_key[(prep_loc + 1):]
                target_key = target_key[:prep_loc]
            except ValueError:
                if not hasattr(action, 'self_object'):
                    return MISSING_PREP
        if target_class == 'args':
            match.targets = [target_key]
            return
        match.target_index, target_key = capture_index(target_key)
        if target_key:
            key_str = ' '.join(target_key)
            found = list(find_targets('primary', self._entity, key_str, target_class, action))
            if not found:
                found = list(find_targets('abbrev', self._entity, key_str, target_class, action))
            if not found:
                return ABSENT_TARGET
            seen = set()
            targets = []
            for target in found:
                if target not in seen:
                    targets.append(target)
                    seen.add(target)
        elif hasattr(action, 'self_target'):
            targets = [self._entity]
        elif target_gen.env in target_class:
            targets = [self._entity.env]
        else:
            return MISSING_TARGET
        targets = [target for target in targets if
                   not match.quantity or match.quantity <= getattr(target, 'quantity', 0)]
        if not targets:
            return INSUFFICIENT_QUANTITY
        msg_class = getattr(match.action, 'msg_class', None)
        if msg_class:
            target_methods = [(target, getattr(target, msg_class)) for target in targets if hasattr(target, msg_class)]
            if target_methods:
                targets, match.target_methods = zip(*target_methods)
            else:
                return INVALID_TARGET
        match.targets = targets

    @match_filter
    def parse_objects(self, match):
        obj_target_class = getattr(match.action, 'obj_target_class', None)
        if not obj_target_class:
            return
        if obj_target_class == 'args':
            match.obj = match.obj_key
            return
        obj_index, obj_key = capture_index(match.obj_key)
        if obj_key:
            key_str = ' '.join(obj_key)
            objects = find_targets('primary', self._entity, key_str, obj_target_class)
            try:
                obj = next(itertools.islice(objects, obj_index, obj_index + 1))
            except StopIteration:
                objects = find_targets('abbrev', self._entity, key_str, obj_target_class)
                try:
                    obj = next(itertools.islice(objects, obj_index, obj_index + 1))
                except StopIteration:
                    return ABSENT_OBJECT
        elif hasattr(match.action, 'self_object'):
            obj = self._entity
        else:
            return MISSING_TARGET

        obj_msg_class = getattr(match.action, 'obj_msg_class', None)
        if obj_msg_class:
            match.obj_method = getattr(obj, obj_msg_class, None)
            if match.obj_method is None:
                return INVALID_OBJECT
        match.obj = obj


def parse_actions(entity, command):
    return Parse(entity, command).parse()


def parse_chat(verb, command):
    verb_ix = command.lower().index(verb) + len(verb)
    return command[verb_ix:].strip()


class ParseError(ClientError):
    pass
