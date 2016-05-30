import sys
import importlib.abc
import importlib.machinery

from lampost.di.resource import module_inject

_original_finder = sys.meta_path[-1]


class LampostFinder(_original_finder):
    def find_spec(self, fullname, path, target=None):
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if not spec:
            return None
        if type(spec.loader).__name__ == 'SourceFileLoader':
            spec.loader.__class__ = LampostLoader
        return spec


class LampostLoader(importlib.machinery.SourceFileLoader):
    def exec_module(self, module):
        super().exec_module(module)
        module_inject(module.__name__)


sys.meta_path.insert(-1, LampostFinder())
