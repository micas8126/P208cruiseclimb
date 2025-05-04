import pandas as pd
import numpy as np
import streamlit as st

# Daten laden
cruise_df = pd.read_csv("tecnam_cruise_performance.csv")
climb_df = pd.read_csv("tecnam_climb_performance_corrected.csv")

# Streamlit UI
st.title("P2008 JC Performance Calculator")
st.markdown("Basisversion: Climb & Cruise Kalkulation ohne Wind oder Alternate")

# Eingaben
weight = st.number_input("Abfluggewicht [kg]", min_value=550, max_value=650, value=600)
airfield_alt = st.number_input("Startplatzhöhe (Pressure Altitude) [ft]", min_value=0, max_value=14000, value=0)
cruise_alt = st.number_input("Reiseflughöhe (Pressure Altitude) [ft]", min_value=0, max_value=14000, value=4000)
temp_surface = st.number_input("Außentemperatur [°C]", value=15.0)
total_dist = st.number_input("Gesamtdistanz [NM]", min_value=10.0, value=100.0)
rpm = st.selectbox("Propeller RPM", sorted(cruise_df["Propeller RPM"].unique(), reverse=True))

# Temperatur in Reiseflughöhe abschätzen
lapse_rate = -2 / 1000  # °C pro 1000 ft
alt_diff = cruise_alt - airfield_alt
temp_cruise = temp_surface + (alt_diff / 1000) * lapse_rate

# Climb Interpolation
def interpolate_climb(alt_ft, weight, temp):
    climb_df["Pressure Altitude [ft]"] = pd.to_numeric(climb_df["Pressure Altitude [ft]"], errors="coerce")
    weights = sorted(climb_df["Weight [kg]"].unique())
    closest_weights = sorted(weights, key=lambda x: abs(x - weight))[:2]

    temp_cols = [col for col in climb_df.columns if col.startswith("ROC @")]
    temp_vals = []
    for col in temp_cols:
        try:
            val = float(col.split("@")[1].replace("°C", "").strip())
            temp_vals.append(val)
        except (IndexError, ValueError):
            continue

    climb_values = []
    for w in closest_weights:
        df_w = climb_df[climb_df["Weight [kg]"] == w].sort_values("Pressure Altitude [ft]")
        if alt_ft < df_w["Pressure Altitude [ft]"].min() or alt_ft > df_w["Pressure Altitude [ft]"].max():
            continue
        interpolated_roc = []
        for col in temp_cols:
            sub = df_w[["Pressure Altitude [ft]", col]].dropna()
            if len(sub) >= 2:
                roc = np.interp(alt_ft, sub["Pressure Altitude [ft]"], sub[col])
                interpolated_roc.append(roc)
        valid_pairs = [(tv, rv) for tv, rv in zip(temp_vals, interpolated_roc) if not pd.isna(rv)]
        if len(valid_pairs) < 2:
            continue
        tv_vals, rv_vals = zip(*valid_pairs)
        roc_final = np.interp(temp, tv_vals, rv_vals)
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
    return climb_time, climb_dist, climb_fuel

# Cruise Interpolation
def interpolate_cruise(cruise_df, altitude, weight, rpm):
    subset = cruise_df[(cruise_df["Pressure Altitude [ft]"] == altitude) &
                       (cruise_df["Propeller RPM"] == rpm)]
    if subset.empty:
        return None, None
    speeds = np.interp(weight, subset["Weight [kg]"], subset["KTAS"])
    fuel_flows = np.interp(weight, subset["Weight [kg]"], subset["Fuel Consumption [lt/hr]"])
    return speeds, fuel_flows

# Berechnung starten
climb_time, climb_dist, climb_fuel = interpolate_climb(alt_diff, weight, temp_surface)
if climb_time is None:
    st.error("Climb-Kalkulation fehlgeschlagen. Bitte gültige Werte wählen.")
else:
    cruise_speed, cruise_flow = interpolate_cruise(cruise_df, cruise_alt, weight, rpm)
    if cruise_speed is None:
        st.error("Keine passenden Cruise-Daten gefunden.")
    else:
        cruise_dist = max(0, total_dist - climb_dist)
        cruise_time = cruise_dist / cruise_speed
        cruise_fuel = cruise_time * cruise_flow

        total_time = climb_time + cruise_time
        total_fuel = climb_fuel + cruise_fuel

        st.success("Ergebnisse")
        st.write(f"**Climb:** {climb_time:.2f} h | {climb_dist:.1f} NM | {climb_fuel:.1f} l")
        st.write(f"**Cruise:** {cruise_time:.2f} h | {cruise_dist:.1f} NM | {cruise_fuel:.1f} l")
        st.write("---")
        st.write(f"**Gesamtdauer:** {total_time:.2f} h")
        st.write(f"**Gesamtverbrauch:** {total_fuel:.1f} l")
