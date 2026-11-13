"""
Project Indradhanu - LoRa Message Codec & Validator (PRD v2.0 Section 6)
Implements compact fixed-width 20-character detection message protocol:
Format: N01T2611121445087001
Field Layout:
  [0:3]   Node ID          (e.g., 'N01', 'N02')
  [3:4]   Animal Code      ('T'=Bengal tiger, 'L'=Indian leopard, 'B'=Indian sloth bear, 'A'=Asiatic lion)
  [4:10]  Date             (YYMMDD, e.g., '261112' -> 2026-11-12)
  [10:14] Time             (HHMM, e.g., '1445' -> 14:45)
  [14:17] Confidence       (000-100, e.g., '087' -> 87%)
  [17:20] Event Sequence   (000-999, e.g., '001')
"""

from datetime import datetime

ANIMAL_CODE_MAP = {
    "T": {
        "code": "T",
        "name": "Bengal Tiger",
        "scientific_name": "Panthera tigris tigris",
        "key": "tiger",
    },
    "L": {
        "code": "L",
        "name": "Indian Leopard",
        "scientific_name": "Panthera pardus fusca",
        "key": "leopard",
    },
    "B": {
        "code": "B",
        "name": "Indian Sloth Bear",
        "scientific_name": "Melursus ursinus",
        "key": "bear",
    },
    "A": {
        "code": "A",
        "name": "Asiatic Lion",
        "scientific_name": "Panthera leo persica",
        "key": "lion",
    },
}

SPECIES_KEY_TO_CODE = {
    "tiger": "T",
    "bengal tiger": "T",
    "leopard": "L",
    "indian leopard": "L",
    "bear": "B",
    "sloth bear": "B",
    "indian sloth bear": "B",
    "lion": "A",
    "asiatic lion": "A",
}


def encode_lora_message(node_id, species_name_or_code, confidence_pct, dt=None, seq_num=1):
    """
    Encodes detection metadata into the fixed-width 20-character LoRa string:
    Example: encode_lora_message('N01', 'T', 87.4, dt=datetime(2026, 11, 12, 14, 45), seq_num=1)
    Returns: 'N01T2611121445087001'
    """
    # 1. Format Node ID: must be 3 characters starting with 'N'
    raw_node = str(node_id).strip().upper()
    if raw_node.startswith("NODE-"):
        # e.g. NODE-01 -> N01
        num_part = raw_node.replace("NODE-", "")
        formatted_node = f"N{int(num_part):02d}"
    elif raw_node.startswith("N") and len(raw_node) == 3:
        formatted_node = raw_node
    elif raw_node.isdigit():
        formatted_node = f"N{int(raw_node):02d}"
    else:
        formatted_node = raw_node[:3].ljust(3, "0")

    # 2. Animal Code: 1 character
    sp_input = str(species_name_or_code).strip()
    if sp_input.upper() in ANIMAL_CODE_MAP:
        animal_code = sp_input.upper()
    else:
        animal_code = SPECIES_KEY_TO_CODE.get(sp_input.lower(), "T")

    # 3. Timestamp
    target_dt = dt or datetime.now()
    date_str = target_dt.strftime("%y%m%d")  # YYMMDD (6 chars)
    time_str = target_dt.strftime("%H%M")    # HHMM (4 chars)

    # 4. Confidence: 3 digits clamped 000-100
    conf_clamped = max(0, min(100, int(round(float(confidence_pct)))))
    conf_str = f"{conf_clamped:03d}"

    # 5. Sequence number: 3 digits (000-999)
    seq_val = int(seq_num) % 1000
    seq_str = f"{seq_val:03d}"

    msg = f"{formatted_node}{animal_code}{date_str}{time_str}{conf_str}{seq_str}"
    if len(msg) != 20:
        raise ValueError(f"LoRa message length mismatch: expected 20 chars, got {len(msg)}: '{msg}'")
    return msg


def decode_lora_message(raw_msg):
    """
    Decodes and validates a raw LoRa message string per PRD 6.2 & 6.3.
    Returns (is_valid, parsed_data_dict_or_error_string).
    """
    if not raw_msg:
        return False, "Empty LoRa message payload."

    msg = str(raw_msg).strip()
    if len(msg) != 20:
        return False, f"Malformed LoRa message: expected 20 characters, received {len(msg)}: '{msg}'"

    node_part = msg[0:3]
    animal_code = msg[3:4]
    date_part = msg[4:10]
    time_part = msg[10:14]
    conf_part = msg[14:17]
    seq_part = msg[17:20]

    # 1. Validate animal code
    if animal_code not in ANIMAL_CODE_MAP:
        return False, f"Invalid animal code '{animal_code}' in LoRa payload. Supported: T, L, B, A."

    animal_info = ANIMAL_CODE_MAP[animal_code]

    # 2. Validate date and time (YYMMDD HHMM)
    try:
        dt_obj = datetime.strptime(f"{date_part}{time_part}", "%y%m%d%H%M")
        timestamp_str = dt_obj.strftime("%Y-%m-%d %H:%M:00")
    except ValueError as e:
        return False, f"Malformed date/time in LoRa payload '{date_part}{time_part}': {e}"

    # 3. Validate confidence
    try:
        confidence_val = int(conf_part)
        if confidence_val < 0 or confidence_val > 100:
            return False, f"Confidence '{conf_part}' outside 0-100 range."
    except ValueError:
        return False, f"Non-numeric confidence in LoRa payload: '{conf_part}'"

    # 4. Canonical Node Code (e.g., N01 -> NODE-01)
    if node_part.startswith("N") and node_part[1:].isdigit():
        canonical_node = f"NODE-{int(node_part[1:]):02d}"
    else:
        canonical_node = node_part

    # 5. Deterministic Unique Event ID for deduplication
    # e.g., LORA-N01-261112-1445-001
    event_id = f"LORA-{node_part}-{date_part}-{time_part}-{seq_part}"

    return True, {
        "raw_message": msg,
        "node_id": node_part,
        "node_code": canonical_node,
        "animal_code": animal_code,
        "animal_name": animal_info["name"],
        "scientific_name": animal_info["scientific_name"],
        "species_key": animal_info["key"],
        "confidence": confidence_val,
        "event_sequence": seq_part,
        "detected_at": timestamp_str,
        "event_id": event_id,
    }
