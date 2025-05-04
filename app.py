import pandas as pd
import numpy as np
import streamlit as st

# Daten laden
cruise_df = pd.read_csv("tecnam_cruise_performance.csv")
climb_df = pd.read_csv("tecnam_climb_performance_corrected.csv")

# Hilfsfunktionen
def interpolate_climb(alt_ft, weight, temp):
    climb_df["Pressure Altitude [ft]"] = pd.to_numeric(climb_df["Pressure Altitude [ft]"], errors='coerce')
    levels = pd.to_numeric(climb_df["Pressure Altitude [ft]"], errors='coerce').dropna().unique()
    if alt_ft > max(levels):
        st.error("Zielhöhe außerhalb des gültigen Bereichs der Tabelle.")
        return None, None, None

    matching_rows = climb_df[climb_df["Pressure Altitude [ft]"] <= alt_ft]
    if matching_rows.empty:
        st.error("Keine passenden Climb-Daten gefunden.")
        return None, None, None

    grouped = climb_df.groupby("Pressure Altitude [ft]")
    alts = sorted(grouped.groups.keys())
    roc_list = []
    for alt in alts:
        group = grouped.get_group(alt)
        temp_vals = [int(c.split("@")[1].replace("°C", "").strip()) for c in group.columns if "@" in c]
        if len(temp_vals) == 0:
            continue
        rocs = [np.interp(weight, group["Weight [kg]"], group[f"ROC @{t}°C"]) for t in temp_vals]
        roc_list.append(np.interp(temp, temp_vals, rocs))

    roc_avg = np.mean(roc_list)
    time = alt_ft / roc_avg / 60  # Stunden
    speed = 80  # angenommene climb speed in kt
    dist = alt_ft / (roc_avg / speed) / 6076  # NM
    fuel = time * 20  # angenommene Verbrauchsrate in l/h
    return time, dist, fuel

def format_time(hours):
    h = int(hours)
    m = int(round((hours - h) * 60))
    return f"{h}:{m:02d}"

# UI
st.title("P2008 JC Climb & Cruise Calculator")

weight = st.number_input("Gewicht [kg]", 550, 650, 600)
airfield_alt = st.number_input("Pressure Altitude Startplatz [ft]", 0, 14000, 1000)
altitude = st.number_input("Reiseflughöhe [ft]", 0, 14000, 4000)
temp_surface = st.number_input("Außentemperatur am Startplatz [°C]", -30, 50, 15)
track = st.number_input("Track (Kursrichtung) [°]", 0, 360, 180)
wind_dir = st.number_input("Windrichtung (woher) [°]", 0, 360, 180)
wind_speed = st.number_input("Windstärke [kt]", 0.0, 100.0, 0.0)
rpm = st.selectbox("Propeller RPM", sorted(cruise_df["Propeller RPM"].unique(), reverse=True))
total_distance = st.number_input("Gesamtdistanz [NM]", 10.0, 1000.0, 100.0)
alternate_distance = st.number_input("Alternate Distanz [NM]", 0.0, 100.0, 0.0)
additional_fuel = st.number_input("Zusätzlicher Kraftstoff [l]", 0.0, 100.0, 0.0)

# Temperatur in Reiseflughöhe berechnen (ISA -2°C/1000ft)
temp_at_alt = temp_surface - ((altitude - airfield_alt) / 1000 * 2)
st.markdown(f"**Berechnete Temperatur auf Reiseflughöhe:** {temp_at_alt:.1f} °C")

# Climb
alt_diff = altitude - airfield_alt
if alt_diff < 0:
    st.error("Zielhöhe liegt unterhalb der Startplatzhöhe.")
else:
    climb_time, climb_dist, climb_fuel = interpolate_climb(alt_diff, weight, temp_surface)

    if climb_time is None:
        st.warning("Climb-Kalkulation fehlgeschlagen.")
    else:
        # Cruise Daten filtern
        cruise_subset = cruise_df[(cruise_df["Pressure Altitude [ft]"] == altitude) &
                                  (cruise_df["Propeller RPM"] == rpm)]
        if cruise_subset.empty:
            st.error("Keine passenden Cruise-Daten gefunden.")
        else:
            ktas_vals = np.interp(weight, cruise_subset["Weight [kg]"], cruise_subset["KTAS"].values)
            fuel_flow_vals = np.interp(weight, cruise_subset["Weight [kg]"], cruise_subset["Fuel Consumption [lt/hr]"].values)

            # Temperaturkorrektur
            isa_temp = 15 - (altitude / 1000 * 2)
            delta_temp = temp_at_alt - isa_temp
            ktas_corr = ktas_vals * (1 + (0.01 * delta_temp / 15))
            fuel_corr = fuel_flow_vals * (1 + (0.025 * delta_temp / 15))

            # Windkorrektur
            wind_angle_rad = np.radians(wind_dir - track)
            wind_comp = wind_speed * np.cos(wind_angle_rad)
            crosswind = wind_speed * np.sin(wind_angle_rad)
            groundspeed = ktas_corr + wind_comp

            # Restdistanz nach Climb
            cruise_distance = max(0, total_distance - climb_dist)
            cruise_time = cruise_distance / groundspeed
            cruise_fuel = cruise_time * fuel_corr

            # Alternate (600 kg, 2000 RPM, 4000 ft fix)
            alt_data = cruise_df[(cruise_df["Pressure Altitude [ft]"] == 4000) & (cruise_df["Propeller RPM"] == 2000)]
            if alt_data.empty:
                alternate_time = 0
                alternate_fuel = 0
            else:
                alt_speed = np.interp(600, alt_data["Weight [kg]"], alt_data["KTAS"].values)
                alt_flow = np.interp(600, alt_data["Weight [kg]"], alt_data["Fuel Consumption [lt/hr]"].values)
                alternate_time = alternate_distance / alt_speed
                alternate_fuel = alternate_time * alt_flow

            total_time = climb_time + cruise_time
            total_fuel = climb_fuel + cruise_fuel + 2 + 1 + additional_fuel + (alt_flow * 0.75 if alt_data is not None else 0)

            st.success("Ergebnisse")
            st.write(f"ISA Temp @ Alt: {isa_temp:.1f} °C | OAT-Abweichung: {delta_temp:+.1f} °C")
            st.write(f"Windkomponente: {wind_comp:.1f} kt ({'Rückenwind -' if wind_comp > 0 else 'Gegenwind +'})")
            st.write(f"Seitenwind: {abs(crosswind):.1f} kt")
            st.write(f"Climb: {format_time(climb_time)}, {climb_dist:.1f} NM, {climb_fuel:.1f} l")
            st.write(f"Cruise GS: {groundspeed:.1f} kt | Fuel Flow: {fuel_corr:.2f} l/h")
            st.write(f"Cruise: {format_time(cruise_time)}, {cruise_distance:.1f} NM, {cruise_fuel:.1f} l")
            st.write(f"\n**Kraftstoffübersicht:**")
            st.write(f"Startzuschlag: 2.0 l")
            st.write(f"Landung: 1.0 l")
            st.write(f"Zusatzkraftstoff: {additional_fuel:.1f} l")
            st.write(f"Reserve (45 Min @ {alt_flow:.1f} l/h): {alt_flow * 0.75:.1f} l")
            st.write(f"Alternate-Flug: {format_time(alternate_time)}, {alternate_distance:.1f} NM, {alternate_fuel:.1f} l")
            st.write(f"**Gesamtdauer:** {format_time(total_time)}")
            st.write(f"**Gesamtverbrauch:** {total_fuel + alternate_fuel:.1f} Liter")
