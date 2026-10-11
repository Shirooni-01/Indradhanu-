import time

def test_temporal_tracking_and_deduplication():
    # Simulation of the ACTIVE_SIGHTINGS tracker logic
    active_sightings = {}
    min_presence = 2.0
    expiry_time = 3.5
    db_records = []

    def process_frame(timestamp, species, confidence, conf_threshold):
        min_conf_pct = conf_threshold * 100.0
        if confidence < min_conf_pct or species not in ("Bengal Tiger", "Indian Leopard"):
            # Sub-threshold: do not track
            return

        if species not in active_sightings:
            active_sightings[species] = {
                "first_seen": timestamp,
                "last_seen": timestamp,
                "logged": False,
                "best_conf": confidence
            }
        else:
            sighting = active_sightings[species]
            sighting["last_seen"] = timestamp
            if confidence > sighting["best_conf"]:
                sighting["best_conf"] = confidence

            presence_time = timestamp - sighting["first_seen"]
            if presence_time >= min_presence and not sighting["logged"]:
                sighting["logged"] = True
                db_records.append({
                    "species": species,
                    "confidence": sighting["best_conf"],
                    "logged_at": timestamp
                })

        # Expiry check
        expired = [sp for sp, s in list(active_sightings.items()) if (timestamp - s["last_seen"]) > expiry_time]
        for sp in expired:
            del active_sightings[sp]

    # --- Scenario 1: Brief flash (0.8s) below 2 seconds ---
    process_frame(0.0, "Bengal Tiger", 75.0, 0.45)
    process_frame(0.8, "Bengal Tiger", 78.0, 0.45)
    assert len(db_records) == 0, "Should NOT log on brief 0.8s flash!"
    print("Test 1 Passed: Brief detection under 2s was rejected.")

    # --- Scenario 2: Continuous presence spanning > 2.0s ---
    process_frame(1.5, "Bengal Tiger", 82.0, 0.45)
    process_frame(2.2, "Bengal Tiger", 85.0, 0.45)  # Now at 2.2s >= 2.0s!
    assert len(db_records) == 1, "Should log exactly ONCE when presence reaches 2.2s!"
    assert db_records[0]["species"] == "Bengal Tiger"
    print("Test 2 Passed: Logged incident once continuous presence exceeded 2.0s.")

    # --- Scenario 3: Deduplication (Animal lingers for 10 more seconds) ---
    for t in [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]:
        process_frame(t, "Bengal Tiger", 88.0, 0.45)
    assert len(db_records) == 1, f"Should STILL be only 1 record, but got {len(db_records)}!"
    print("Test 3 Passed: Lingering animal was deduplicated, zero duplicate records.")

    # --- Scenario 4: Sub-threshold animal (conf 40% < threshold 50%) ---
    process_frame(10.5, "Indian Leopard", 40.0, 0.50)
    process_frame(13.0, "Indian Leopard", 42.0, 0.50)
    assert len(db_records) == 1, "Sub-threshold animal should NOT be tracked or logged!"
    print("Test 4 Passed: Sub-threshold detection was filtered out.")

    # --- Scenario 5: Animal leaves, scene clears, new animal arrives later ---
    # At t=15.0s, Bengal Tiger was last seen at t=10.0s (delta=5.0s > 3.5s expiry)
    process_frame(15.0, "Indian Leopard", 80.0, 0.45)
    assert "Bengal Tiger" not in active_sightings, "Bengal Tiger encounter should have expired!"
    process_frame(17.2, "Indian Leopard", 84.0, 0.45)
    assert len(db_records) == 2, "Second distinct encounter should be logged after 2.0s!"
    print("Test 5 Passed: Scene clearance and subsequent encounter logged cleanly.")

    print("\nALL 5 TEMPORAL & DEDUPLICATION TESTS PASSED SUCCESSFULLY! [OK]")

if __name__ == "__main__":
    test_temporal_tracking_and_deduplication()
