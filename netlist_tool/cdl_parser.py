"""
CDL (.cdl) parser — closed-source-PDK companion to lib_parser.

CDL is a SPICE-subset format. For our purposes only three line kinds
matter:

    .SUBCKT <name> <pin1> <pin2> ...
    *.PININFO <pin>:<I|O|B> ...
    .ENDS

Everything else (transistor primitives, header comments, the `…`
placeholder used in stub files) is ignored.

The CDL format gives us pin direction but **none** of the metadata the
Liberty path derives from `function:` strings or `ff()`/`latch()`
groups. To classify buffers and sequential cells we read a sidecar JSON
file:

    {
      "buffers":    ["BUFF_TEST", "CLKBUF_X1"],
      "sequential": ["DFF_TEST",  "DLAT_TEST"]
    }

Auto-discovery: if the constructor is given a CDL path `foo.cdl` and no
explicit `cell_meta`, we look for `foo.cells.json` next to it. Names in
the sidecar that aren't in the parsed CDL produce a warning, not an
error (PDK / sidecar can drift independently).

Public API mirrors LibParser so graph_builder / inserter / main use it
through duck typing without modification.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .cell_info import CellInfo

# ---------------------------------------------------------------------------
# Direction mapping
# ---------------------------------------------------------------------------
# CDL collapses bias + supply + ground into one token. Mapping to "power"
# (Liberty's category) lets CellInfo.signal_pins() filter them out the
# same way it does for Liberty pg_pins.
_DIR_MAP = {"I": "input", "O": "output", "B": "power"}


# ---------------------------------------------------------------------------
# Line classifier
# ---------------------------------------------------------------------------
# CDL line-continuation marker `+` at start of a line is technically
# legal SPICE but the stubs we target keep .SUBCKT / *.PININFO on a
# single line, so we don't try to splice continuations.

_SUBCKT_RE = re.compile(r"^\s*\.SUBCKT\s+(\S+)\s*(.*)$", re.IGNORECASE)
_ENDS_RE = re.compile(r"^\s*\.ENDS\b", re.IGNORECASE)
_PININFO_RE = re.compile(r"^\s*\*\.PININFO\s+(.*)$", re.IGNORECASE)
_PIN_TOKEN_RE = re.compile(r"(\S+?):([IOB])\b")


def _scan(text: str) -> dict[str, CellInfo]:
    """Walk the CDL text line-by-line and build {name: CellInfo}."""
    cells: dict[str, CellInfo] = {}
    current: CellInfo | None = None

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue

        # Order matters: *.PININFO is a comment-prefixed directive, so
        # check it before generic comment skipping.
        m_pin = _PININFO_RE.match(line)
        if m_pin is not None:
            if current is None:
                continue  # stray PININFO outside a subckt; ignore
            for pin_name, code in _PIN_TOKEN_RE.findall(m_pin.group(1)):
                # First occurrence wins, matching lib_parser semantics.
                if pin_name not in current.pins:
                    current.pins[pin_name] = _DIR_MAP[code]
            continue

        # Comment line — skip.
        if line.lstrip().startswith("*"):
            continue

        m_sub = _SUBCKT_RE.match(line)
        if m_sub is not None:
            name = m_sub.group(1)
            current = cells.setdefault(name, CellInfo(name=name))
            # Seed pin order from the .SUBCKT port list; direction is
            # filled in by the subsequent *.PININFO line. If PININFO is
            # missing, pins remain with no direction entry, which is
            # fine — graph_builder falls back to its heuristic.
            continue

        if _ENDS_RE.match(line):
            current = None
            continue

        # Body line (transistor, .PARAM, …) — ignored.

    # EOF implicitly closes any still-open cell (TEST_CELLS.cdl is
    # missing the final .ENDS).
    return cells


# ---------------------------------------------------------------------------
# Sidecar classification
# ---------------------------------------------------------------------------


def _apply_meta(
    cells: dict[str, CellInfo],
    meta: dict,
    meta_source: str,
) -> None:
    """Set is_buf / is_seq flags from a sidecar dict. Warn on unknown names."""
    for key, attr in (("buffers", "is_buf"), ("sequential", "is_seq")):
        names = meta.get(key, []) or []
        if not isinstance(names, list):
            raise ValueError(
                f"{meta_source}: '{key}' must be a list, got {type(names).__name__}"
            )
        for name in names:
            cell = cells.get(name)
            if cell is None:
                print(
                    f"warning: {meta_source}: '{name}' listed under '{key}' "
                    f"but not present in the CDL",
                    file=sys.stderr,
                )
                continue
            setattr(cell, attr, True)


# ---------------------------------------------------------------------------
# CdlParser — public class
# ---------------------------------------------------------------------------


class CdlParser:
    """CDL file parser, duck-typed compatible with LibParser."""

    _CACHE_VERSION = 1

    def __init__(
        self,
        cdl_path: str | Path,
        cell_meta: str | Path | None = None,
    ) -> None:
        self.cdl_path = Path(cdl_path)
        if cell_meta is None:
            # Default sidecar: foo.cdl → foo.cells.json
            candidate = self.cdl_path.with_suffix(".cells.json")
            self.meta_path: Path | None = candidate if candidate.exists() else None
        else:
            self.meta_path = Path(cell_meta)
        self._db: dict[str, CellInfo] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, use_cache: bool = True) -> dict[str, CellInfo]:
        if self._db is not None:
            return self._db

        cache = self.cdl_path.with_suffix(self.cdl_path.suffix + ".json")
        if use_cache and cache.exists() and self._cache_is_fresh(cache):
            loaded = self._load_cache(cache)
            if loaded is not None:
                self._db = loaded
                return self._db

        text = self.cdl_path.read_text(encoding="utf-8", errors="replace")
        self._db = _scan(text)

        if self.meta_path is not None:
            meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
            _apply_meta(self._db, meta, str(self.meta_path))

        if use_cache:
            self._write_cache(cache)

        return self._db

    def get_pin_direction(self, cell_type: str, pin_name: str) -> str | None:
        cell = self.parse().get(cell_type)
        return cell.pins.get(pin_name) if cell else None

    def get_output_pins(self, cell_type: str) -> list[str]:
        cell = self.parse().get(cell_type)
        return cell.output_pins() if cell else []

    def get_input_pins(self, cell_type: str) -> list[str]:
        cell = self.parse().get(cell_type)
        return cell.input_pins() if cell else []

    def get_signal_pins(self, cell_type: str) -> dict[str, str]:
        cell = self.parse().get(cell_type)
        return cell.signal_pins() if cell else {}

    def cell_exists(self, cell_type: str) -> bool:
        return cell_type in self.parse()

    def summary(self) -> str:
        db = self.parse()
        lines = [
            f"CDL library     : {self.cdl_path.name}",
            f"Total cells     : {len(db)}",
            f"Total pins      : {sum(len(c.pins) for c in db.values())}",
            f"Buffers tagged  : {sum(1 for c in db.values() if c.is_buf)}",
            f"Sequential tag  : {sum(1 for c in db.values() if c.is_seq)}",
            "",
        ]
        for i, (name, cell) in enumerate(db.items()):
            if i >= 5:
                lines.append(f"  … and {len(db) - 5} more")
                break
            sig = cell.signal_pins()
            ins = [p for p, d in sig.items() if d == "input"]
            outs = [p for p, d in sig.items() if d == "output"]
            lines.append(f"  {name}: in={ins}  out={outs}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _cache_is_fresh(self, cache: Path) -> bool:
        ctime = cache.stat().st_mtime
        if ctime < self.cdl_path.stat().st_mtime:
            return False
        if self.meta_path is not None and self.meta_path.exists():
            if ctime < self.meta_path.stat().st_mtime:
                return False
        return True

    def _write_cache(self, path: Path) -> None:
        data = {
            "version": self._CACHE_VERSION,
            "cells": {
                name: {
                    "pins": cell.pins,
                    "is_seq": cell.is_seq,
                    "is_buf": cell.is_buf,
                }
                for name, cell in self._db.items()
            },
        }
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def _load_cache(cls, path: Path) -> dict[str, CellInfo] | None:
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or data.get("version") != cls._CACHE_VERSION:
            return None
        return {
            name: CellInfo(
                name=name,
                pins=entry.get("pins", {}),
                is_seq=entry.get("is_seq", False),
                is_buf=entry.get("is_buf", False),
            )
            for name, entry in data["cells"].items()
        }


# ---------------------------------------------------------------------------
# Stub-Liberty emitter
# ---------------------------------------------------------------------------
# Generates the minimal `.lib` Yosys needs to consume a CDL-only design
# under `read_liberty -ignore_miss_func`. Every cell becomes a black box
# with explicit pin directions; buffers (cells tagged `is_buf`) additionally
# carry `function : "<input_pin>"` so `equiv_induct` recognizes inserted
# buffer instances as identity stages. Sequential cells get no `ff()` block
# — their semantic equivalence is left to vendor LEC.


def emit_stub_lib(
    db: dict[str, CellInfo],
    out_path: str | Path,
    source_name: str = "stub",
) -> None:
    """Write a minimal Liberty stub from a parsed cell database.

    Used by both the CDL flow (input from CdlParser, function info comes
    from the sidecar's `is_buf` flag) and by Liberty round-trip tests
    (input from LibParser, function info comes from `pin_function`).

    Notes:
    - `is_buf` cells get `function : "<input_pin>"` on the single output.
    - Otherwise, any `pin_function` entry is emitted verbatim (Liberty
      round-trip). When neither is set, the output pin gets no function
      attribute and Yosys (with -ignore_miss_func) treats the cell as a
      blackbox.
    - Sequential cells are not given ff()/latch() blocks here; the CDL
      sidecar doesn't carry the clk/D mapping needed to synthesize them.
      For Liberty round-trip this means clk2fflogic won't recognize
      sequential cells from the stub.
    """
    lines: list[str] = []
    lines.append(f"/* Auto-generated from {source_name} — do not edit. */")
    lines.append("library (cdl_stub) {")
    for name, cell in db.items():
        lines.append(f"  cell ({name}) {{")
        outs = cell.output_pins()
        single_in = (
            cell.input_pins()[0]
            if cell.is_buf and len(cell.input_pins()) == 1
            else None
        )
        for pin, direction in cell.pins.items():
            stub_dir = direction if direction in ("input", "output", "inout") else "input"
            func: str | None = None
            if direction == "output":
                if cell.is_buf and single_in is not None and pin in outs:
                    func = single_in
                elif pin in cell.pin_function and not cell.is_seq:
                    # Skip function: on sequential cells — Liberty
                    # functions of an FF output reference internal ff()
                    # nodes (e.g. "IQ") that we don't emit, so Yosys
                    # would fail to resolve them. Drop the function and
                    # let -ignore_miss_func black-box the cell.
                    func = cell.pin_function[pin]
            if func is not None:
                lines.append(f"    pin ({pin}) {{")
                lines.append(f"      direction : {stub_dir};")
                lines.append(f'      function  : "{func}";')
                lines.append("    }")
            else:
                lines.append(f"    pin ({pin}) {{ direction : {stub_dir}; }}")
        lines.append("  }")
    lines.append("}")
    Path(out_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI entry: python -m netlist_tool.cdl_parser --emit-stub-lib FILE.cdl -o OUT
# ---------------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        prog="python -m netlist_tool.cdl_parser",
        description="CDL parser utilities (stub-.lib emitter).",
    )
    ap.add_argument(
        "--emit-stub-lib",
        type=Path,
        metavar="CDL",
        required=True,
        help="CDL file to read.",
    )
    ap.add_argument(
        "--cell-meta",
        type=Path,
        default=None,
        metavar="JSON",
        help="Sidecar classification JSON (defaults to <cdl_stem>.cells.json).",
    )
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        metavar="LIB",
        help="Destination path for the stub Liberty file.",
    )
    args = ap.parse_args(argv)

    parser = CdlParser(args.emit_stub_lib, cell_meta=args.cell_meta)
    db = parser.parse()
    emit_stub_lib(db, args.output, source_name=parser.cdl_path.name)
    print(
        f"Wrote {args.output} ({len(db)} cells, "
        f"{sum(1 for c in db.values() if c.is_buf)} buffer(s) with function attr)"
    )
    return 0


if __name__ == "__main__":
    import sys as _sys

    _sys.exit(_main())
