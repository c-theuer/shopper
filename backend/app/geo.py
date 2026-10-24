from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_MI = 3958.8


def miles_between(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Straight-line (haversine) distance, the PRD's proposed MVP radius rule."""
    dlat, dlng = radians(lat2 - lat1), radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_MI * asin(sqrt(a))
