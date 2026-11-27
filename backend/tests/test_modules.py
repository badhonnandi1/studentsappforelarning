import importlib
import importlib.util
from pathlib import Path

from app.modules.registry import CLIENT_OWNED, SCHEMAS, SERVER_MODULES

MIGRATION = Path(__file__).parents[1] / "migrations" / "versions" / "0001_module_schemas.py"


def test_seventeen_modules_accounted_for() -> None:
    codes = {m.code for m in SERVER_MODULES} | set(CLIENT_OWNED)
    assert len(SERVER_MODULES) == 16
    assert codes == {
        "AUTH",
        "TAX",
        "QB",
        "CMS",
        "PRAC",
        "EXAM",
        "ANL",
        "AI",
        "GAM",
        "PLAN",
        "COM",
        "PAR",
        "INST",
        "PAY",
        "OFF",
        "OPS",
        "NFR",
    }
    assert len(set(SCHEMAS)) == 16


def test_each_server_module_is_importable_and_declares_its_schema() -> None:
    for module in SERVER_MODULES:
        package = importlib.import_module(module.package)
        assert module.code == package.CODE
        assert module.schema == package.SCHEMA
        assert package.__doc__, f"{module.package} needs a description"
        importlib.import_module(f"{module.package}.internal")


def test_off_is_client_owned_without_a_package() -> None:
    assert "OFF" in CLIENT_OWNED
    assert importlib.util.find_spec("app.modules.off") is None


def test_migration_creates_exactly_the_registry_schemas() -> None:
    spec = importlib.util.spec_from_file_location("migration_0001", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert tuple(migration.SCHEMAS) == SCHEMAS
