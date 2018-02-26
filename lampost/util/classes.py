def cls_name(cls):
    return ".".join([cls.__module__, cls.__name__])


def call_by_name(obj, func_name, *args, **kwargs):
    try:
        func = getattr(obj, func_name)
    except AttributeError:
        return
    func(*args, **kwargs)


def call_mro(obj, func_name, *args, **kwargs):
    for cls in reversed(obj.__class__.__mro__):
        try:
            cls.__dict__[func_name](obj, *args, **kwargs)
        except KeyError:
            pass


def call_each(coll, func_name, *args, **kwargs):
    for obj in coll:
        try:
            func = getattr(obj, func_name)
        except AttributeError:
            continue
        func(*args, **kwargs)


def no_op(*args, **kwargs):
    pass


def call_values(dict_obj, func_name, *args, **kwargs):
    call_each(dict_obj.values(), func_name, *args, **kwargs)


def subclasses(cls):
    for subclass in cls.__subclasses__():
        yield subclass
        for sub_sub in subclasses(subclass):
            yield sub_sub
