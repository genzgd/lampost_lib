from collections import defaultdict

from lampost.di.resource import Injected, module_inject
from lampost.db.dbo import DBOField, ParentDBO, ChildDBO, CoreDBO

log = Injected('log')
db = Injected('datastore')
module_inject(__name__)


def create(config_id, raw_configs, set_defaults=False):
    sections = {}
    all_values = defaultdict(set)

    def init_section(section_name, section_dto=None):
        try:
            return sections[section_name]
        except KeyError:
            section_dto = section_dto or {}
            section_dto['dbo_id'] = '{}:{}'.format(config_id, section_name)
            section = db.create_object(ConfigSection, section_dto)
            sections[section_name] = section
            return section

    def add_raw(raw_config):
        for section_name, section_dto in raw_config.pop('sections', {}).items():
            init_section(section_name, section_dto)

        for section_name, settings in raw_config.items():
            section = init_section(section_name)
            setting_map = {setting.name: setting for setting in section.settings}
            for raw_setting in settings:
                setting = Setting().hydrate(raw_setting)
                if set_defaults:
                    setting.default = setting.value
                try:
                    existing = setting_map[setting.name]
                    log.warn("Setting {} with value {} overwritten by {}", setting.name, existing.value, setting.value)
                except KeyError:
                    pass
                setting_map[setting.name] = setting
                all_values[setting.name].add(section_name)
            section.settings = setting_map.values()
            db.save_object(section)

    for rc in raw_configs:
        add_raw(rc)

    for setting_name, section_names in all_values.items():
        if len(section_names) > 1:
            log.warn("Setting name {} found in multiple sections: {}", setting_name, ' '.join(section_names))

    return db.create_object(Config, {'dbo_id': config_id})


class Config(ParentDBO):
    dbo_key_type = 'config'
    dbo_set_key = 'configs'

    dbo_children_types = ['c_sect']

    def update_value(self, section, name, value):
        section = db.load_object('c_sect:{}:{}'.format(self.dbo_id, section))
        if section:
            self.section_values['{}:{}'.format(section, name)] = value
            for setting in section.settings:
                if setting.name == name:
                    setting.value = value
                    db.save_object(section)
                    return
        log.error("No setting found for {}:{}".format(section, name))

    def on_loaded(self):
        self.section_values = {}
        self.exports = {}
        for child_key in self.dbo_child_keys('c_sect'):
            section = db.load_object(child_key, ConfigSection)
            if section:
                for setting in section.settings:
                    self.section_values['{}:{}'.format(section.child_id, setting.name)] = setting.value


class ConfigSection(ChildDBO):
    dbo_key_type = 'c_sect'
    dbo_parent_type = 'config'

    desc = DBOField()
    editor_constants = DBOField(False)
    settings = DBOField([], 'setting')


class Setting(CoreDBO):
    class_id = 'setting'
    name = DBOField()
    value = DBOField()
    desc = DBOField()
    default = DBOField()
    data_type = DBOField()
    min_value = DBOField()
    max_value = DBOField()
    step = DBOField(1)
    export = DBOField(False)
