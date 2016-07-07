import itertools
from collections import deque

from lampost.gameops.action import action_verbs
from lampost.gameops.target import make_gen
from lampost.util.lputil import ClientError

MISSING_VERB = "Unrecognized command '{verb}'.  Perhaps you should try 'help'?"
MISSING_TARGET = MISSING_OBJECT = "'{command}' what? or whom?"
MISSING_PREP = "'{prep}' missing from command."
ABSENT_TARGET = "{target} is not here."
ABSENT_OBJECT = "{object} is not here."
INVALID_TARGET = "You can't {verb} {target}."
INVALID_OBJECT = "You can't {verb} {target} {prep} {object}."
INSUFFICIENT_QUANTITY = "Not enough there to {verb} {quantity}."
AMBIGUOUS_COMMAND = "Ambiguous command matches: {}"

action_keywords = ['source', 'target', 'obj', 'quantity']


def primary_actions(entity, verb):
    return itertools.chain.from_iterable(cache.primary(verb) for cache in entity.current_actions)


def abbrev_actions(entity, verb):
    return itertools.chain.from_iterable(cache.abbrev(verb) for cache in entity.current_actions)


def has_action(entity, action, verb):
    return action in primary_actions(entity, verb)


def find_targets(key_type, entity, target_key, target_class, action=None):
    return itertools.chain.from_iterable([target_func(key_type, target_key, entity, action) for target_func in target_class])


def find_invalid_target(target_key, entity, action):
    bad_gen = make_gen('__invalid__')
    bad_targets = find_targets('primary', entity, target_key, bad_gen, action)
    try:
        return next(bad_targets)
    except StopIteration:
        bad_targets = find_targets('abbrev', entity, target_key, bad_gen, action)
        return next(bad_targets, None)


class ActionMatch():
    target = None
    target_key = ''
    targets = []
    target_index = 0
    quantity = None
    prep = None
    obj_str = ''
    obj_key = ''
    obj = None
    obj_method = None

    def __init__(self, source, action, verb, remaining):
        self.source = source
        self.action = action
        self.verb = verb
        self.remaining = remaining


def match_filter(func):
    def wrapper(self):
        for match in reversed(self._matches):
            result = func(self, match)
            if result:
                self._reject(result, match)
    return wrapper


def capture_index(target_words):
    try:
        ix = int(target_words[-1])
        if ix > 0:
            return ix - 1, target_words[:-1]
    except (TypeError, IndexError):
        pass
    except ValueError:
        try:
            first_split = target_words[0].split('.')
            return int(first_split[0]) - 1, (first_split[1],) + tuple(target_words[1:])
        except (ValueError, IndexError):
            pass
    return 0, target_words


