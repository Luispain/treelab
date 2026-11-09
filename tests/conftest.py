"""Shared pytest configuration and cleanup for the treelab test suite.

The noder library bundles its own HDF5 C extension.  On Python 3.8 and 3.10
the interpreter shutdown order of C extensions is non-deterministic, which can
trigger a ``munmap_chunk(): invalid pointer`` segfault after pytest completes.
This module provides fixtures that explicitly release HDF5/noder resources
before the shutdown sequence begins.
"""

from __future__ import annotations

import gc
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(autouse=True)
def _hdf5_cleanup():
    """Release HDF5/noder resources after every test."""
    yield
    # Force a full garbage collection pass so that any numpy arrays or Python
    # objects that reference HDF5-allocated memory are freed *before* the
    # interpreter starts its shutdown sequence.
    gc.collect()


@pytest.fixture(scope="session", autouse=True)
def _hdf5_session_cleanup():
    """Final cleanup at session end to prevent segfaults at process exit."""
    yield
    gc.collect()
