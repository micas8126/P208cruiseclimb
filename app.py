import streamlit as st
import pandas as pd
import numpy as np

# CSV-Dateien laden
climb_df = pd.read_csv("tecnam_climb_performance_corrected.csv")
cruise_df = pd.read_csv("tecnam_cruise_performance.csv")

# Korrekturfaktoren laut AFM
TEMP_CORR = {+15: -0.02, -15: +0.01}  # je °C Abweichung
FUEL_CORR = {+15: -0.025, -15: +0.03}
WEIGHT_KTAS_CORR = 0.033  # +3.3% je -100kg

# Interpolationsfunktionen
def interpolate_climb(df, alt_ft, weight, oat):
    df["Pressure Altitude [ft]"] = pd.to_numeric(df["Pressure Altitude [ft]"], errors="coerce")
    df["Weight [kg]"] = pd.to_numeric(df["Weight [kg]"], errors="coerce")

    subset = df[np.isclose(df["Pressure Altitude [ft]"], alt_ft, atol=500)]
    if subset.empty:
        return None, None, None

    grouped = subset.groupby(["Pressure Altitude [ft]", "Weight [kg]"])
    means = grouped.mean().reset_index()
    temp_cols = [c for c in means.columns if "°C" in c and "ROC" not in c and "Distance" not in c]
    temps = sorted([int(c.split("@")[1].replace("°C", "")) for c in temp_cols])

    # Zeitinterpolation
    time_array = means[[col for col in means.columns if "Time" in col]].values.flatten()
    dist_array = means[[col for col in means.columns if "Distance" in col]].values.flatten()
    fuel_array = means[[col for col in means.columns if "Fuel" in col]].values.flatten()

    climb_time = np.interp(oat, temps, time_array)
    climb_dist = np.interp(oat, temps, dist_array)
    climb_fuel = np.interp(oat, temps, fuel_array)

    return climb_time, climb_dist, climb_fuel

def interpolate_cruise(df, alt_ft, weight, rpm, oat):
    subset = df[(df["Pressure Altitude [ft]"] == alt_ft) & (df["Propeller RPM"] == rpm)]
    if subset.empty:
        return None, None

    base_speed = float(subset["KTAS"].values[0])
    base_fuel = float(subset["Fuel Consumption [l/hr]"].values[0])

    weight_corr = ((650 - weight) / 100) * WEIGHT_KTAS_CORR
    corrected_speed = base_speed * (1 + weight_corr)

    isa_temp = 15 - (alt_ft / 1000 * 2)
    delta_t = oat - isa_temp

    if delta_t > 0:
        temp_corr = TEMP_CORR[+15] * (delta_t / 15)
        fuel_corr = FUEL_CORR[+15] * (delta_t / 15)
    else:
        temp_corr = TEMP_CORR[-15] * (delta_t / -15)
        fuel_corr = FUEL_CORR[-15] * (delta_t / -15)

    corrected_speed *= (1 + temp_corr)
    corrected_fuel = base_fuel * (1 + fuel_corr)

    return corrected_speed, corrected_fuel

# Streamlit UI
st.title("P2008 JC Cruise + Climb Kalkulator")

weight = st.number_input("Gewicht [kg]", value=600, min_value=550, max_value=650)
oat_surface = st.number_input("Außentemperatur am Startplatz [°C]", value=15.0)
track = st.number_input("Track (Kursrichtung) [°]", value=180)
wind_dir = st.number_input("Windrichtung (woher) [°]", value=180)
wind_speed = st.number_input("Windstärke [kt]", value=0.0)
rpm = st.selectbox("Propeller RPM", sorted(cruise_df["Propeller RPM"].unique()))
total_distance = st.number_input("Gesamtdistanz [NM]", value=100.0)
alt_field = st.number_input("Startplatz Pressure Altitude [ft]", value=1000)
target_alt = st.number_input("Reiseflughöhe [ft]", value=6000)
alt_diff = target_alt - alt_field

# Temperatur in der Reiseflughöhe
isa_at_alt = 15 - (target_alt / 1000 * 2)
oat_alt = oat_surface - (target_alt - alt_field) / 1000 * 2
st.markdown(f"**Berechnete Temperatur auf Reiseflughöhe:** {oat_alt:.1f} °C")

# Climb
climb_time, climb_dist, climb_fuel = interpolate_climb(climb_df, alt_diff, weight, oat_surface)

# Cruise
cruise_speed, cruise_flow = interpolate_cruise(cruise_df, target_alt, weight, rpm, oat_alt)

# Windkorrektur
if None not in (climb_time, climb_dist, climb_fuel, cruise_speed, cruise_flow):
    remaining_dist = total_distance - climb_dist
    if remaining_dist <= 0:
        st.error("Gesamtdistanz kleiner als Climb-Strecke")
    else:
        wind_angle = np.radians(wind_dir - track)
        wind_component = wind_speed * np.cos(wind_angle)
        ground_speed = cruise_speed + wind_component

        cruise_time = remaining_dist / ground_speed
        cruise_fuel = cruise_time * cruise_flow

        total_time = climb_time / 60 + cruise_time
        total_fuel = climb_fuel + cruise_fuel + 2 + 1 + 6.75  # inkl. Start/Landung/Reserve

        st.success("Ergebnisse")
        st.write(f"**ISA Temp @ Alt:** {isa_at_alt:.1f} °C | **OAT-Abweichung:** {oat_alt - isa_at_alt:+.1f} °C")
        st.write(f"**Climb:** {climb_time:.0f} min, {climb_dist:.1f} NM, {climb_fuel:.1f} l")
        st.write(f"**Cruise GS:** {ground_speed:.1f} kt | Fuel Flow: {cruise_flow:.2f} l/h")
        st.write(f"**Cruise:** {cruise_time:.2f} h, {remaining_dist:.1f} NM, {cruise_fuel:.1f} l")
        st.write("---")
        st.write(f"**Total Time:** {total_time:.2f} h")
        st.write(f"**Total Fuel:** {total_fuel:.1f} l (inkl. 2 l Start, 1 l Landung, 45 min Reserve)")
else:
    st.warning("Nicht genügend Daten für Berechnung gefunden.")
