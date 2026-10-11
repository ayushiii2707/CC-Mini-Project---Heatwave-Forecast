"""Locations served by the prototype.

Each city is mapped to the centre of the nearest IMD 1x1 degree grid cell
(cell centres are at x.5 degrees), so values are grid-cell averages, not
station readings. "coastal" selects the IMD coastal-station heatwave rule.
"""

# city: (grid-cell latitude, grid-cell longitude)
CITIES = {
    "Delhi": (28.5, 77.5),
    "Jaipur": (26.5, 75.5),
    "Lucknow": (26.5, 80.5),
    "Patna": (25.5, 85.5),
    "Ahmedabad": (23.5, 72.5),
    "Nagpur": (21.5, 79.5),
    "Kolkata": (22.5, 88.5),
    "Bhubaneswar": (20.5, 85.5),
    "Hyderabad": (17.5, 78.5),
    "Chennai": (13.5, 80.5),
}

COASTAL = {"Kolkata", "Chennai"}
