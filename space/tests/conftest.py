"""Shared fixtures. The Dataset repo files (question.schema.json, categories.json, QUESTION_GUIDE.md) live in a
different repository; point TDA_DATASET_DIR at a checkout of it (default: ../dataset next to this Space)."""
import copy
import os
import pathlib
import sys

import pytest

SPACE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SPACE))
DATASET_DIR = pathlib.Path(os.environ.get("TDA_DATASET_DIR", SPACE.parent / "dataset"))
FIXTURES = SPACE / "tests" / "fixtures"
RUN_SCHEMA = SPACE / "tda_eval" / "schemas" / "run_report.schema.json"

from tda_eval.validators import load_json, load_jsonl, make_validator  # noqa: E402


def pytest_sessionstart(session):
    missing = [n for n in ("question.schema.json", "categories.json", "QUESTION_GUIDE.md")
               if not (DATASET_DIR / n).exists()]
    if missing:
        pytest.exit(f"Dataset files not found in {DATASET_DIR}: {missing}. Set TDA_DATASET_DIR.", returncode=3)


@pytest.fixture(scope="session")
def qschema():
    return load_json(DATASET_DIR / "question.schema.json")


@pytest.fixture(scope="session")
def rschema():
    return load_json(RUN_SCHEMA)


@pytest.fixture(scope="session")
def cats():
    return load_json(DATASET_DIR / "categories.json")


@pytest.fixture(scope="session")
def qvalidator(qschema):
    return make_validator(qschema)


@pytest.fixture(scope="session")
def rvalidator(rschema):
    return make_validator(rschema)


@pytest.fixture(scope="session")
def samples():
    return load_jsonl(FIXTURES / "sample_questions.jsonl")


@pytest.fixture(scope="session")
def by_id(samples):
    return {q["id"]: q for q in samples}


@pytest.fixture(scope="session")
def ref_solutions():
    return load_json(FIXTURES / "reference_solutions.json")


@pytest.fixture
def clone():
    return copy.deepcopy
