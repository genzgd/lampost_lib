from lampost.di.resource import Injected, module_inject

perm = Injected('perm')
module_inject(__name__)


def immortal_list(**_):
    return ([{'dbo_id': key, 'name': key, 'imm_level': value, 'dbo_key_type': 'immortal'} for key, value in
             perm.immortals.items()])
