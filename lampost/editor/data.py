from lampost.di.resource import Injected
from lampost.server.link import link_route

perm = Injected('perm')


@link_route('editor/immortal/list')
def immortal_list(**_):
    return ([{'dbo_id': key, 'name': key, 'imm_level': value, 'dbo_key_type': 'immortal'} for key, value in
             perm.immortals.items()])
