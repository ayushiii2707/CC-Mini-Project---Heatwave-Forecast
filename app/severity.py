"""Rule-based heatwave severity classifier (NOT machine learning).

Applies the India Meteorological Department (IMD) heatwave criteria to a
(forecast or observed) maximum temperature:

* Minimum threshold before a heatwave is considered:
  40 C for plains, 37 C for coastal stations.
* By departure from normal: 4.5 to 6.4 C -> Heatwave, > 6.4 C -> Severe heatwave.
* By actual Tmax (plains only): >= 45 C -> Heatwave, >= 47 C -> Severe heatwave.

Simplifications (documented as limitations): applied to a single grid cell
for a single day; IMD declares heatwaves when criteria hold at two or more
stations in a sub-division for two consecutive days. Normals here come from
2014-2022 IMD gridded data, not IMD's 30-year station normals.
"""

NORMAL, HEATWAVE, SEVERE = "Normal", "Heatwave", "Severe heatwave"
LEVELS = [NORMAL, HEATWAVE, SEVERE]

ADVICE = {
    NORMAL: "No heatwave expected. Normal summer precautions apply.",
    HEATWAVE: "Heatwave conditions likely. Avoid sun exposure 12-3 pm, drink water often, "
              "check on elderly people, children and outdoor workers.",
    SEVERE: "Severe heatwave likely. High risk of heat illness. Stay indoors in the afternoon, "
            "keep cool, and seek medical help for symptoms like dizziness or confusion.",
}


def classify(tmax: float, normal: float, coastal: bool = False) -> dict:
    departure = tmax - normal
    threshold = 37.0 if coastal else 40.0
    level = NORMAL
    reason = f"Tmax {tmax:.1f} C below the {threshold:.0f} C threshold"
    if tmax >= threshold:
        reason = f"departure {departure:+.1f} C from normal {normal:.1f} C"
        if departure > 6.4:
            level = SEVERE
        elif departure >= 4.5:
            level = HEATWAVE
        if not coastal:  # absolute-temperature rule applies to plains only
            if tmax >= 47.0:
                level, reason = SEVERE, f"Tmax {tmax:.1f} C >= 47 C"
            elif tmax >= 45.0 and level == NORMAL:
                level, reason = HEATWAVE, f"Tmax {tmax:.1f} C >= 45 C"
    return {
        "level": level,
        "departure_from_normal": round(departure, 1),
        "rule": reason,
        "advisory": ADVICE[level],
    }
