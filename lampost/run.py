from lampost.server import services
from lampost.server.link import add_link_module, add_link_route
from lampost.user import add_player_targets, settings


def add_common_routes():
    add_link_route('register_service', services.register_service)
    add_link_route('unregister_service', services.unregister_service)
    add_link_module(settings)


def enable_game_ops():
    add_player_targets()
