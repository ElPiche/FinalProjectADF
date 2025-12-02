"""Algorithms Package - Self-contained anomaly detection algorithms.

Each algorithm is in its own file and registers itself via @register_algorithm.
Just import this package to register all algorithms.

To add a new algorithm:
1. Create a new file in this folder (e.g., my_algo.py)
2. Use @register_algorithm decorator on your class
3. Import it in this __init__.py

That's it! The algorithm will be available across the entire stack.
"""

# Import all algorithms to trigger registration
from .zscore import ZScoreAlgorithm
from .mock import MockAlgorithm
from .iqr import IQRAlgorithm
