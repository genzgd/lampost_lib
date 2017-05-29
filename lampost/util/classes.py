def cls_name(cls):
    return ".".join([cls.__module__, cls.__name__])


def call_each(coll, func_name, *args, **kwargs):
    for obj in coll:
        try:
            func = getattr(obj, func_name)
        except AttributeError:
            continue
        func(*args, **kwargs)


def subclasses(cls):
    for subclass in cls.__subclasses__():
        yield subclass
        for sub_sub in subclasses(subclass):
            yield sub_sub
