import time
import json

pronouns = {'none': ['it', 'it', 'its', 'itself', 'its'],
            'male': ['he', 'him', 'his', 'himself', 'his'],
            'female': ['she', 'her', 'her', 'herself', 'hers']}


def l_just(value, size):
    return value.ljust(size).replace(' ', '&nbsp;')


def timestamp(record):
    ts = int(time.time())
    try:
        record['timestamp'] = ts
        return record
    except KeyError:
        return ':'.join([record, ts])


def plural(noun):
    if noun[-1:] == 's':
        return "{}es".format(noun)
    return "{}s".format(noun)


def dump(dump_dict):
    return ["{0}: {1}".format(key, str(value)) for key, value in dump_dict.items()]


def find_nth(haystack, needle, n):
    start = haystack.find(needle)
    while start >= 0 and n > 1:
        start = haystack.find(needle, start + len(needle))
        n -= 1
    return start


def javascript_safe(value):
    value = value.replace('"', '\\\"')
    value = value.replace("'", "\\'")
    value = value.replace("\n", "")
    return value


def tuples_to_list(keys, tuples):
    return [{name: value[ix] for ix, name in enumerate(keys)} for value in tuples]


class jsonToObj():
    def __init__(self, json_dict):
        self.__dict__.update(**json_dict)


class ClientError(Exception):
    http_status = 400

    def __init__(self, client_message="client_error", display=None, http_status=None):
        self.client_message = client_message
        self.display = display
        if http_status:
            self.http_status = http_status


class PermError(ClientError):
    http_status = 403

    def __init__(self):
        super().__init__("You do not have permission to do that")


def patch_object(obj, prop, new_value):
    existing_value = getattr(obj, prop, None)
    if existing_value is not None:
        try:
            if isinstance(existing_value, int):
                new_value = int(new_value)
            elif isinstance(existing_value, float):
                new_value = float(new_value)
            elif isinstance(existing_value, str):
                pass
            else:
                raise ClientError("Only number and string values can be patched")
        except ValueError:
            raise ClientError("Existing value is not compatible with patch value")
    try:
        setattr(obj, prop, new_value)
    except:
        raise ClientError("Failed to set value.")


def str_to_primitive(value):
    if value == 'None':
        return None
    try:
        return json.JSONDecoder().decode(value)
    except ValueError:
        pass
    return json.JSONDecoder().decode('"{}"'.format(value))


def args_print(**kwargs):
    return ''.join(['{0}:{1} '.format(key, str(value)) for key, value in kwargs.items()])
