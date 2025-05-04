import pandas as pd
import numpy as np
import streamlit as st

# Daten laden
cruise_df = pd.read_csv("tecnam_cruise_performance.csv")
climb_df = pd.read_csv("tecnam_climb_performance_corrected.csv")

st.title("P2008 JC Cruise & Climb Calculator")

# Eingaben
weight = st.number_input("Abfluggewicht [kg]", min_value=550, max_value=650, value=600)
distance = st.number_input("Gesamtdistanz [NM]", min_value=10.0, step=1.0)
airfield_alt = st.number_input("Airfield Pressure Altitude [ft]", step=100)
cruise_alt = st.number_input("Reiseflughöhe (Pressure Altitude) [ft]", step=100)
temp_surface = st.number_input("Außentemperatur am Startplatz [°C]", value=15.0)
prop_rpm = st.selectbox("Propeller RPM", sorted(cruise_df['Propeller RPM'].unique(), reverse=True))
track = st.number_input("Track (Kursrichtung) [°]", min_value=0, max_value=360, value=180)
wind_direction = st.number_input("Windrichtung (woher) [°]", min_value=0, max_value=360, value=360)
wind_speed = st.number_input("Windstärke [kt]", min_value=0.0, value=10.0)
alternate_dist = st.number_input("Alternate Distanz [NM]", min_value=0.0, value=0.0)
additional_fuel = st.number_input("Zusätzlicher Kraftstoff [l]", min_value=0.0, value=0.0)

# Temperatur auf Reiseflughöhe berechnen (ISA - 2°C pro 1000 ft)
isa_temp = 15 - (2 * cruise_alt / 1000)
oat_at_alt = temp_surface - (2 * (cruise_alt - airfield_alt) / 1000)
oat_deviation = oat_at_alt - isa_temp
st.markdown(f"**Berechnete Temperatur auf Reiseflughöhe:** {oat_at_alt:.1f} °C")

# Interpolation Cruise
subset = cruise_df[(cruise_df['Pressure Altitude [ft]'] == cruise_alt) & (cruise_df['Propeller RPM'] == prop_rpm)]
if subset.empty:
    st.error("Keine passenden Cruise-Daten gefunden.")
else:
    speeds = subset['KTAS'].values
    fuels = subset['Fuel Consumption [l/hr]'].values
    weights = np.full_like(speeds, 650)  # Basisgewicht

    # Gewichtskorrektur: +3.3% TAS je -100 kg
    weight_diff = 650 - weight
    speed_corr = speeds * (1 + (0.033 * weight_diff / 100))

    # Temperaturkorrektur
    temp_corr = speed_corr * (1 + (0.01 * oat_deviation / 15))
    fuel_corr = fuels * (1 + (-0.025 * oat_deviation / 15))

    cruise_speed = np.mean(temp_corr)
    fuel_flow = np.mean(fuel_corr)

    # Windkorrektur
    wind_rad = np.radians(wind_direction)
    track_rad = np.radians(track)
    rel_angle = wind_rad - track_rad
    headwind = wind_speed * np.cos(rel_angle)
    crosswind = wind_speed * np.sin(rel_angle)
    gs = cruise_speed + headwind

    # Climb interpolieren
    climb_alt = cruise_alt - airfield_alt
    climb_segment = climb_df[climb_df['Delta Altitude [ft]'] == climb_alt]
    if climb_segment.empty:
        st.warning("Keine passenden Climb-Daten.")
        climb_time = climb_dist = climb_fuel = 0.0
    else:
        climb_weights = climb_segment['Weight [kg]'].values
        climb_temps = climb_segment.columns[3:].astype(float)

        # Interpolation Climb Zeit, Distanz, Fuel
        climb_time_vals = []
        climb_dist_vals = []
        climb_fuel_vals = []
        for col in climb_temps:
            climb_time_vals.append(np.interp(weight, climb_weights, climb_segment[str(col)].values))
            climb_dist_vals.append(np.interp(weight, climb_weights, climb_segment[str(col) + '_Dist'].values))
            climb_fuel_vals.append(np.interp(weight, climb_weights, climb_segment[str(col) + '_Fuel'].values))

        climb_time = np.interp(oat_at_alt, climb_temps, climb_time_vals) / 60
        climb_dist = np.interp(oat_at_alt, climb_temps, climb_dist_vals)
        climb_fuel = np.interp(oat_at_alt, climb_temps, climb_fuel_vals)

    remaining_dist = distance - climb_dist
    time_cruise = remaining_dist / gs
    fuel_cruise = time_cruise * fuel_flow

    # Alternate fix: 600kg, 2000 RPM, 4000 ft
    alt_subset = cruise_df[(cruise_df['Pressure Altitude [ft]'] == 4000) & (cruise_df['Propeller RPM'] == 2000)]
    if alt_subset.empty:
        alt_time = alt_fuel = 0.0
    else:
        alt_speed = alt_subset[alt_subset['KTAS'] == alt_subset['KTAS'].max()].iloc[0]['KTAS']
        alt_flow = alt_subset[alt_subset['KTAS'] == alt_subset['KTAS'].max()].iloc[0]['Fuel Consumption [l/hr]']
        alt_time = alternate_dist / alt_speed
        alt_fuel = alt_time * alt_flow

    # Fixe Komponenten
    fuel_departure = 2.0
    fuel_landing = 1.0
    fuel_reserve = 45 * fuel_flow / 60

    total_time = climb_time + time_cruise + alt_time
    total_fuel = climb_fuel + fuel_cruise + alt_fuel + fuel_departure + fuel_landing + fuel_reserve + additional_fuel

    st.success("Ergebnisse")
    st.markdown(f"**ISA Temp @ Alt:** {isa_temp:.1f} °C | **OAT-Abweichung:** {oat_deviation:+.1f} °C")
    st.markdown(f"**Windkomponente:** {abs(headwind):.1f} kt ({'Gegenwind +' if headwind > 0 else 'Rückenwind -'}) | **Seitenwind:** {abs(crosswind):.1f} kt")
    st.markdown(f"**Climb:** {climb_time:.2f} h, {climb_dist:.1f} NM, {climb_fuel:.1f} l")
    st.markdown(f"**Cruise GS:** {gs:.1f} kt | Fuel Flow: {fuel_flow:.2f} l/h")
    st.markdown(f"**Cruise:** {time_cruise:.2f} h, {remaining_dist:.1f} NM, {fuel_cruise:.1f} l")
    st.markdown(f"**Alternate:** {alt_time:.2f} h, {alt_fuel:.1f} l")
    st.markdown("---")
    st.markdown(f"**Zusätze:** Start: {fuel_departure:.1f} l | Landung: {fuel_landing:.1f} l | Reserve: {fuel_reserve:.1f} l | Extra: {additional_fuel:.1f} l")
    st.markdown("---")
    st.markdown(f"**Gesamtdauer:** {total_time:.2f} h")
    st.markdown(f"**Gesamtverbrauch:** {total_fuel:.1f} l")
