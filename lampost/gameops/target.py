import math


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


def test():
    tk = TargetKeys()
    tk.add('bright green chariot')
    print (tk.primary)
    print (list(tk.abbrev))
