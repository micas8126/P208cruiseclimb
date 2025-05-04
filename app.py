import pandas as pd
import numpy as np
import streamlit as st

# Daten laden
cruise_df = pd.read_csv("tecnam_cruise_performance.csv")
climb_df = pd.read_csv("tecnam_climb_performance_corrected.csv")

# UI
st.title("Tecnam P2008 JC Performance Kalkulation")
st.markdown("Berechnung von **Flugzeit** und **Kraftstoffverbrauch [l]** inkl. Climb, Cruise, Windkorrektur, Alternate und Reserve")

# Eingabefelder
weight = st.number_input("Abfluggewicht [kg]", min_value=550, max_value=650, value=600)
airfield_alt = st.number_input("Druckhöhe am Startplatz [ft]", min_value=0, max_value=14000, value=0)
target_alt = st.number_input("Reiseflughöhe (Druckhöhe) [ft]", min_value=0, max_value=14000, value=4000)
temp_surface = st.number_input("Außentemperatur am Startplatz [°C]", value=15.0)
temp_lapse_rate = -2.0 / 1000  # °C pro 1000 ft
track = st.number_input("Track (Kursrichtung) [°]", min_value=0, max_value=360, value=180)
wind_dir = st.number_input("Windrichtung (woher) [°]", min_value=0, max_value=360, value=180)
wind_speed = st.number_input("Windstärke [kt]", min_value=0.0, value=0.0)
prop_rpm = st.selectbox("Propeller RPM", sorted(cruise_df["Propeller RPM"].unique(), reverse=True))
total_dist = st.number_input("Gesamtdistanz [NM]", min_value=1.0, value=100.0)
alt_dist = st.number_input("Alternate Distanz [NM]", min_value=0.0, value=0.0)
additional_fuel = st.number_input("Zusätzlicher Kraftstoff [l]", min_value=0.0, value=0.0)

# Temperatur auf Reiseflughöhe berechnen
alt_diff = target_alt - airfield_alt
temp_at_alt = temp_surface + (alt_diff / 1000) * temp_lapse_rate
st.markdown(f"**Berechnete Temperatur auf Reiseflughöhe:** {temp_at_alt:.1f} °C")

# Windkomponente berechnen
def calc_wind_component(track, wind_dir, wind_speed):
    angle_rad = np.radians(wind_dir - track)
    headwind = wind_speed * np.cos(angle_rad)
    crosswind = wind_speed * np.sin(angle_rad)
    return round(headwind, 1), round(crosswind, 1)

hwc, cwc = calc_wind_component(track, wind_dir, wind_speed)

# Climb-Interpolation mit Original-CSV (Interpolation über Höhe, Temperatur, Gewicht)
def interpolate_climb(alt_ft, weight, temp):
    climb_df_cleaned = climb_df.copy()
    climb_df_cleaned["Pressure Altitude [ft]"] = climb_df_cleaned["Pressure Altitude [ft]"].replace("S.L.", 0).astype(int)
    weights = sorted(climb_df_cleaned["Weight [kg]"].unique())
    closest_weights = sorted(weights, key=lambda x: abs(x - weight))[:2]

    temp_cols = [col for col in climb_df_cleaned.columns if col.startswith("Rate @")]
    temp_vals = [float(col.split("@")[1].replace("°C", "").strip()) for col in temp_cols]

    climb_values = []

    for w in closest_weights:
        df_w = climb_df_cleaned[climb_df_cleaned["Weight [kg]"] == w].sort_values("Pressure Altitude [ft]")
        if alt_ft < df_w["Pressure Altitude [ft]"].min() or alt_ft > df_w["Pressure Altitude [ft]"].max():
            continue

        interpolated_roc = []
        for col in temp_cols:
            sub = df_w[["Pressure Altitude [ft]", col]].dropna()
            if len(sub) >= 2:
                roc = np.interp(alt_ft, sub["Pressure Altitude [ft]"], sub[col])
                interpolated_roc.append(roc)
        if len(interpolated_roc) != len(temp_vals):
            continue

        # Nur gültige Paare behalten
        valid_pairs = [(tv, rv) for tv, rv in zip(temp_vals, interpolated_roc) if not pd.isna(rv)]
        if len(valid_pairs) < 2:
            continue
        tv_vals, rv_vals = zip(*valid_pairs)
        roc_final = np.interp(temp, tv_vals, rv_vals)

        if roc_final <= 0:
            continue
        time_hr = alt_ft / roc_final / 60
        dist_nm = time_hr * 90
        fuel_l = time_hr * 20
        climb_values.append((w, time_hr, dist_nm, fuel_l))

    if len(climb_values) < 2:
        return None, None, None

    w1, t1, d1, f1 = climb_values[0]
    w2, t2, d2, f2 = climb_values[1]

    climb_time = np.interp(weight, [w1, w2], [t1, t2])
    climb_dist = np.interp(weight, [w1, w2], [d1, d2])
    climb_fuel = np.interp(weight, [w1, w2], [f1, f2])

    st.write(f"**Interpolierte ROC:** {roc_final:.1f} ft/min")
    return climb_time, climb_dist, climb_fuel
