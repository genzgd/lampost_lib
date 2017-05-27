def display_dto(obj, observer):
    if not hasattr(obj, '__class__'):
        return obj
    display = {}
    for cls in obj.__class__.__mro__:
        for field_name in cls.__dict__.get('display_fields', ()):
            value = getattr(obj, field_name, None)
            if hasattr(value, '__call__'):
                value = value(observer)
            if value is None:
                continue
            if isinstance(value, (int, str, bool, float, dict)):
                display[field_name] = value
            else:
                display[field_name] = (display_dto(member, observer) for member in value)
    return display
