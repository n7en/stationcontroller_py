"""
Root conftest - registers the 'hardware' pytest mark and the --hardware CLI flag.

Hardware tests are skipped by default. To run them:

    pytest --hardware

To run only hardware tests:

    pytest --hardware -m hardware

To run only simulation tests (the default):

    pytest
"""
import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--hardware",
        action="store_true",
        default=False,
        help="Run hardware integration tests against physical devices",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "hardware: marks tests that require physical DCN hardware to be connected",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--hardware"):
        return  # run everything when flag is present

    skip_hw = pytest.mark.skip(reason="hardware tests require --hardware flag")
    for item in items:
        if "hardware" in item.keywords:
            item.add_marker(skip_hw)
