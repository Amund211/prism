def compare_uuids(uuid_1: str, uuid_2: str, /) -> bool:
    """Return True if the two uuids (dashed or not) are equal"""
    return uuid_1.replace("-", "") == uuid_2.replace("-", "")
