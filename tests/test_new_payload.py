from __future__ import annotations

import numpy as np
import pytest

from treelab.gui.new_payload import PayloadExpressionError, evaluate_payload_expression


def test_new_payload_evaluates_numpy_expression():
    result = evaluate_payload_expression(
        "np.linspace(0, 1, 11) + 2",
        lambda _filename, _path: np.array([]),
    )

    np.testing.assert_allclose(result, np.linspace(0, 1, 11) + 2)


def test_new_payload_resolves_and_slices_referenced_arrays():
    payload = np.arange(15, dtype=float).reshape(3, 5)

    def resolve(filename, path):
        assert filename == "polar_HVAB_elsa.cgns"
        assert path == "Base/zone/FlowSolution/CL"
        return payload

    result = evaluate_payload_expression(
        '"{polar_HVAB_elsa.cgns@Base/zone/FlowSolution/CL}"[:, 2] / '
        '"{polar_HVAB_elsa.cgns@Base/zone/FlowSolution/CL}"[:, 2]',
        resolve,
    )

    np.testing.assert_array_equal(result, np.ones(3))


def test_new_payload_accepts_documented_double_brace_reference_form():
    result = evaluate_payload_expression(
        '"{{file.cgns}@{Base/Values}}" + 1',
        lambda filename, path: np.array([4, 5]),
    )

    np.testing.assert_array_equal(result, np.array([5, 6]))


def test_new_payload_none_removes_payload():
    assert evaluate_payload_expression("None", lambda *_args: np.array([])) is None


def test_new_payload_rejects_python_builtins():
    with pytest.raises(PayloadExpressionError, match="Only calls"):
        evaluate_payload_expression("__import__('os')", lambda *_args: np.array([]))
