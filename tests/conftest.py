import json
import os
from pathlib import Path

import pytest

from mozilla_pipeline_schemas.bigquery import resolve_ref
from mozilla_pipeline_schemas.utils import get_repository_root, run

ROOT = get_repository_root()
SCHEMAS_ROOT = ROOT / "schemas"
VALIDATION_ROOT = ROOT / "validation"
JARS_ROOT = ROOT / "target"


@pytest.fixture()
def schemas_root():
    return SCHEMAS_ROOT


@pytest.fixture()
def validation_root():
    return VALIDATION_ROOT


@pytest.fixture()
def jars_root():
    return JARS_ROOT


def load_schemas():
    """Load all the schemas under the `schemas` folder."""
    schemas = {}
    for path in SCHEMAS_ROOT.glob("**/*.schema.json"):
        assert (
            len(path.relative_to(ROOT).parts) <= 4
        ), f"schemas directory too deep: {path}"
        # Using the path parts allows proper handling of schemas that are not
        # placed in the expected directory structure, like pioneer-study.
        #
        #   >>> path.relative_to(ROOT).parts
        #   ('validation', 'pocket', 'fire-tv-events.1.sample.pass.json')
        #
        # https://docs.python.org/3/library/pathlib.html#accessing-individual-parts
        namespace = path.relative_to(ROOT).parts[1]
        doctype, version = path.name.split(".")[:2]
        qualifier = f"{namespace}.{doctype}.{version}"
        with path.open() as fp:
            schemas[qualifier] = json.load(fp)
    return schemas


def load_examples():
    """Load all the examples under the `validation` folder."""
    examples = {"pass": {"params": [], "ids": []}, "fail": {"params": [], "ids": []}}
    for path in sorted(VALIDATION_ROOT.glob("**/*.json")):
        assert (
            len(path.relative_to(ROOT).parts) == 3
        ), f"validation directory structure invalid: {path}"
        namespace = path.relative_to(ROOT).parts[1]
        try:
            doctype, version, _, expect, _ = path.name.split(".")
        except ValueError:
            raise ValueError(
                "validation example name must match "
                "'{doctype}.{version}.{validation_reason}.{pass|fail}.json', "
                f"got: {path.name}"
            )
        assert expect in ("pass", "fail"), f"unknown example type: {path.name}"
        qualifier = f"{namespace}.{doctype}.{version}"

        with path.open() as fp:
            example = json.load(fp)

        examples[expect]["params"].append((qualifier, example))
        examples[expect]["ids"].append(f"{namespace}/{path.name}")

    return examples


@pytest.fixture()
def schemas():
    return load_schemas()


def pytest_generate_tests(metafunc):
    """Generate tests for validating schemas against examples.

    Run the tests for this function in `scripts/test-pytest-generation`.

    See: https://docs.pytest.org/en/2.8.7/parametrize.html#the-metafunc-object
    """
    examples = load_examples()

    # inject parameters into the relevant tests
    for expect, examples in examples.items():
        if f"{expect}ing_example" in metafunc.fixturenames:
            metafunc.parametrize(
                ["qualifier", f"{expect}ing_example"],
                examples["params"],
                ids=examples["ids"],
            )


@pytest.fixture
def tmp_git(tmp_path: Path) -> Path:
    """Copy the entire repository with the current revision.

    To check the state of a failed test, change directories to the temporary
    directory surfaced by pytest.
    """
    curdir = os.getcwd()
    origin = ROOT
    workdir = tmp_path / "mps"
    resolved_head_ref = resolve_ref("HEAD")

    run(f"git clone {origin} {workdir}")
    os.chdir(workdir)
    # make branches available by checking them out, but ensure state ends up on HEAD
    run(f"git checkout main")
    run(f"git checkout {resolved_head_ref}")
    yield workdir
    os.chdir(curdir)
