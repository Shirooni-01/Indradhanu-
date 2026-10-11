"""
Project Indradhanu - Central Siren Activation & Alert Policy Service
Evaluates central AI verification results against the configured alert policy,
prevents duplicate siren activations per event_id, dispatches authenticated
commands to the siren controller, and records explicit command vs. acknowledgement
status in the central database.
"""

import os
import time
from datetime import datetime
import requests

from database.system_config import load_system_config
from database.db_manager import (
    get_siren_alert_by_event_id,
    record_siren_alert,
    get_recent_siren_alerts,
    log_system_event,
)
from edge.siren_controller import SirenHardwareController


class SirenService:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.local_controller = SirenHardwareController()

    def _get_policy_config(self):
        cfg = load_system_config()
        return {
            "siren_mode": os.environ.get("SIREN_MODE", cfg.get("siren_mode", "SAFE_TEST")).upper(),
            "controller_url": os.environ.get("SIREN_CONTROLLER_URL", cfg.get("siren_controller_url", "")).strip(),
            "siren_api_key": os.environ.get("SIREN_API_KEY", cfg.get("siren_api_key", "indradhanu-siren-secret-key-2026")).strip(),
            "alert_conf_threshold": float(
                os.environ.get("SIREN_ALERT_CONF_THRESHOLD", cfg.get("siren_alert_conf_threshold", 65.0))
            ),
            "duration_sec": int(os.environ.get("SIREN_DURATION_SEC", cfg.get("siren_duration_sec", 15))),
            "max_sync_delay_sec": int(
                os.environ.get("SIREN_MAX_SYNC_DELAY_SEC", cfg.get("siren_max_sync_delay_sec", 900))
            ),
        }

    def evaluate_and_trigger(
        self,
        event_id,
        detection_id,
        node_code,
        verification_result,
        sync_latency_seconds=0,
    ):
        """
        Evaluates a verified detection event against the configured siren alert policy:
        1. Duplicate prevention: checks if event_id already has a siren record.
        2. Verification gate: requires verification_result['is_verified'] == True and target species.
        3. Confidence threshold gate: requires verified_confidence >= SIREN_ALERT_CONF_THRESHOLD.
        4. Sync freshness gate: suppresses immediate siren if offline delay > SIREN_MAX_SYNC_DELAY_SEC.
        5. Dispatches authenticated command and records COMMAND_SENT -> ACKNOWLEDGED_ACTIVE / TEST_MODE_VERIFIED / FAILED_NO_ACK.
        """
        policy = self._get_policy_config()
        siren_mode = policy["siren_mode"]
        controller_url = policy["controller_url"]

        # 1. Prevent duplicate siren commands for the same event_id
        existing = get_siren_alert_by_event_id(event_id)
        if existing and existing.get("command_status") in (
            "COMMAND_SENT",
            "ACKNOWLEDGED_ACTIVE",
            "TEST_MODE_VERIFIED",
            "SUPPRESSED_POLICY",
        ):
            return {
                "triggered": False,
                "duplicate_prevented": True,
                "event_id": event_id,
                "policy_decision": "DUPLICATE_PREVENTED",
                "command_status": existing["command_status"],
                "physical_siren_active": bool(existing.get("physical_siren_active")),
                "siren_mode": existing.get("siren_mode", siren_mode),
                "message": f"Duplicate siren command prevented for event {event_id} (existing status: {existing['command_status']}).",
            }

        is_verified = bool(verification_result.get("is_verified"))
        verified_species = verification_result.get("verified_species") or "Unknown"
        verified_conf = float(verification_result.get("verified_confidence") or 0.0)
        ver_status = verification_result.get("verification_status", "UNVERIFIED")

        # 2. Verification status gate
        if not is_verified:
            decision = f"SUPPRESSED_{ver_status}"
            msg = f"Siren suppressed: central AI verification status is {ver_status} ({verified_conf:.1f}%)."
            record_siren_alert(
                event_id=event_id,
                detection_id=detection_id,
                node_code=node_code,
                species=verified_species,
                verified_confidence=verified_conf,
                policy_decision=decision,
                siren_mode=siren_mode,
                command_status="SUPPRESSED_POLICY",
                physical_siren_active=0,
                controller_url=controller_url or "LOCAL_CONTROLLER",
                error_message=msg,
            )
            return {
                "triggered": False,
                "duplicate_prevented": False,
                "event_id": event_id,
                "policy_decision": decision,
                "command_status": "SUPPRESSED_POLICY",
                "physical_siren_active": False,
                "siren_mode": siren_mode,
                "message": msg,
            }

        # 3. Alert confidence policy gate
        if verified_conf < policy["alert_conf_threshold"]:
            decision = "SUPPRESSED_LOW_CONFIDENCE"
            msg = (
                f"Siren suppressed: verified confidence ({verified_conf:.1f}%) is below "
                f"siren alert policy threshold ({policy['alert_conf_threshold']:.1f}%)."
            )
            record_siren_alert(
                event_id=event_id,
                detection_id=detection_id,
                node_code=node_code,
                species=verified_species,
                verified_confidence=verified_conf,
                policy_decision=decision,
                siren_mode=siren_mode,
                command_status="SUPPRESSED_POLICY",
                physical_siren_active=0,
                controller_url=controller_url or "LOCAL_CONTROLLER",
                error_message=msg,
            )
            return {
                "triggered": False,
                "duplicate_prevented": False,
                "event_id": event_id,
                "policy_decision": decision,
                "command_status": "SUPPRESSED_POLICY",
                "physical_siren_active": False,
                "siren_mode": siren_mode,
                "message": msg,
            }

        # 4. Stale offline delay policy gate
        if int(sync_latency_seconds or 0) > policy["max_sync_delay_sec"]:
            decision = "SUPPRESSED_STALE_DELAY"
            msg = (
                f"Siren suppressed: event arrived after {sync_latency_seconds}s offline delay "
                f"(exceeds max real-time siren window of {policy['max_sync_delay_sec']}s)."
            )
            record_siren_alert(
                event_id=event_id,
                detection_id=detection_id,
                node_code=node_code,
                species=verified_species,
                verified_confidence=verified_conf,
                policy_decision=decision,
                siren_mode=siren_mode,
                command_status="SUPPRESSED_POLICY",
                physical_siren_active=0,
                controller_url=controller_url or "LOCAL_CONTROLLER",
                error_message=msg,
            )
            return {
                "triggered": False,
                "duplicate_prevented": False,
                "event_id": event_id,
                "policy_decision": decision,
                "command_status": "SUPPRESSED_POLICY",
                "physical_siren_active": False,
                "siren_mode": siren_mode,
                "message": msg,
            }

        # 5. Policy satisfied -> Record COMMAND_SENT first (before hardware acknowledgement)
        record_siren_alert(
            event_id=event_id,
            detection_id=detection_id,
            node_code=node_code,
            species=verified_species,
            verified_confidence=verified_conf,
            policy_decision="TRIGGER_APPROVED",
            siren_mode=siren_mode,
            command_status="COMMAND_SENT",
            physical_siren_active=0,
            controller_url=controller_url or "LOCAL_CONTROLLER",
        )

        return self._dispatch_command(
            event_id=event_id,
            detection_id=detection_id,
            node_code=node_code,
            species=verified_species,
            verified_confidence=verified_conf,
            policy_decision="TRIGGER_APPROVED",
            policy=policy,
        )

    def trigger_manual_or_test(self, node_code="NODE-01", species="Manual Siren Test", mode_override=None, duration_sec=None):
        """Triggers a safe test or hardware siren command from the dashboard/API."""
        policy = self._get_policy_config()
        if mode_override:
            policy["siren_mode"] = mode_override.upper()
        if duration_sec:
            policy["duration_sec"] = int(duration_sec)

        event_id = f"manual-siren-{int(time.time() * 1000)}"
        record_siren_alert(
            event_id=event_id,
            detection_id=None,
            node_code=node_code,
            species=species,
            verified_confidence=100.0,
            policy_decision="MANUAL_TEST",
            siren_mode=policy["siren_mode"],
            command_status="COMMAND_SENT",
            physical_siren_active=0,
            controller_url=policy["controller_url"] or "LOCAL_CONTROLLER",
        )
        return self._dispatch_command(
            event_id=event_id,
            detection_id=None,
            node_code=node_code,
            species=species,
            verified_confidence=100.0,
            policy_decision="MANUAL_TEST",
            policy=policy,
        )

    def _dispatch_command(self, event_id, detection_id, node_code, species, verified_confidence, policy_decision, policy):
        """Dispatches authenticated siren command via HTTP controller or local controller instance."""
        siren_mode = policy["siren_mode"]
        controller_url = policy["controller_url"]
        api_key = policy["siren_api_key"]
        duration_sec = policy["duration_sec"]
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Option A: Remote HTTP Siren Controller (when SIREN_MODE == HARDWARE_HTTP)
        if siren_mode == "HARDWARE_HTTP" and controller_url:
            headers = {
                "Content-Type": "application/json",
                "X-Siren-Key": api_key,
            }
            payload = {
                "event_id": event_id,
                "node_code": node_code,
                "species": species,
                "verified_confidence": verified_confidence,
                "duration_sec": duration_sec,
                "mode": "HARDWARE_GPIO",
            }
            try:
                resp = requests.post(controller_url, json=payload, headers=headers, timeout=5)
                ack_data = resp.json() if resp.content else {}
                acknowledged = bool(resp.status_code == 200 and ack_data.get("acknowledged"))
                physically_active = bool(ack_data.get("physical_siren_active"))

                if acknowledged and physically_active:
                    cmd_status = "ACKNOWLEDGED_ACTIVE"
                elif acknowledged and not physically_active:
                    cmd_status = "TEST_MODE_VERIFIED"
                else:
                    cmd_status = ack_data.get("command_status", "FAILED_NO_ACK")

                err_msg = ack_data.get("error") if not acknowledged else None
                record_siren_alert(
                    event_id=event_id,
                    detection_id=detection_id,
                    node_code=node_code,
                    species=species,
                    verified_confidence=verified_confidence,
                    policy_decision=policy_decision,
                    siren_mode=siren_mode,
                    command_status=cmd_status,
                    physical_siren_active=1 if physically_active else 0,
                    controller_url=controller_url,
                    ack_payload=ack_data,
                    error_message=err_msg,
                    acknowledged_at=now_str if acknowledged else None,
                )
                log_system_event(
                    "SIREN_COMMAND",
                    f"Event {event_id} ({species}): HTTP Siren Controller -> {cmd_status} (Physical Active: {physically_active})",
                )
                return {
                    "triggered": acknowledged,
                    "duplicate_prevented": False,
                    "event_id": event_id,
                    "policy_decision": policy_decision,
                    "command_status": cmd_status,
                    "physical_siren_active": physically_active,
                    "siren_mode": siren_mode,
                    "ack_payload": ack_data,
                    "message": ack_data.get("message") or err_msg or f"Controller returned {cmd_status}",
                }
            except Exception as e:
                err_str = f"Siren controller unreachable at {controller_url}: {e}"
                record_siren_alert(
                    event_id=event_id,
                    detection_id=detection_id,
                    node_code=node_code,
                    species=species,
                    verified_confidence=verified_confidence,
                    policy_decision=policy_decision,
                    siren_mode=siren_mode,
                    command_status="CONTROLLER_UNREACHABLE",
                    physical_siren_active=0,
                    controller_url=controller_url,
                    error_message=err_str,
                )
                log_system_event("SIREN_ERROR", f"Event {event_id}: {err_str}")
                return {
                    "triggered": False,
                    "duplicate_prevented": False,
                    "event_id": event_id,
                    "policy_decision": policy_decision,
                    "command_status": "CONTROLLER_UNREACHABLE",
                    "physical_siren_active": False,
                    "siren_mode": siren_mode,
                    "message": err_str,
                }

        # Option B: Direct Controller Invocation (SAFE_TEST or local HARDWARE_GPIO)
        self.local_controller.api_key = api_key
        ack_data, status_code = self.local_controller.activate(
            event_id=event_id,
            species=species,
            verified_confidence=verified_confidence,
            duration_sec=duration_sec,
            provided_key=api_key,
            requested_mode=siren_mode,
        )
        acknowledged = bool(status_code == 200 and ack_data.get("acknowledged"))
        physically_active = bool(ack_data.get("physical_siren_active"))
        cmd_status = ack_data.get("command_status", "FAILED_NO_ACK")
        err_msg = ack_data.get("error")

        record_siren_alert(
            event_id=event_id,
            detection_id=detection_id,
            node_code=node_code,
            species=species,
            verified_confidence=verified_confidence,
            policy_decision=policy_decision,
            siren_mode=siren_mode,
            command_status=cmd_status,
            physical_siren_active=1 if physically_active else 0,
            controller_url="LOCAL_CONTROLLER",
            ack_payload=ack_data,
            error_message=err_msg,
            acknowledged_at=now_str if acknowledged else None,
        )
        log_system_event(
            "SIREN_COMMAND",
            f"Event {event_id} ({species}): {cmd_status} (Mode: {siren_mode}, Physical Active: {physically_active})",
        )
        return {
            "triggered": acknowledged,
            "duplicate_prevented": False,
            "event_id": event_id,
            "policy_decision": policy_decision,
            "command_status": cmd_status,
            "physical_siren_active": physically_active,
            "siren_mode": siren_mode,
            "ack_payload": ack_data,
            "message": ack_data.get("message") or err_msg or cmd_status,
        }

    def get_status(self):
        policy = self._get_policy_config()
        ctrl_status = self.local_controller.get_status()
        recent_alerts = get_recent_siren_alerts(limit=15)
        last_alert = recent_alerts[0] if recent_alerts else None
        return {
            "siren_mode": policy["siren_mode"],
            "controller_url": policy["controller_url"] or "LOCAL_CONTROLLER",
            "alert_conf_threshold": policy["alert_conf_threshold"],
            "duration_sec": policy["duration_sec"],
            "max_sync_delay_sec": policy["max_sync_delay_sec"],
            "hardware_gpio_available": ctrl_status["hardware_gpio_available"],
            "physical_siren_active": ctrl_status["physical_siren_active"],
            "last_alert": last_alert,
            "recent_alerts": recent_alerts,
        }
