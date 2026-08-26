from unittest.mock import Mock

import pytest

from dbgpt_serve.datasource.manages.connector_manager import ConnectorManager


def _manager_with_sqlite_config(ext_config):
    manager = object.__new__(ConnectorManager)
    manager.storage = Mock()
    manager.storage.get_db_config.return_value = {
        "db_type": "sqlite",
        "db_path": "D:/ProductionData/production.db",
        "db_pwd": "",
        "ext_config": ext_config,
    }
    connector_class = Mock()
    connector_class.from_file_path.return_value = Mock()
    manager.get_cls_by_dbtype = Mock(return_value=connector_class)
    return manager, connector_class


@pytest.mark.parametrize("ext_config", [{"read_only": True}, '{"read_only": true}'])
def test_build_sqlite_connector_restores_read_only_setting(ext_config):
    manager, connector_class = _manager_with_sqlite_config(ext_config)

    manager._build_connector("production")

    connector_class.from_file_path.assert_called_once_with(
        "D:/ProductionData/production.db", read_only=True
    )


def test_build_sqlite_connector_defaults_to_writable_compatibility():
    manager, connector_class = _manager_with_sqlite_config(None)

    manager._build_connector("development")

    connector_class.from_file_path.assert_called_once_with(
        "D:/ProductionData/production.db", read_only=False
    )


@pytest.mark.parametrize("ext_config", ['{"read_only": "true"}', "not-json"])
def test_build_sqlite_connector_rejects_invalid_read_only_config(ext_config):
    manager, connector_class = _manager_with_sqlite_config(ext_config)

    with pytest.raises(ValueError):
        manager._build_connector("production")

    connector_class.from_file_path.assert_not_called()
