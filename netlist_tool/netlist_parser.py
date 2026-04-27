"""
----------
Philippe Logoz verilog netlist parser
27.04.2026 @ 15h30
----------
"""

import json
import re

import pyparsing as pp

pp.ParserElement.enablePackrat()

# Comment stripping
_COMMENT = pp.cpp_style_comment | pp.Regex(r"")


def _strip_comments(text: str) -> str:
    return _COMMENT.transform_string(text)
