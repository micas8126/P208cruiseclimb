import pandas as pd
import numpy as np
import streamlit as st
import math

# Daten laden
cruise_df = pd.read_csv("tecnam_cruise_performance.csv")
climb_df = pd.read_csv("tecnam_climb_performance_corrected.csv")

st.title("Tecnam P2008 JC - Flugleistungsrechner")

# Eingaben
weight = st.number_input("Abfluggewicht [kg]", min_value=550, max_value=650, value=611)
temp_surface = st.number_input("Außentemperatur am Startplatz [°C]", value=15.0)
track = st.number_input("Track (Kursrichtung) [°]", min_value=0, max_value=360, value=180)
wind_dir = st.number_input("Windrichtung (woher) [°]", min_value=0, max_value=360, value=180)
wind_speed = st.number_input("Windstärke [kt]", min_value=0.0, value=0.0)
rpm = st.selectbox("Propeller RPM", sorted(cruise_df["Propeller RPM"].unique(), reverse=True))
total_distance = st.number_input("Gesamtdistanz [NM]", min_value=10.0, value=100.0)
alt_distance = st.number_input("Alternate Distanz [NM]", min_value=0.0, value=0.0)
extra_fuel = st.number_input("Zusätzlicher Kraftstoff [l]", min_value=0.0, value=0.0)

alt_airfield = st.number_input("Pressure Altitude am Startplatz [ft]", min_value=0, max_value=14000, value=0)
alt_target = st.number_input("Reiseflughöhe (Pressure Altitude) [ft]", min_value=0, max_value=14000, value=4000)

# Temperatur auf Reiseflughöhe berechnen (Standardatmosphäre -2°/1000ft)
temp_alt = temp_surface - (alt_target - alt_airfield) * 0.002
st.markdown(f"**Berechnete Temperatur auf Reiseflughöhe:** {temp_alt:.1f} °C")

# Windkomponenten berechnen
def wind_components(track, wind_dir, wind_speed):
    angle = math.radians((wind_dir - track) % 360)
    headwind = round(wind_speed * math.cos(angle), 1)
    crosswind = round(wind_speed * math.sin(angle), 1)
    return headwind, crosswind

hw_comp, cw_comp = wind_components(track, wind_dir, wind_speed)

# --- Climb Interpolation ---
def interpolate_climb(alt_ft, weight, temp):
    climb_subset = climb_df[climb_df['Weight [kg]'] == min(climb_df['Weight [kg]'], key=lambda x: abs(x-weight))]
    available_alts = climb_subset['Pressure Altitude [ft]'].unique()
    lower_alt = max([a for a in available_alts if a <= alt_ft], default=None)
    upper_alt = min([a for a in available_alts if a >= alt_ft], default=None)

    if lower_alt is None or upper_alt is None or lower_alt == upper_alt:
        return 0, 0, 0

    interpolated = []
    for alt in [lower_alt, upper_alt]:
        temp_cols = [c for c in climb_df.columns if f"{alt}" in c and "ROC" in c]
        temps = [float(c.split()[2].replace('°C', '')) for c in temp_cols]
        rocs = [climb_df[(climb_df['Weight [kg]'] == weight) & (climb_df['Pressure Altitude [ft]'] == alt)][c].values[0] for c in temp_cols]
        roc = np.interp(temp, temps, rocs)
        interpolated.append((alt, roc))

    roc_ft_min = np.interp(alt_ft, [lower_alt, upper_alt], [i[1] for i in interpolated])
    time_hr = alt_ft / roc_ft_min / 60
    dist_nm = time_hr * 80
    fuel_l = time_hr * 25
    return time_hr, dist_nm, fuel_l

# --- Cruise Interpolation ---
def interpolate_cruise(alt_ft, rpm, weight, temp):
    df = cruise_df[(cruise_df['Pressure Altitude [ft]'] == alt_ft) & (cruise_df['Propeller RPM'] == rpm)]
    if df.empty:
        return None, None
    temps = df['OAT ISA [deg C]'].values
    ktas_vals = df['KTAS'].values
    ff_vals = df['Fuel Consumption [lt/hr]'].values
    gs = np.interp(temp, temps, ktas_vals) + hw_comp
    ff = np.interp(temp, temps, ff_vals)
    return gs, ff

# Climb
alt_diff = alt_target - alt_airfield
climb_time, climb_dist, climb_fuel = interpolate_climb(alt_diff, weight, temp_surface)

# Cruise
remaining_dist = total_distance - climb_dist
if remaining_dist < 0:
    st.error("Distanz zu kurz für Climb. Bitte erhöhen.")
else:
    gs, ff = interpolate_cruise(alt_target, rpm, weight, temp_alt)
    if gs is None:
        st.error("Keine passenden Cruise-Daten gefunden.")
    else:
        cruise_time = remaining_dist / gs
        cruise_fuel = cruise_time * ff

        # Alternate
        alt_gs, alt_ff = interpolate_cruise(4000, 2000, 600, temp_alt)
        alt_time = alt_distance / alt_gs if alt_gs else 0
        alt_fuel = alt_time * alt_ff if alt_ff else 0

        total_fuel = climb_fuel + cruise_fuel + alt_fuel + 2 + 1 + extra_fuel + 45/60 * ff

        st.success("Ergebnisse")
        st.write(f"**ISA Temp @ Alt:** {15 - 0.002 * alt_target:.1f} °C | **OAT-Abweichung:** {temp_alt - (15 - 0.002 * alt_target):+.1f} °C")
        st.write(f"**Windkomponente:** {hw_comp:+.1f} kt ({'Gegenwind +' if hw_comp < 0 else 'Rückenwind -'}), Seitenwind: {cw_comp:.1f} kt")
        st.write("---")
        st.write(f"**Climb:** {climb_time:.2f} h, {climb_dist:.1f} NM, {climb_fuel:.1f} l")
        st.write(f"**Cruise GS:** {gs:.1f} kt | Fuel Flow: {ff:.2f} l/h")
        st.write(f"**Cruise:** {cruise_time:.2f} h, {remaining_dist:.1f} NM, {cruise_fuel:.1f} l")
        st.write("---")
        st.write(f"**Al
