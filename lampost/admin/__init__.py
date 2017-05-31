import importlib

from lampost.admin.ops import admin_operation
from lampost.server.link import add_link_route


def enable_admin_ops():
    importlib.import_module('lampost/admin/dbops')
    add_link_route('admin/operation', admin_operation, 'supreme')
