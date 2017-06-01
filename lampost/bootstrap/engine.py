import os

from lampost.db import dbconfig
from lampost.db import permissions
from lampost.db.redisstore import RedisStore
from lampost.event.system import dispatcher
from lampost.gameops import friend
from lampost.di import resource, config
from lampost.server import session as session_manager
from lampost.service import email as email_sender
from lampost.service import message
from lampost.server import services
from lampost.server.link import add_link_module, add_link_route
from lampost.user import add_player_targets, settings
from lampost.service.channel import ChannelService
from lampost.user import manage as user_manager
from lampost.util import json

from lampost.server import web
from lampost.server.link import LinkHandler
from lampost.server.services import AnyLoginService, PlayerListService, EditUpdateService
from lampost.server.web import NoCacheStaticHandler

from lampost.util.logging import get_logger
from tornado.ioloop import IOLoop
from tornado.web import RedirectHandler, StaticFileHandler


def start_core_services(args):
    json.select_json()

    datastore = resource.register('datastore', RedisStore(args.db_host, args.db_port, args.db_num, args.db_pw))
    db_config = datastore.load_object(args.config_id, dbconfig.Config)
    config.activate(db_config.section_values)

    resource.register('dispatcher', dispatcher)
    resource.register('perm', permissions)
    resource.register('user_manager', user_manager)
    resource.register('session_manager', session_manager)


def start_app_services():
    resource.register('email_sender', email_sender)
    resource.register('channel_service', ChannelService())
    resource.register('friend_service', friend)
    resource.register('message_service', message)
    resource.register('player_list_service', PlayerListService())
    resource.register('login_notify_service', AnyLoginService())
    resource.register('edit_update_service', EditUpdateService())

    add_player_targets()


def start_server(args):
    add_link_route('register_service', services.register_service)
    add_link_route('unregister_service', services.unregister_service)
    add_link_module(settings)

    tornado_logger = get_logger('tornado.general')
    tornado_logger.setLevel(args.log_level.upper())
    tornado_logger = get_logger('tornado.access')
    tornado_logger.setLevel(args.log_level.upper())
    web.service_root = args.service_root
    if args.web_files:
        web.add_raw_route("/", RedirectHandler, url="/webclient/lampost.html")
        web.add_raw_route("/webclient/(lampost\.html)", NoCacheStaticHandler, path=os.path.abspath(args.web_files))
        web.add_raw_route("/webclient/(.*)", StaticFileHandler, path=os.path.abspath(args.web_files))
    web.add_raw_route("/link", LinkHandler)
    web.start_service(args.port, args.server_interface)

    IOLoop.instance().start()
