import streamlit as st
import pandas as pd
import numpy as np

# Daten laden
cruise_df = pd.read_csv("tecnam_cruise_performance.csv")
climb_df = pd.read_csv("tecnam_climb_performance_corrected.csv")

# ISA Temperatur

def isa_temperature(alt_ft):
    return 15 - (alt_ft / 1000) * 2

# Cruise Interpolation

def interpolate_cruise(df, alt_ft, rpm, oat, weight):
    subset = df[(df["Pressure Altitude [ft]"] == alt_ft) & (df["Propeller RPM"] == rpm)]
    if subset.empty:
        return None, None
    base_speed = float(subset["KTAS"].values[0])
    base_fuel = float(subset["Fuel Consumption [l/hr]"].values[0])
    delta_t = oat - isa_temperature(alt_ft)
    if delta_t >= 0:
        speed = base_speed * (1 - 0.00133 * delta_t)
        fuel = base_fuel * (1 - 0.00167 * delta_t)
    else:
        speed = base_speed * (1 + 0.00067 * abs(delta_t))
        fuel = base_fuel * (1 + 0.002 * abs(delta_t))
    speed *= 1 + ((650 - weight) * 0.00033)
    return round(speed, 1), round(fuel, 2)

# Climb Interpolation

def interpolate_climb(df, alt_ft, weight, temp):
    df["Pressure Altitude [ft]"] = pd.to_numeric(df["Pressure Altitude [ft]"], errors="coerce")
    df["Weight [kg]"] = pd.to_numeric(df["Weight [kg]"], errors="coerce")
    df = df.dropna()
    heights = sorted(df["Pressure Altitude [ft]"].unique())
    weights = sorted(df["Weight [kg]"].unique())
    lower_h = max([h for h in heights if h <= alt_ft], default=min(heights))
    upper_h = min([h for h in heights if h >= alt_ft], default=max(heights))
    lower_w = max([w for w in weights if w <= weight], default=min(weights))
    upper_w = min([w for w in weights if w >= weight], default=max(weights))
    def entry(alt, w):
        row = df[(df["Pressure Altitude [ft]"] == alt) & (df["Weight [kg]"] == w)]
        temp_cols = [c for c in row.columns if "ROC @" in c]
        temps, rocs = [], []
        for col in temp_cols:
            try:
                t = float(col.split("@")[1].replace("°C", "").strip())
                temps.append(t)
                rocs.append(row[col].values[0])
            except:
                continue
        roc = np.interp(temp, temps, rocs)
        time = alt / roc / 60
        dist = time * 90
        fuel = time * 20
        return time, dist, fuel
    t1, d1, f1 = entry(lower_h, lower_w)
    t2, d2, f2 = entry(lower_h, upper_w)
    t3, d3, f3 = entry(upper_h, lower_w)
    t4, d4, f4 = entry(upper_h, upper_w)
    climb_time = np.interp(weight, [lower_w, upper_w], [np.interp(alt_ft, [lower_h, upper_h], [t1, t3]), np.interp(alt_ft, [lower_h, upper_h], [t2, t4])])
    climb_dist = np.interp(weight, [lower_w, upper_w], [np.interp(alt_ft, [lower_h, upper_h], [d1, d3]), np.interp(alt_ft, [lower_h, upper_h], [d2, d4])])
    climb_fuel = np.interp(weight, [lower_w, upper_w], [np.interp(alt_ft, [lower_h, upper_h], [f1, f3]), np.interp(alt_ft, [lower_h, upper_h], [f2, f4])])
    return climb_time, climb_dist, climb_fuel

# Streamlit UI
st.title("Tecnam P2008 JC Performance Kalkulation")

weight = st.selectbox("Abfluggewicht [kg]", list(range(550, 651, 10)))
airfield_alt = st.selectbox("Startplatzhöhe [ft]", list(range(0, 14500, 500)))
target_alt = st.selectbox("Reiseflughöhe [ft]", list(range(0, 14500, 500)))
temp_surface = st.number_input("Temperatur am Startplatz [°C]", value=15.0)
total_distance = st.number_input("Gesamtdistanz (NM)", value=200.0)
rpm = st.selectbox("Propeller RPM", sorted(cruise_df["Propeller RPM"].dropna().unique()))
alternate_distance = st.number_input("Alternate-Distanz (NM)", value=30.0)
additional_fuel = st.number_input("Zusätzlicher Kraftstoff (l)", value=0.0)

alt_diff = target_alt - airfield_alt
temp_cruise = temp_surface - ((target_alt - airfield_alt) / 1000 * 2)

climb_time, climb_dist, climb_fuel = interpolate_climb(climb_df, alt_diff, weight, temp_surface)
cruise_speed, cruise_flow = interpolate_cruise(cruise_df, target_alt, rpm, temp_cruise, weight)

# Cruise Segment
if None in (climb_time, climb_dist, climb_fuel, cruise_speed, cruise_flow):
    st.error("Berechnung fehlgeschlagen – bitte gültige Eingaben verwenden.")
else:
    cruise_dist = max(0, total_distance - climb_dist)
    cruise_time = cruise_dist / cruise_speed
    cruise_fuel = cruise_time * cruise_flow

    # Fixwerte
    fuel_start = 2.0
    fuel_landing = 1.0

    # Reserve (45 Min bei 650kg, 2000 RPM, 4000ft)
    reserve_speed, reserve_flow = interpolate_cruise(cruise_df, 4000, 2000, isa_temperature(4000), 650)
    fuel_reserve = 0.75 * reserve_flow

    # Alternate (aktuelles Gewicht, 2000 RPM, 4000ft)
    alt_speed, alt_flow = interpolate_cruise(cruise_df, 4000, 2000, isa_temperature(4000), weight)
    time_alt = alternate_distance / alt_speed
    fuel_alt = time_alt * alt_flow

    # Totalrechnung
    total_time = climb_time + cruise_time
    total_fuel = sum([climb_fuel, cruise_fuel, fuel_start, fuel_landing, fuel_reserve, fuel_alt, additional_fuel])

    st.success("Berechnung abgeschlossen")
    st.write(f"**Climb:** {climb_time:.2f} h, {climb_dist:.1f} NM, {climb_fuel:.1f} l")
    st.write(f"**Cruise:** {cruise_time:.2f} h, {cruise_dist:.1f} NM, {cruise_fuel:.1f} l")
    st.write("---")
    st.write(f"**Start + Landung:** {fuel_start + fuel_landing:.1f} l")
    st.write(f"**Reserve (45 min @ 650kg/2000RPM/4000ft):** {fuel_reserve:.1f} l")
    st.write(f"**Alternate:** {time_alt:.2f} h, {fuel_alt:.1f} l")
    st.write(f"**Zusatzkraftstoff:** {additional_fuel:.1f} l")
    st.write("---")
    st.write(f"**Gesamtdauer:** {total_time:.2f} h")
    st.write(f"**Gesamtverbrauch:** {total_fuel:.1f} l")
