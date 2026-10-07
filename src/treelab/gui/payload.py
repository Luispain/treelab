"""Payload markers and bounded payload-table helpers.

The marker formatting intentionally follows the compact marker used by
Noder's ``cgnsviz`` terminal model.  In particular, asking the Qt model for a
row summary never loads a lazy payload.
"""

from __future__ import annotations

import math
import re

import numpy as np


UNLOADED_MARKER = "Press F5 for load data"
PAYLOAD_ELEMENT_LIMIT = 20_000
MARKER_ELEMENT_LIMIT = 64
MAX_MARKER_CHARS = 80


def _compact_string(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _short_word(word: str) -> str:
    return word if len(word) <= 24 else word[:21] + "..."


def _string_marker(value: str) -> str:
    compact = _compact_string(value)
    if len(value) <= MAX_MARKER_CHARS:
        return compact
    words = value.split()
    if not words:
        return "big str: 0 words"
    first = _short_word(words[0])
    last = _short_word(words[-1])
    if len(words) == 1:
        return f'big str: 1 words "{first}"'
    return f'big str: {len(words)} words "{first} ... {last}"'


def _number(value) -> str:
    """Match cgnsviz's compact six-significant-digit numeric formatting."""
    if isinstance(value, (bool, np.bool_)):
        return "1" if value else "0"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    value = float(value)
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "-inf" if value < 0 else "inf"
    return format(value, ".6g")


def _numerical_summary(array: np.ndarray) -> str:
    if array.size == 0:
        return "empty array"
    values = np.asarray(array).reshape(-1)
    if np.issubdtype(values.dtype, np.floating) and np.isnan(values).any():
        return "mn=nan MX=nan avg=nan med=nan"
    # The C++ implementation sorts before selecting min/max/median.  This is
    # deliberately done on a bounded copy only after the payload is loaded.
    sorted_values = np.sort(values)
    median = np.median(sorted_values)
    return (
        f"mn={_number(sorted_values[0])} MX={_number(sorted_values[-1])} "
        f"avg={_number(np.mean(values))} med={_number(median)}"
    )


def _array_kind(data, array: np.ndarray) -> str:
    try:
        dtype = data.dtype()
    except Exception:
        dtype = str(array.dtype)
    return np.asarray(array).dtype.kind if dtype else np.asarray(array).dtype.kind


def payload_marker(node) -> str:
    """Return the marker text shown in the Qt tree's Payload column."""
    try:
        if not node.has_data():
            return ""
        loaded = getattr(node, "data_is_loaded", lambda: True)()
        if not loaded:
            return UNLOADED_MARKER
        data = node.data()
        if data is None or data.isNone():
            return ""
        if data.hasString():
            return _string_marker(data.extractString())

        array = np.asarray(data.getPyArray())
        kind = _array_kind(data, array)
        if kind in "biuf":
            if data.size() <= 9:
                return f"Array {data.dtype()} {data.getPrintString(0)}"
            return _numerical_summary(array)
        if data.size() > MARKER_ELEMENT_LIMIT:
            return ""
        return data.short_info() if data.isScalar() else ""
    except Exception:
        # A closed reader or an unsupported third-party Data implementation
        # must not make Qt's paint path fail.
        return ""


def payload_array(node):
    """Return a loaded node payload as a NumPy array, or ``None``."""
    data = node.data()
    if data is None or data.isNone():
        return None
    if data.hasString():
        return np.asarray(data.getPyArray())
    return np.asarray(data.getPyArray())
