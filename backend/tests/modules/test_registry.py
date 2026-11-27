import importlib
import importlib.util
from pathlib import Path

import pytest

from app.modules import registry

pytestmark = pytest.mark.unit
MIGRATION = Path(__file__).resolve().parents[2] / "migrations/versions/b01_01_extensions_schemas.py"


def load_migration_schemas() -> tuple[str, ...]:
    spec = importlib.util.spec_from_file_location("b01_01", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return tuple(module.SCHEMAS)


def test_sixteen_modules_with_unique_codes_and_schemas() -> None:
    assert len(registry.MODULES) == 16
    assert len({m.code for m in registry.MODULES}) == 16
    assert len(set(registry.SCHEMAS)) == 16


def test_registry_schemas_equal_first_migration() -> None:
    assert load_migration_schemas() == registry.SCHEMAS


def test_every_module_package_exists_with_constants() -> None:
    for info in registry.MODULES:
        module = registry.load(info)
        assert info.code == module.CODE
        assert info.schema == module.SCHEMA


def test_off_has_no_package() -> None:
    assert importlib.util.find_spec("app.modules.off") is None
    assert "OFF" not in {m.code for m in registry.MODULES}


def test_hooks_collect_without_error() -> None:
    assert isinstance(registry.all_routers(), list)
    assert isinstance(registry.all_job_handlers(), dict)
    registry.load_models()
