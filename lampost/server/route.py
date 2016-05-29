class Route:
    def __init__(self, url_regex, handler, **kwargs):
        self.url_regex = url_regex
        self.handler = handler
        self.init_args = kwargs
