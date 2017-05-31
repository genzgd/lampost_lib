from lampost.editor import data, session, events
from lampost.editor.players import PlayerEditor, UserEditor
from lampost.server.link import add_link_module, add_link_object


def add_common_routes():
    add_link_module(data)
    add_link_module(session)
    add_link_object('editor/player', PlayerEditor())
    add_link_object('editor/user', UserEditor())


def register_editor_events():
    events.register()
