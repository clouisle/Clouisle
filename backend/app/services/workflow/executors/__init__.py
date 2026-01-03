"""
Executors package.

Auto-imports all executor modules to register them.
"""

# Import all executors to register them
from . import start
from . import answer
from . import llm
from . import condition
from . import code
from . import template
from . import variable
from . import iteration
from . import tool
from . import subworkflow
from . import knowledge

__all__ = [
    "start",
    "answer",
    "llm",
    "condition",
    "code",
    "template",
    "variable",
    "iteration",
    "tool",
    "subworkflow",
    "knowledge",
]
