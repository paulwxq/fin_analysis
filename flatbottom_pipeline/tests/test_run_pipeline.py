"""Tests for flatbottom_pipeline.run_pipeline (preflight checks & stage definitions)."""
from unittest.mock import patch, MagicMock

import pytest

from flatbottom_pipeline.run_pipeline import (
    check_db_connection,
    check_monthly_kline,
    check_preselect_table,
    check_kline_images,
    STAGES,
    STAGE_ORDER,
    run_preflight,
)


# ===========================================================================
# check_db_connection
# ===========================================================================

class TestCheckDbConnection:
    @patch("flatbottom_pipeline.run_pipeline._get_db_connection")
    def test_success(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        assert check_db_connection() is True

    @patch("flatbottom_pipeline.run_pipeline._get_db_connection", side_effect=Exception("Connection refused"))
    def test_failure(self, mock_get_conn):
        assert check_db_connection() is False


# ===========================================================================
# check_monthly_kline
# ===========================================================================

class TestCheckMonthlyKline:
    @patch("flatbottom_pipeline.run_pipeline._get_db_connection")
    def test_exists_with_data(self, mock_get_conn):
        mock_cursor = MagicMock()
        # to_regclass returns a non-None value
        mock_cursor.fetchone.side_effect = [("stock_monthly_kline",), (1,)]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

        assert check_monthly_kline() is True

    @patch("flatbottom_pipeline.run_pipeline._get_db_connection")
    def test_not_exists(self, mock_get_conn):
        mock_cursor = MagicMock()
        # to_regclass returns (None,)
        mock_cursor.fetchone.side_effect = [(None,)]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

        assert check_monthly_kline() is False

    @patch("flatbottom_pipeline.run_pipeline._get_db_connection")
    def test_exists_but_empty(self, mock_get_conn):
        mock_cursor = MagicMock()
        # to_regclass returns value, but SELECT 1 returns None (empty)
        mock_cursor.fetchone.side_effect = [("stock_monthly_kline",), None]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

        assert check_monthly_kline() is False


# ===========================================================================
# check_preselect_table
# ===========================================================================

class TestCheckPreselectTable:
    @patch("flatbottom_pipeline.run_pipeline._get_db_connection")
    def test_has_data(self, mock_get_conn):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

        assert check_preselect_table() is True

    @patch("flatbottom_pipeline.run_pipeline._get_db_connection")
    def test_empty(self, mock_get_conn):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

        assert check_preselect_table() is False

    @patch("flatbottom_pipeline.run_pipeline._get_db_connection", side_effect=Exception("Table not found"))
    def test_exception(self, mock_get_conn):
        assert check_preselect_table() is False


# ===========================================================================
# check_kline_images
# ===========================================================================

class TestCheckKlineImages:
    @patch("flatbottom_pipeline.run_pipeline.glob.glob", return_value=["/output/000001.SZ_kline.png"])
    def test_found(self, mock_glob):
        assert check_kline_images() is True

    @patch("flatbottom_pipeline.run_pipeline.glob.glob", return_value=[])
    def test_none(self, mock_glob):
        assert check_kline_images() is False


# ===========================================================================
# Stage definitions
# ===========================================================================

class TestStageDefinitions:
    def test_stages_keys(self):
        assert set(STAGES.keys()) == {"select", "plot", "refine"}

    def test_stage_order_length(self):
        assert STAGE_ORDER == ["select", "plot", "refine"]

    def test_each_stage_has_required_keys(self):
        for name, stage in STAGES.items():
            assert "module" in stage, f"{name} missing 'module'"
            assert "preflight" in stage, f"{name} missing 'preflight'"
            assert "description" in stage, f"{name} missing 'description'"
            assert isinstance(stage["preflight"], list)

    def test_select_preflight_order(self):
        """select stage checks DB first, then monthly kline."""
        fns = STAGES["select"]["preflight"]
        assert fns[0] is check_db_connection
        assert fns[1] is check_monthly_kline

    def test_refine_no_db_check(self):
        """refine stage only checks images, not DB."""
        fns = STAGES["refine"]["preflight"]
        assert check_db_connection not in fns
        assert check_kline_images in fns


# ===========================================================================
# run_preflight
# ===========================================================================

class TestRunPreflight:
    @patch("flatbottom_pipeline.run_pipeline._get_db_connection")
    def test_run_preflight_select_success(self, mock_get_conn):
        """run_preflight('select') returns True when all checks pass."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [
            (1,),  # check_db_connection: SELECT 1
            ("stock_monthly_kline",),  # check_monthly_kline: to_regclass
            (1,),  # check_monthly_kline: SELECT 1 LIMIT 1
        ]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

        assert run_preflight("select") is True

    @patch("flatbottom_pipeline.run_pipeline.glob.glob", return_value=[])
    def test_run_preflight_refine_fails(self, mock_glob):
        """run_preflight('refine') returns False when no images found."""
        assert run_preflight("refine") is False
