"""Child tool summaries cannot establish that a real action executed (MIT-0)."""
import json


def verify_child_receipts(reported, host_receipts):
    """Compare child reports with host callbacks and return only host values.

    The child legitimately pops action_echo after printing it. No other field
    is allowed to alter a host action result. This fixes one IPC integrity bug;
    it does not confine Python, authenticate filesystem writes, or make child
    stdout/result/retained functions trusted scientific evidence.
    """
    if not isinstance(host_receipts, list) or any(not isinstance(row, dict) for row in host_receipts):
        raise ValueError("host receipt ledger must contain dictionaries")
    host = json.loads(json.dumps(host_receipts, allow_nan=False))
    for row in host:
        row.pop("action_echo", None)
    valid = isinstance(reported, list) and all(isinstance(row, dict) for row in reported)
    if valid:
        try:
            child = json.loads(json.dumps(reported, allow_nan=False))
            for row in child:
                row.pop("action_echo", None)
            valid = json.dumps(child, sort_keys=True, separators=(",", ":")) == json.dumps(host, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError):
            valid = False
    return {"valid": valid, "action_results": host,
            "error": None if valid else "Sandbox child action receipts differ from the actual host ledger; child result rejected."}
