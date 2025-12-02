"""Algorithms Package - Self-contained anomaly detection algorithms.

Each algorithm registers itself via @register_algorithm decorator.
This package auto-discovers and imports all algorithm modules.

To add a new algorithm:
1. Create a new file in this folder (e.g., my_algo.py)
   OR create a subfolder with same-named file (e.g., my_algo/my_algo.py)
2. Use @register_algorithm decorator on your class

That's it! The algorithm will be auto-discovered and available across the entire stack.
No __init__.py needed in subfolders!
"""

import importlib
import pkgutil
from pathlib import Path

# Auto-discover and import all algorithm modules
_package_dir = Path(__file__).parent

# 1. Import single-file algorithms (e.g., iqr.py, mock.py)
for _module_info in pkgutil.iter_modules([str(_package_dir)]):
    if _module_info.name.startswith('_'):
        continue
    if not _module_info.ispkg:
        importlib.import_module(f".{_module_info.name}", __package__)

# 2. Import subfolder algorithms (e.g., zscore/zscore.py) - no __init__.py needed
for _subdir in _package_dir.iterdir():
    if _subdir.is_dir() and not _subdir.name.startswith('_'):
        _main_module = _subdir / f"{_subdir.name}.py"
        if _main_module.exists():
            importlib.import_module(f".{_subdir.name}.{_subdir.name}", __package__)
