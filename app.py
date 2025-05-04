import streamlit as st
import pandas as pd
import numpy as np

# CSV laden
cruise_df = pd.read_csv("tecnam_cruise_performance.csv")
climb_df = pd.read_csv("tecnam_climb_performance_corrected.csv")

# ISA Temperaturberechnung

def isa_temperature(altitude_ft):
    return 15 - 2 * (altitude_ft / 1000)

# Interpolation Cruise

def interpolate_cruise(df, altitude, weight, rpm, oat_alt):
    subset = df[df["Pressure Altitude [ft]"] == altitude]
    if subset.empty:
        closest_alt = df["Pressure Altitude [ft]"].iloc[(df["Pressure Altitude [ft]"].astype(int) - altitude).abs().argsort()[:1]].values[0]
        subset = df[df["Pressure Altitude [ft]"] == closest_alt]

    rpm_subset = subset[subset["Propeller RPM"] == rpm]
    if rpm_subset.empty:
        closest_rpm = subset["Propeller RPM"].iloc[(subset["Propeller RPM"] - rpm).abs().argsort()[:1]].values[0]
        rpm_subset = subset[subset["Propeller RPM"] == closest_rpm]

    if rpm_subset.empty:
        st.warning("Keine passenden Cruise-Daten gefunden.")
        return None, None

    # Grundwerte
    base_speed = float(rpm_subset["KTAS"].values[0])
    base_fuel = float(rpm_subset["Fuel Consumption [ltr/hr]"].values[0])

    # Temperaturkorrektur (relativ zu ISA)
    isa_temp = isa_temperature(altitude)
    delta_temp = oat_alt - isa_temp
    if delta_temp >= 0:
        ktas_corr = base_speed * (1 - 0.00133 * delta_temp)
        fuel_corr = base_fuel * (1 - 0.00167 * delta_temp)
    else:
        ktas_corr = base_speed * (1 + 0.00067 * abs(delta_temp))
        fuel_corr = base_fuel * (1 + 0.002 * abs(delta_temp))

    # Gewichtskorrektur
    delta_weight = 650 - weight
    ktas_corr *= 1 + (delta_weight * 0.00033)

    return round(ktas_corr, 1), round(fuel_corr, 2)

# UI
st.title("Tecnam P2008 JC Performance Calculator")

weight = st.number_input("Abfluggewicht [kg]", min_value=550, max_value=650, value=630)
airfield_alt = st.number_input("Flugplatzhöhe [ft]", min_value=0, max_value=14000, value=2000)
target_alt = st.number_input("Reiseflughöhe [ft]", min_value=0, max_value=14000, value=6000)
temp_surface = st.number_input("Außentemperatur am Startplatz [°C]", value=15.0)
total_distance = st.number_input("Gesamtdistanz [NM]", value=100.0)
rpm = st.selectbox("Propeller RPM", sorted(cruise_df["Propeller RPM"].unique()))

# Temperatur in Reiseflughöhe
isa_temp_alt = isa_temperature(target_alt)
oat_alt = isa_temp_alt + (temp_surface - isa_temperature(airfield_alt))
st.markdown(f"**Berechnete Temperatur auf Reiseflughöhe:** {oat_alt:.1f} °C")

# Climb-Höhe berechnen
alt_diff = target_alt - airfield_alt

# Climb-Daten interpolieren
def interpolate_climb(df, alt_ft, weight, temp):
    df["Pressure Altitude [ft]"] = pd.to_numeric(df["Pressure Altitude [ft]"], errors='coerce')
    df = df.dropna(subset=["Pressure Altitude [ft]"])

    grouped = df.groupby("Pressure Altitude [ft]")
    levels = sorted(grouped.groups.keys())

    if alt_ft > max(levels):
        st.warning("Zielhöhe außerhalb des gültigen Bereichs der Tabelle.")
        return 0, 0, 0

    lower = max([lvl for lvl in levels if lvl <= alt_ft], default=min(levels))
    upper = min([lvl for lvl in levels if lvl >= alt_ft], default=max(levels))

    def row_interp(rows):
        weights = rows["Weight [kg]"].astype(float)
        rocs = rows.filter(like="RoC").T
        temps = [float(c.split("@")[1].replace("°C", "")) for c in rocs.index if "@" in c]
        roc_interp = [np.interp(temp, temps, rocs[col].values) for col in rocs.columns]
        roc_final = np.interp(weight, weights, roc_interp)
        return 500 / max(roc_final, 1), 0.1, 4.9  # Dummywerte: Zeit, Distanz, Fuel

    climb_time, climb_dist, climb_fuel = row_interp(grouped.get_group(lower))
    return climb_time, climb_dist, climb_fuel

# Cruise-Berechnung
cruise_speed, cruise_flow = interpolate_cruise(cruise_df, target_alt, weight, rpm, oat_alt)

# Climb-Werte
climb_time, climb_dist, climb_fuel = interpolate_climb(climb_df, alt_diff, weight, temp_surface)

remaining_distance = total_distance - climb_dist

if cruise_speed and cruise_flow:
    cruise_time = remaining_distance / cruise_speed
    cruise_fuel = cruise_time * cruise_flow

    st.success("Ergebnisse")
    st.write(f"**ISA Temp @ Alt:** {isa_temp_alt:.1f} °C | **OAT-Abweichung:** {oat_alt - isa_temp_alt:+.1f} °C")
    st.write(f"**Climb:** {climb_time:.2f} h, {climb_dist:.1f} NM, {climb_fuel:.1f} l")
    st.write(f"**Cruise GS:** {cruise_speed:.1f} kt | Fuel Flow: {cruise_flow:.2f} l/h")
    st.write(f"**Cruise:** {cruise_time:.2f} h, {remaining_distance:.1f} NM, {cruise_fuel:.1f} l")
else:
    st.error("Cruise-Daten nicht berechenbar.")
