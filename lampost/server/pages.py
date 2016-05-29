from tornado.web import RequestHandler

_pages = {}


def add_page(page):
    _pages[page.page_id] = page


class LspHandler(RequestHandler):
    def get(self, page_id):
        try:
            page = _pages[page_id]
            self.set_header("Content-Type", "{}; charset=UTF-8".format(page.content_type))
            self.write(page.content)
        except KeyError:
            self.set_status(404)


class LspPage:
    def __init__(self, page_id, content, content_type='js'):
        self.page_id = page_id
        self.content = content
        self.content_type = _content_types.get(content_type, content_type)


_content_types = {'html': 'text/html', 'js': 'text/javascript', 'json': 'application/json'}
