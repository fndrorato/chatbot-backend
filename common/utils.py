def parse_int(data, key, required=True):
    val = data.get(key, None)
    if val is None:
        if required:
            raise ValueError(f"'{key}' is required")
        return None
    try:
        return int(str(val).strip())
    except (TypeError, ValueError):
        raise ValueError(f"'{key}' must be an integer")