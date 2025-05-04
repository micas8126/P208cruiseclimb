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

# Climb-Interpolation (nach Höhe, Gewicht, Temperatur)
def interpolate_climb(alt_ft, weight, temp):
    climb_subset = climb_df[np.isclose(climb_df["Weight [kg]"], weight, atol=100)]
    if len(climb_subset) == 0:
        return None, None, None

    temp_cols = [col for col in climb_subset.columns if col.startswith("Rate @")]
    temp_vals = [float(col.split("@")[1].replace("°C", "").strip()) for col in temp_cols]
    altitudes = sorted(climb_subset["Pressure Altitude [ft]"].unique())
    if alt_ft > max(altitudes):
        return None, None, None

    # Interpolieren des Rate of Climb
    rates = []
    for tcol in temp_cols:
        sub = climb_subset[["Pressure Altitude [ft]", tcol]].dropna()
        roc = np.interp(alt_ft, sub["Pressure Altitude [ft]"], sub[tcol])
        rates.append(roc)

    roc_interp = np.interp(temp, temp_vals, rates)
    if roc_interp <= 0:
        return None, None, None

    time_hr = alt_ft / roc_interp / 60
    dist_nm = time_hr * 90  # Annahme GS während climb 90kt
    fuel_l = time_hr * 20  # Verbrauch geschätzt mit 20 l/h
    return time_hr, dist_nm, fuel_l

# Cruise-Interpolation
cruise_subset = cruise_df[cruise_df["Propeller RPM"] == prop_rpm]

if len(cruise_subset) == 0:
    st.error("Keine passenden Cruise-Daten gefunden. RPM prüfen.")
else:
    grouped = cruise_subset.groupby("Pressure Altitude [ft]")
    altitudes = sorted(grouped.groups.keys())
    if target_alt < min(altitudes) or target_alt > max(altitudes):
        st.error("Zielhöhe außerhalb des gültigen Bereichs der Tabelle.")
    else:
        speeds = []
        fuels = []
        for alt in altitudes:
            row = cruise_subset[cruise_subset["Pressure Altitude [ft]"] == alt]
            ktas = row["KTAS"].mean()
            fuel = row["Fuel Consumption [l/hr]"].mean()
            speeds.append(ktas)
            fuels.append(fuel)
        ktas_interp = np.interp(target_alt, altitudes, speeds)
        fuel_flow_interp = np.interp(target_alt, altitudes, fuels)

        # Korrekturen für Temperatur
        isa_temp = 15 + (-2 * target_alt / 1000)
        oat_dev = temp_at_alt - isa_temp
        ktas_corr = ktas_interp * (1 + oat_dev * 0.01)  # grobe Näherung
        fuel_corr = fuel_flow_interp * (1 + oat_dev * 0.025)

        # Windkorrektur
        gs = ktas_corr - hwc
        time_cruise = (total_dist - alt_dist) / gs
        fuel_cruise = time_cruise * fuel_corr

        # Climb
        climb_time, climb_dist, climb_fuel = interpolate_climb(alt_diff, weight, temp_surface)
        if climb_time is None:
            st.error("Climb-Kalkulation fehlgeschlagen.")
        else:
            # Alternate (fix angenommen)
            alt_ktas = 100
            alt_fuel = 17
            time_alt = alt_dist / alt_ktas
            fuel_alt = time_alt * alt_fuel

            total_fuel = fuel_cruise + climb_fuel + 2 + 1 + additional_fuel + fuel_alt + (45 / 60) * fuel_corr
            total_time = climb_time + time_cruise + time_alt

            st.success("Ergebnisse")
            st.write(f"**ISA Temp @ Alt:** {isa_temp:.1f} °C | OAT-Abweichung: {oat_dev:+.1f} °C")
            st.write(f"**Windkomponente:** {hwc} kt ({'Gegenwind +' if hwc > 0 else 'Rückenwind -'}), Seitenwind: {cwc} kt")
            st.write(f"**Climb:** {climb_time:.2f} h, {climb_dist:.1f} NM, {climb_fuel:.1f} l")
            st.write(f"**Cruise GS:** {gs:.1f} kt | Fuel Flow: {fuel_corr:.2f} l/h")
            st.write(f"**Cruise:** {time_cruise:.2f} h, {(total_dist - alt_dist):.1f} NM, {fuel_cruise:.1f} l")
            st.write(f"**Alternate:** {time_alt:.2f} h, {alt_dist:.1f} NM, {fuel_alt:.1f} l")
            st.markdown("---")
            st.write(f"**Totalzeit:** {total_time:.2f} h")
            st.write(f"**Totalverbrauch:** {total_fuel:.1f} l")
