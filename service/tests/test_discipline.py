"""Conventions enforced as tests, in the spirit of the client's discipline test.

Each assertion here corresponds to a way this service could be quietly wrong in a
way no functional test would catch, because the code would keep working - just
not for the reason anybody intended.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

SERVICE = Path(__file__).resolve().parents[1]
MODULES = sorted(p for p in SERVICE.glob("*.py"))
REPO = SERVICE.parent


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def code_constants(path: Path) -> list[object]:
    """Every literal the module actually *uses*, excluding prose.

    Comments never reach the AST and docstrings are skipped explicitly, so this
    reads what the code does rather than what it says about itself. The
    distinction matters: a docstring explaining that the client downscales to 448
    is documentation, and ``imgsz = 448`` is a bug.
    """
    tree = ast.parse(source(path))

    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))

    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and id(node) not in docstrings
    ]


def test_there_are_modules_to_check():
    assert {p.name for p in MODULES} >= {
        "app.py", "pipeline.py", "artefacts.py", "colour.py", "shed.py", "wire.py", "settings.py"
    }


# --------------------------------------------------------------------------- #
# Nothing about the model is hard-coded
# --------------------------------------------------------------------------- #


def test_no_form_factor_name_appears_anywhere_in_the_service():
    """The detector's class list comes from the sidecar, in ONNX index order.

    A form-factor name written into this codebase is a second source of truth for
    something whose *order* is the ONNX class index - reordering it silently
    invalidates every deployed model. The service must never be able to disagree
    with the artefact about what class 3 is.
    """
    taxonomy = json.loads(
        (REPO / "data" / "taxonomy" / "waste-streams.json").read_text(encoding="utf-8")
    )
    names = {entry["id"] for entry in taxonomy["form_factors"]}

    for path in MODULES:
        used = {c for c in code_constants(path) if isinstance(c, str)}
        assert not (used & names), f"{path.name} names the form factor(s) {used & names}"


def test_no_stream_id_appears_anywhere_in_the_service():
    # Same argument. What a blue lid means lives in a region pack, and the
    # service's job is to look it up, never to know it.
    taxonomy = json.loads(
        (REPO / "data" / "taxonomy" / "waste-streams.json").read_text(encoding="utf-8")
    )
    # `unknown` is the designed no-answer state and names a concept, not a rule.
    ids = {entry["id"] for entry in taxonomy["streams"] if entry["id"] != "unknown"}

    for path in MODULES:
        used = {c for c in code_constants(path) if isinstance(c, str)}
        assert not (used & ids), f"{path.name} names the stream(s) {used & ids}"


def test_the_input_size_is_never_written_down():
    # 448 and 320 come from the sidecar. A model exported at a different size must
    # work by being deployed, not by being accompanied by a code change.
    sizes = {448, 320}
    for path in MODULES:
        used = {c for c in code_constants(path) if isinstance(c, int) and not isinstance(c, bool)}
        assert not (used & sizes), f"{path.name} hard-codes the input size {used & sizes}"


def test_the_resolver_is_imported_rather_than_reimplemented():
    """A third copy of the rules deciding what may be thrown where would be the
    worst possible place for drift. There are two: sbr.taxonomy and web/src/domain."""
    text = source(SERVICE / "pipeline.py")
    assert "from sbr.taxonomy import" in text

    for path in MODULES:
        body = source(path)
        assert "def resolve(" not in body, f"{path.name} defines its own resolve()"


# --------------------------------------------------------------------------- #
# Privacy, as a property of the source rather than a promise in a doc
# --------------------------------------------------------------------------- #

WRITE_CALLS = {"write_bytes", "write_text", "mkdir", "touch", "makedirs", "imwrite", "save"}


@pytest.mark.parametrize("module", ["pipeline.py", "app.py", "wire.py", "colour.py"])
def test_nothing_on_the_request_path_writes_a_file(module):
    """docs/01 § 7 and docs/03 § 4: frames are processed in memory and discarded.

    The consent lifecycle is not built, so nothing here could make retention
    lawful. A service that retained "just until the flow exists" is exactly what
    that paragraph was written to prevent, and this is the check that it has not
    happened by accident - a debug dump left in, say.
    """
    tree = ast.parse(source(SERVICE / module))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in WRITE_CALLS, (
                f"{module} calls {node.func.attr}() on the request path"
            )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "open", f"{module} calls open() on the request path"


def test_the_service_states_its_retention_publicly():
    # A claim nobody can check is a claim nobody should believe. /health says it.
    assert "retention" in source(SERVICE / "app.py")


# --------------------------------------------------------------------------- #
# The gates
# --------------------------------------------------------------------------- #


def test_only_artefacts_py_decides_whether_something_may_ship():
    # One place, so there is one thing to audit.
    for path in MODULES:
        if path.name == "artefacts.py":
            continue
        assert "may_ship" not in source(path), f"{path.name} reasons about may_ship"


def test_the_ungated_override_cannot_be_the_default():
    text = source(SERVICE / "settings.py")
    assert "allow_ungated: bool = False" in text


def test_forcing_crops_requires_the_ungated_flag():
    # SBR_FORCE_CROPS fabricates detections. On a real artefact that would be a
    # service inventing bins, so the two flags are welded together.
    text = source(SERVICE / "settings.py")
    assert "requires SBR_ALLOW_UNGATED" in text


# --------------------------------------------------------------------------- #
# Prose
# --------------------------------------------------------------------------- #


def test_comments_use_en_dashes_never_em_dashes():
    # The same rule the client's discipline test enforces, so the two codebases
    # read as one project.
    for path in MODULES:
        assert "—" not in source(path), f"{path.name} uses an em dash"
