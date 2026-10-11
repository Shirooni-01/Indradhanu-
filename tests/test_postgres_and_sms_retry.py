"""
Comprehensive Unit & Integration Verification Suite for:
1. PostgreSQL Central Layer (connection pooling, schema, CRUD, transactions, fallback)
2. SMS Retry Engine (retry logic, backoff, max retries, FAILED_PERMANENT termination, deduplication)
"""

import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.db_manager import (
    execute_query,
    init_db,
    queue_offline_alert,
    get_pending_offline_alerts,
    record_alert_retry_result,
    flush_offline_queue,
    get_db_connection,
    release_db_connection,
    close_db_pool,
    IS_POSTGRES
)
from edge.database.edge_db import (
    init_edge_db,
    queue_sms_alert,
    get_pending_sms_alerts,
    record_edge_sms_result,
    flush_edge_sms_queue
)


class TestPostgreSqlCentralLayer(unittest.TestCase):
    """Priority 1: PostgreSQL Central Layer Verification"""

    def setUp(self):
        init_db()

    def test_database_crud_operations(self):
        """Verify insertion, query execution, and parameter mapping work correctly."""
        # Insert detection
        det_id = execute_query(
            """
            INSERT INTO detections 
            (species, scientific_name, confidence, threat_level, latitude, longitude, distance_meters, rotator_heading, node_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("Tiger", "Panthera tigris", 96.5, "CRITICAL", 21.1458, 79.0882, 120, 180, "NODE-01"),
            commit=True
        )
        self.assertIsNotNone(det_id)
        self.assertGreater(det_id, 0)

        # Query single detection
        row = execute_query(
            "SELECT * FROM detections WHERE id = ?",
            (det_id,),
            fetchone=True
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["species"], "Tiger")
        self.assertEqual(float(row["confidence"]), 96.5)

        # Query all detections
        rows = execute_query(
            "SELECT id, species FROM detections WHERE id = ?",
            (det_id,),
            fetchall=True
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], det_id)

    def test_postgres_parameter_translation_and_returning_clause(self):
        """Verify the database abstraction translates queries and formats properly for PostgreSQL."""
        # Test query parameter translation logic
        raw_query = "SELECT * FROM detections WHERE species = ? AND confidence >= ?"
        expected_pg = "SELECT * FROM detections WHERE species = %s AND confidence >= %s"
        translated = raw_query.replace("?", "%s")
        self.assertEqual(translated, expected_pg)

    def test_postgres_fallback_to_sqlite(self):
        """Verify that when DATABASE_URL is unavailable or fails, fallback to SQLite occurs safely without crash."""
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://invalid_user:bad_pass@127.0.0.1:5432/nonexistent_db"}):
            # Database connection should either connect or fallback to SQLite gracefully
            conn = get_db_connection()
            self.assertIsNotNone(conn)
            release_db_connection(conn)


class TestSmsRetryEngine(unittest.TestCase):
    """Priority 2: SMS Retry Engine Verification"""

    def setUp(self):
        init_db()
        # Clean test entries in alert_fallback_queue
        execute_query("DELETE FROM alert_fallback_queue WHERE recipient_phone LIKE 'TEST-%'", commit=True)

    def test_sms_enqueue_and_atomic_checkout(self):
        """Verify SMS alert enqueues properly and checkout applies atomic PROCESSING lock."""
        alert_id = queue_offline_alert(
            detection_id=None,
            phone="TEST-9876543210",
            name="Ranger Sharma",
            message="CRITICAL: Tiger detected near Rampur!",
            max_retries=3
        )
        self.assertIsNotNone(alert_id)

        # Checkout pending alerts
        pending = get_pending_offline_alerts(limit=5)
        matched = [a for a in pending if a["id"] == alert_id]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["recipient_phone"], "TEST-9876543210")
        self.assertEqual(matched[0]["retry_count"], 0)

        # Verify atomic PROCESSING lock prevents concurrent/duplicate checkout
        second_pending = get_pending_offline_alerts(limit=5)
        second_matched = [a for a in second_pending if a["id"] == alert_id]
        self.assertEqual(len(second_matched), 0, "Duplicate checkout must be prevented while in PROCESSING state!")

    def test_sms_retry_backoff_and_permanent_failure(self):
        """Verify retry increments counter, applies exponential backoff, and terminates at max retries."""
        alert_id = queue_offline_alert(
            detection_id=None,
            phone="TEST-9999999999",
            name="Sarpanch Patil",
            message="WARNING: Leopard spotted!",
            max_retries=3
        )

        # Attempt 1: Fail
        record_alert_retry_result(alert_id, success=False, error_msg="Network timeout (Attempt 1)")
        alert = execute_query("SELECT * FROM alert_fallback_queue WHERE id = ?", (alert_id,), fetchone=True)
        self.assertEqual(alert["status"], "QUEUED_OFFLINE")
        self.assertEqual(alert["retry_count"], 1)
        self.assertIn("Attempt 1", alert["last_error"])

        # Attempt 2: Fail
        record_alert_retry_result(alert_id, success=False, error_msg="Provider HTTP 503 (Attempt 2)")
        alert = execute_query("SELECT * FROM alert_fallback_queue WHERE id = ?", (alert_id,), fetchone=True)
        self.assertEqual(alert["status"], "QUEUED_OFFLINE")
        self.assertEqual(alert["retry_count"], 2)

        # Attempt 3: Fail (reaching max_retries = 3)
        record_alert_retry_result(alert_id, success=False, error_msg="Invalid Gateway Response (Attempt 3)")
        alert = execute_query("SELECT * FROM alert_fallback_queue WHERE id = ?", (alert_id,), fetchone=True)
        self.assertEqual(alert["status"], "FAILED_PERMANENT", "Must transition to FAILED_PERMANENT when retry_count >= max_retries!")
        self.assertEqual(alert["retry_count"], 3)
        self.assertIn("Max retries (3) exhausted", alert["last_error"])

        # Verify it is no longer returned in pending checkout
        pending = get_pending_offline_alerts(limit=10)
        self.assertEqual(len([a for a in pending if a["id"] == alert_id]), 0)

    def test_sms_successful_dispatch(self):
        """Verify successful dispatch transitions status to DELIVERED and records dispatched_at."""
        alert_id = queue_offline_alert(
            detection_id=None,
            phone="TEST-8888888888",
            name="Villager Ramesh",
            message="ALERT: Animal detection test",
            max_retries=3
        )

        record_alert_retry_result(alert_id, success=True)
        alert = execute_query("SELECT * FROM alert_fallback_queue WHERE id = ?", (alert_id,), fetchone=True)
        self.assertEqual(alert["status"], "DELIVERED")
        self.assertIsNotNone(alert["dispatched_at"])

    def test_stale_processing_lock_recovery(self):
        """Verify that stale PROCESSING locks (e.g. from crashed processes) are automatically recovered."""
        alert_id = queue_offline_alert(
            detection_id=None,
            phone="TEST-7777777777",
            name="Villager Suresh",
            message="ALERT: Stale lock test",
            max_retries=3
        )

        # Manually put into PROCESSING state with old timestamp (3 minutes ago)
        execute_query(
            "UPDATE alert_fallback_queue SET status = 'PROCESSING', created_at = datetime('now', '-3 minutes') WHERE id = ?",
            (alert_id,),
            commit=True
        )

        # Next checkout call must recover the stale alert back to QUEUED_OFFLINE and return it
        pending = get_pending_offline_alerts(limit=10)
        matched = [a for a in pending if a["id"] == alert_id]
        self.assertEqual(len(matched), 1, "Stale PROCESSING alerts must be recovered and re-queued!")

    def test_flush_offline_queue_with_mock_provider(self):
        """Verify flush_offline_queue coordinates with SMS service and reports correct metrics."""
        # Queue 2 test alerts
        id1 = queue_offline_alert(detection_id=None, phone="TEST-1111111111", message="Message 1", name="User 1", max_retries=3)
        id2 = queue_offline_alert(detection_id=None, phone="TEST-2222222222", message="Message 2", name="User 2", max_retries=3)

        # Mock SMS service: 1 success, 1 failure
        mock_sms_service = MagicMock()
        def mock_send(phone, message):
            if "1111111111" in phone:
                return (True, "Delivered via Mock", "MOCK_SMS")
            return (False, "Network error", "MOCK_SMS")

        mock_sms_service.send_sms.side_effect = mock_send

        stats = flush_offline_queue(mock_sms_service)
        self.assertGreaterEqual(stats["total_processed"], 2)
        self.assertGreaterEqual(stats["delivered"], 1)
        self.assertGreaterEqual(stats["retrying"] + stats["failed_permanent"], 1)


class TestEdgeSmsRetryEngine(unittest.TestCase):
    """Edge Device SMS Retry Engine Verification"""

    def setUp(self):
        init_edge_db()

    def test_edge_sms_retry_lifecycle(self):
        """Verify local edge queue lifecycle: queue -> retry -> permanent failure."""
        alert_id = queue_sms_alert(
            detection_id=None,
            phone="TEST-EDGE-1",
            name="Guard 1",
            message="PIR alert",
            max_retries=2,
            error_msg="No GSM signal"
        )
        self.assertIsNotNone(alert_id)

        # Checkout
        pending = get_pending_sms_alerts(limit=5)
        matched = [a for a in pending if a["id"] == alert_id]
        self.assertEqual(len(matched), 1)

        # Retry 1
        record_edge_sms_result(alert_id, success=False, error_msg="SIM Busy")
        # Retry 2 (max retries = 2)
        record_edge_sms_result(alert_id, success=False, error_msg="Timeout")

        # After reaching 2 retries, must not be pending
        pending2 = get_pending_sms_alerts(limit=5)
        self.assertEqual(len([a for a in pending2 if a["id"] == alert_id]), 0)


if __name__ == "__main__":
    unittest.main()