class Parse:
    _matches = []

    def __init__(self, entity, command):
        self._command = command
        self._entity = entity
        self._last_reject = None
        self._primary_parsed = False
        self._last_reason = MISSING_VERB

    def _reject(self, last_reason, reject):
        self._matches.remove(reject)
        if not self._primary_parsed or not self._last_reject:
            self._last_reject = reject
            self._last_reason = last_reason

    def _raise_error(self):
        reject_format = {'command': self._command, 'verb': self._command.split(' ')[0]}
        last_reason = self._last_reason
        reject = self._last_reject
        if reject:
            reject_format['quantity'] = reject.quantity
            reject_format['verb'] = next((verb for verb in action_verbs(reject.action) if verb.startswith(reject.verb)),
                                         reject.verb)
            reject_format['prep'] = reject.prep
            if last_reason == ABSENT_TARGET:
                if reject.target_key:
                    reject.target = find_invalid_target(reject.target_key, self._entity, reject)
                    if reject.target:
                        last_reason = INVALID_TARGET
                    else:
                        try:
                            last_reason = reject.action.target_class[0].absent_msg
                        except (IndexError, AttributeError):
                            pass
                else:
                    last_reason = MISSING_TARGET
            reject_format['target'] = getattr(reject.target, 'name', reject.target_key)
            if last_reason == ABSENT_OBJECT:
                if reject.obj_key:
                    reject.obj = find_invalid_target(reject.obj_key, self._entity, reject)
                else:
                    last_reason = MISSING_OBJECT
            reject_format['object'] = getattr(reject.obj, 'name', reject.obj_key)

        raise ParseError(last_reason.format(**reject_format))

    def parse(self):
        matches = []
        remaining = self._command
        verb_set = deque()
        while True:
            word, remaining = next_word(remaining)
            verb_set.append(word)
            verb = ' '.join(verb_set)
            matches.extend(ActionMatch(self._entity, action, verb, remaining) for action in primary_actions(self._entity, verb))
            if not remaining:
                break
        self._matches = self._entity.filter_actions(matches)
        result = self._process_matches()
        if result:
            return result
        self._primary_parsed = True
        verb, remaining = next_word(self._command)
        matches = [ActionMatch(self._entity, action, verb, remaining) for action in abbrev_actions(self._entity, verb)]
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
            target_matches = [(match, target) for target in match.targets]
            all_targets = set(match.targets)
            for match in self._matches[1:]:
                if not match.targets or match.target_index != target_index:
                    self._ambiguous()
                target_matches.extend(((match, target) for target in match.targets))
                all_targets.update(match.targets)
            if target_index >= len(target_matches):
                self._reject(INVALID_TARGET, match)
                return
            if len(all_targets) != len(target_matches):
                self._ambiguous()
            match, match.target = target_matches[target_index]
        elif len(self._matches) > 1:
            raise self._ambiguous()
        return match.action, {key: getattr(match, key) for key in match.action.match_args}

    @match_filter
    def parse_targets(self, match):
        action = match.action
        target_str = match.remaining
        if hasattr(action, 'quantity'):
            try:
                qty, remaining = next_word(target_str)
                match.quantity = int(qty)
                target_str = remaining
            except (IndexError, ValueError):
                pass
        prep = getattr(action, 'prep', None)
        if prep == '_implicit_':
            match.obj_str = target_str
        elif prep:
            match.prep = prep
            try:
                prep_str = " {} ".format(prep)
                prep_loc = target_str.index(prep_str)
                match.obj_str = target_str[prep_loc + len(prep) + 2:]
                target_str = target_str[:prep_loc].strip()
            except ValueError:
                if hasattr(action, 'self_object'):
                    match.obj_str = ''
                else:
                    return MISSING_PREP
        match.target_str = target_str
        target_class = getattr(action, 'target_class', _noop)

        try:
            return target_class(match)
        except TypeError:
            pass

        found = ()

        def _find(target_words):
            nonlocal found
            match.target_index, temp_key = capture_index(target_words)
            match.target_key = key_str = ' '.join(temp_key)
            found = tuple(find_targets('primary', self._entity, key_str, target_class, action))
            if not found:
                found = tuple(find_targets('abbrev', self._entity, key_str, target_class, action))

        if prep == '_implicit_':
            word_set = deque()
            while True:
                word, match.obj_str = next_word(match.obj_str)
                word_set.append(word.lower())
                _find(word_set)
                if found or not match.obj_str:
                    break
        else:
            _find(target_str.lower().split(' '))
        if not found:
            return ABSENT_TARGET
        seen = set()
        targets = []
        for target in found:
            if target not in seen:
                targets.append(target)
                seen.add(target)
        targets = [target for target in targets if
                   not match.quantity or match.quantity <= getattr(target, 'quantity', 0)]
        if not targets:
            return INSUFFICIENT_QUANTITY
        msg_class = getattr(match.action, 'msg_class', None)
        if msg_class:
            targets = [target for target in targets if getattr(target, msg_class, None) is not None]
            if not targets:
                return INVALID_TARGET
        match.targets = targets

    @match_filter
    def parse_objects(self, match):
        obj_class = getattr(match.action, 'obj_class', _noop)
        try:
            return obj_class(match)
        except TypeError:
            pass
        obj_index, obj_key = capture_index(match.obj_str.lower().split(' '))
        match.obj_key = key_str = ' '.join(obj_key)
        objects = find_targets('primary', self._entity, key_str, obj_class)
        obj = next(itertools.islice(objects, obj_index, obj_index + 1), None)
        if not obj:
            objects = find_targets('abbrev', self._entity, key_str, obj_class)
            obj = next(itertools.islice(objects, obj_index, obj_index + 1), None)
            if not obj:
                return ABSENT_OBJECT
        match.obj = obj
        obj_msg_class = getattr(match.action, 'obj_msg_class', None)
        if obj_msg_class and getattr(obj, obj_msg_class, None) is None:
            return INVALID_OBJECT



def next_word(text):
    next_space = text.find(' ')
    if next_space == -1:
        next_space = len(text) + 1
    return text[:next_space], text[next_space + 1:].strip()


def parse_actions(entity, command):
    return Parse(entity, command.strip()).parse()


def _noop(*_):
    pass


class ParseError(ClientError):
    pass
