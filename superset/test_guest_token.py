import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


EMBEDDED_ID = "d8755a51-1984-451b-9bd1-8a5f220ed205"


class SqlaTable:
    def __init__(self, dataset_id=7, columns=("partner_id",)):
        self.id = dataset_id
        self.table_name = "metrics"
        self.sql = None
        self.columns = [types.SimpleNamespace(column_name=name) for name in columns]


class EmbeddedDashboard:
    pass


class Query:
    def __init__(self, embedded):
        self.embedded = embedded

    def filter_by(self, **kwargs):
        return self

    def one_or_none(self):
        return self.embedded


class GuestTokenValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        environment = {
            "SUPERSET_SECRET_KEY": "test-only",
            "SUPERSET_GUEST_TOKEN_JWT_SECRET": "test-only",
            "SUPERSET_DB_PASSWORD": "test-only",
        }
        with patch.dict(os.environ, environment):
            spec = importlib.util.spec_from_file_location(
                "local_superset_config", Path(__file__).with_name("superset_config.py")
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        cls.validate = staticmethod(module.validate_telemetry_guest_token)

    def setUp(self):
        self.datasource = SqlaTable()
        self.embedded = types.SimpleNamespace(
            dashboard=types.SimpleNamespace(datasources={self.datasource})
        )
        database = types.SimpleNamespace(
            session=types.SimpleNamespace(
                query=lambda model: Query(self.embedded)
            )
        )
        modules = {
            "superset": types.ModuleType("superset"),
            "superset.connectors": types.ModuleType("superset.connectors"),
            "superset.connectors.sqla": types.ModuleType("superset.connectors.sqla"),
            "superset.connectors.sqla.models": types.ModuleType(
                "superset.connectors.sqla.models"
            ),
            "superset.extensions": types.ModuleType("superset.extensions"),
            "superset.models": types.ModuleType("superset.models"),
            "superset.models.embedded_dashboard": types.ModuleType(
                "superset.models.embedded_dashboard"
            ),
        }
        modules["superset.connectors.sqla.models"].SqlaTable = SqlaTable
        modules["superset.extensions"].db = database
        modules["superset.models.embedded_dashboard"].EmbeddedDashboard = (
            EmbeddedDashboard
        )
        self.modules = patch.dict(sys.modules, modules)
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.environment = patch.dict(os.environ, {
            "TELEMETRY_OVERVIEW_EMBEDDED_ID": EMBEDDED_ID,
            "TELEMETRY_OVERVIEW_DATASET_ID": "7",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def body(self):
        return {
            "user": {"username": "15"},
            "resources": [{"type": "dashboard", "id": EMBEDDED_ID}],
            "rls": [{"dataset": 7, "clause": "partner_id = 1"}],
        }

    def test_valid_dashboard_and_rls(self):
        self.assertTrue(self.validate(self.body()))

    def test_wrong_or_missing_dataset_never_issues_token(self):
        for rules in ([], [{"dataset": 8, "clause": "partner_id = 1"}]):
            with self.subTest(rules=rules):
                body = self.body()
                body["rls"] = rules
                self.assertFalse(self.validate(body))
        self.datasource.id = 8
        self.assertFalse(self.validate(self.body()))

    def test_dashboard_change_or_missing_partner_column_fails(self):
        self.embedded.dashboard.datasources.add(SqlaTable(dataset_id=8))
        self.assertFalse(self.validate(self.body()))
        self.embedded.dashboard.datasources = {SqlaTable(columns=("metric",))}
        self.assertFalse(self.validate(self.body()))
        self.datasource = SqlaTable()
        self.datasource.sql = "SELECT * FROM telemetry.metrics"
        self.embedded.dashboard.datasources = {self.datasource}
        self.assertFalse(self.validate(self.body()))

    def test_invalid_clause_or_resource_fails(self):
        body = self.body()
        body["rls"][0]["clause"] = "partner_id = 1 OR 1=1"
        self.assertFalse(self.validate(body))
        body = self.body()
        body["resources"][0]["id"] = "other"
        self.assertFalse(self.validate(body))


if __name__ == "__main__":
    unittest.main()
