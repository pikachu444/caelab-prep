"""The reusable core imports without an application, solver, UI or test host."""
import subprocess
import sys


def test_core_imports_with_host_dependencies_blocked():
    code = """
import importlib.abc
import sys
class Fence(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.startswith(('PySide6', 'vtk', 'gmsh', 'caelab_prep.radioss',
                                'caelab_prep.ui', 'caelab_prep.application', 'tests', 'scripts')):
            raise AssertionError(fullname)
sys.meta_path.insert(0, Fence())
from caelab_prep.cae_core import Document, CommandDispatcher, Resource, PrepError
assert Document("Independent core").revision == 0
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
