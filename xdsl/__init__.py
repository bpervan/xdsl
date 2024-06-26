from collections.abc import Sequence
from itertools import chain
from types import ModuleType
from typing import Any

from xdsl.dialects import get_all_dialects
from xdsl.traits import SymbolTable
from xdsl.utils.dialect_stub import DialectStubGenerator

from . import _version

__version__ = _version.get_versions()["version"]

import importlib.abc
import importlib.util
import os
import sys


class IRDLDialectLoader(importlib.abc.Loader):
    """
    Custom module loader for IRDL files.

    When loading an irdl file as a module:
    - parse the dialect
    - generate its PyRDL implementation
    - generate type stubs for its implmentation and write to disk
    - populate the Python module
    """

    def __init__(self, module_name: str, path: str):
        self.module_name = module_name
        self.path = path

    def exec_module(self, module: ModuleType):
        from xdsl.context import MLContext
        from xdsl.dialects.irdl import DialectOp
        from xdsl.interpreters.irdl import make_dialect
        from xdsl.parser import Parser

        # Open the irdl file
        with open(self.path) as file:
            # Parse it
            ctx = MLContext()
            for dialect_name, dialect_factory in get_all_dialects().items():
                ctx.register_dialect(dialect_name, dialect_factory)
            irdl_module = Parser(ctx, file.read(), self.path).parse_module()

            # Make it a PyRDL Dialect
            filename = os.path.basename(self.path)
            dialect_name, _ = os.path.splitext(filename)
            dialect_op = SymbolTable.lookup_symbol(irdl_module, dialect_name)
            assert isinstance(dialect_op, DialectOp)
            dialect = make_dialect(dialect_op)
            with open(
                f"{os.path.dirname(self.path)}/{dialect_name}.pyi", "w"
            ) as stubfile:
                print(
                    f"""\
""\"
This file is automatically generated by xDSL and not meant to be modified.

It was generated from {self.path}
""\"
""",
                    file=stubfile,
                )
                print(
                    DialectStubGenerator(dialect).generate_dialect_stubs(),
                    file=stubfile,
                )

            for obj in chain(dialect.attributes, dialect.operations):
                setattr(module, obj.__name__, obj)
            setattr(module, dialect.name.capitalize(), dialect)


class IRDLDialectFinder(importlib.abc.MetaPathFinder):
    """
    Custom module finder for IRDL files.

    Look for a <name>.irdl file instead of a <name>.py file.

    """

    def find_spec(self, fullname: str, path: Sequence[str] | None, target: Any = None):
        # Check if module is already loaded and return it if so
        if fullname in sys.modules:
            return sys.modules[fullname].__spec__

        # Look for the file
        filename = fullname.split(".")[-1] + ".irdl"
        if path is None:
            path = [os.getcwd()]
        for entry in path:
            potential_path = os.path.join(entry, filename)
            if os.path.isfile(potential_path):
                # If found, create the right loader and return it
                loader = IRDLDialectLoader(fullname, potential_path)
                return importlib.util.spec_from_file_location(
                    fullname, potential_path, loader=loader
                )

        # Return None if not found to let importlib do its thing.
        return None


# Add the IRDLDialectFinder to the meta path as last resort, i.e, it will look for a
# .irdl implementation if no .py implementation is found.
sys.meta_path.append(IRDLDialectFinder())
