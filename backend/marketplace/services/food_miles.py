import math

# A sample of Bristol-area postcode sectors mapped to approximate latitude/longitude.
# This is a simplified subset for demonstration; a production system would use a
# full postcode lookup API or database (e.g. Ordnance Survey Code-Point Open).
POSTCODE_COORDINATES = {
    'BS1': (51.4536, -2.5973),
    'BS2': (51.4615, -2.5836),
    'BS3': (51.4393, -2.6093),
    'BS4': (51.4374, -2.5722),
    'BS5': (51.4654, -2.5644),
    'BS6': (51.4736, -2.5953),
    'BS7': (51.4831, -2.5853),
    'BS8': (51.4555, -2.6219),
    'BS9': (51.4789, -2.6280),
    'BS10': (51.5018, -2.6105),
    'BS11': (51.4889, -2.6802),
    'BS13': (51.4150, -2.6233),
    'BS14': (51.4126, -2.5680),
    'BS15': (51.4624, -2.4949),
    'BS16': (51.4824, -2.5151),
    'BA1': (51.3837, -2.3597),
    'GL1': (51.8642, -2.2380),
    'TA1': (51.0163, -3.1067),
    'SN1': (51.5639, -1.7795),
}

DEFAULT_DISTANCE_MILES = 10.0
EARTH_RADIUS_MILES = 3958.8


def _normalise_postcode(postcode: str) -> str:
    return (postcode or '').strip().upper().replace(' ', '')


def _sector_key(postcode: str) -> str:
    """Extract the outward code (e.g. 'BS1' from 'BS1 4DJ')."""
    normalised = _normalise_postcode(postcode)
    for length in (4, 3, 2):
        candidate = normalised[:length]
        if candidate in POSTCODE_COORDINATES:
            return candidate
    return ''


def _haversine_miles(lat1, lon1, lat2, lon2) -> float:
    lat1_r, lon1_r, lat2_r, lon2_r = map(math.radians, [lat1, lon1, lat2, lon2])
    d_lat = lat2_r - lat1_r
    d_lon = lon2_r - lon1_r
    a = math.sin(d_lat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(d_lon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return EARTH_RADIUS_MILES * c


def postcode_distance_miles(origin_postcode: str, destination_postcode: str) -> float:
    """
    Calculate the great-circle distance between two postcodes using the
    Haversine formula. Falls back to a fuzzy sector match, then to a
    default distance, if either postcode is not in the lookup table.

    Note: this is straight-line distance, not actual road distance, so it
    will understate real food miles for indirect routes.
    """
    origin_key = _sector_key(origin_postcode)
    destination_key = _sector_key(destination_postcode)

    if not origin_key or not destination_key:
        return DEFAULT_DISTANCE_MILES

    if origin_key == destination_key:
        return 0.5  # Same sector — treat as a short local hop

    lat1, lon1 = POSTCODE_COORDINATES[origin_key]
    lat2, lon2 = POSTCODE_COORDINATES[destination_key]
    return round(_haversine_miles(lat1, lon1, lat2, lon2), 2)