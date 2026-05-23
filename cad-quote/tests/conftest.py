"""使 ``cad-quote`` 目录下的 ``app`` 包可作为顶层模块被测试发现。"""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(ROOT)
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)
