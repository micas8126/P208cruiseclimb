import streamlit as st
import pandas as pd
import numpy as np
import math

# Daten laden
df = pd.read_csv("tecnam_cruise_performance.csv")
climb_df = pd.read_csv("tecnam_climb_performance_corrected.csv")

# UI
st.title("Tecnam P2008 JC – Cruise + Climb Kalkulation")
st.markdown("Berechnung von **Flugzeit** und **Kraftstoffverbrauch** inkl. Climb, Gewicht, Temperatur, Wind und Interpolation")

# Eingaben
distance = st.number_input("Gesamtdistanz [NM]", min_value=10.0, step=1.0)
airfield_altitude = st.number_input("Startplatz Pressure Altitude [ft]", min_value=0, max_value=10000, step=100)
target_altitude = st.number_input("Reiseflug Pressure Altitude [ft]", min_value=0, max_value=10000, step=100)
rpm = st.selectbox("Propeller RPM", sorted(df["Propeller RPM"].unique()))
weight = st.number_input("Tatsächliches Gewicht [kg]", min_value=550, max_value=650, step=1)
temp_airfield = st.number_input("Außentemperatur am Startplatz [°C]", value=15.0)

tack = st.number_input("Track (Kursrichtung) [°]", min_value=0, max_value=360, step=1)
wind_dir = st.number_input("Windrichtung (woher) [°]", min_value=0, max_value=360, step=1)
wind_speed = st.number_input("Windstärke [kt]", min_value=0.0, step=0.5)

alternate_distance = st.number_input("Alternate Distanz [NM]", min_value=0.0, step=1.0)
additional_fuel = st.number_input("Zusätzlicher Kraftstoff [l]", min_value=0.0, step=0.5)

# Temperatur berechnen auf Reiseflughöhe
lapse_rate = 2
delta_alt = target_altitude - airfield_altitude
temperature = temp_airfield - (delta_alt / 1000) * lapse_rate
st.markdown(f"**Berechnete Temperatur auf Reiseflughöhe:** {temperature:.1f} °C")

# Hilfsfunktionen
def format_time(hours):
    h = int(hours)
    m = int(round((hours - h) * 60))
    return f"{h}:{m:02d} h"

def wind_component(track, wind_dir, wind_speed):
    angle = math.radians(wind_dir - track)
    return wind_speed * math.cos(angle)

def interpolate_climb(alt_diff, weight, temp):
    weights = sorted(climb_df["Weight [kg]"].unique())
    nearest_weights = sorted(weights, key=lambda x: abs(x - weight))[:2]

    results = []
    for w in nearest_weights:
        df_w = climb_df[climb_df["Weight [kg]"] == w].copy()
        df_w["Pressure Altitude [ft]"] = df_w["Pressure Altitude [ft]"].replace("S.L.", 0).astype(int)
        df_w = df_w.sort_values("Pressure Altitude [ft]")

        climb_points = df_w[df_w["Pressure Altitude [ft]"] <= alt_diff]
        if climb_points.empty:
            continue
        last_row = climb_points.iloc[-1]

        temp_cols = [col for col in df_w.columns if "ROC" in col and "ISA" not in col]
        temp_values = [float(col.split("@")[1].replace("°C", "").strip()) for col in temp_cols]
        roc_values = last_row[temp_cols].values.astype(float)
        roc_interp = np.interp(temp, temp_values, roc_values)

        results.append((w, last_row["Climb Speed Vy [KIAS]"], roc_interp))

    if len(results) < 2:
        return 0, 0, 0

    w1, vy1, roc1 = results[0]
    w2, vy2, roc2 = results[1]

    vy = np.interp(weight, [w1, w2], [vy1, vy2])
    roc = np.interp(weight, [w1, w2], [roc1, roc2])

    time_hr = alt_diff / roc / 60
    distance_nm = vy * time_hr * 60 / 6076.12
    fuel_lph = 27
    fuel = time_hr * fuel_lph

    return time_hr, distance_nm, fuel

# Climb Berechnung
alt_diff = target_altitude - airfield_altitude
if alt_diff < 0:
    st.error("Zielhöhe muss über Startplatz liegen.")
else:
    climb_time, climb_dist, climb_fuel = interpolate_climb(alt_diff, weight, temperature)
    remaining_distance = distance - climb_dist

    if remaining_distance <= 0:
        st.error("Distanz zu kurz für Cruise nach Climb.")
    else:
        rpm_df = df[df["Propeller RPM"] == rpm]
        altitudes = sorted(rpm_df["Pressure Altitude [ft]"].unique())
        lower_alts = [alt for alt in altitudes if alt <= target_altitude]
        upper_alts = [alt for alt in altitudes if alt >= target_altitude]

        if not lower_alts or not upper_alts:
            st.error("Nicht genug Daten für Cruise-Interpolation.")
        else:
            alt_low = max(lower_alts)
            alt_high = min(upper_alts)

            if alt_low == alt_high:
                row = rpm_df[rpm_df["Pressure Altitude [ft]"] == alt_low].iloc[0]
                ktas = row["KTAS"]
                fuel_flow = row["Fuel Consumption [l/hr]"]
                isa_temp = row["OAT ISA [°C]"]
            else:
                row_low = rpm_df[rpm_df["Pressure Altitude [ft]"] == alt_low].iloc[0]
                row_high = rpm_df[rpm_df["Pressure Altitude [ft]"] == alt_high].iloc[0]

                def interp(val_low, val_high):
                    return np.interp(target_altitude, [alt_low, alt_high], [val_low, val_high])

                ktas = interp(row_low["KTAS"], row_high["KTAS"])
                fuel_flow = interp(row_low["Fuel Consumption [l/hr]"], row_high["Fuel Consumption [l/hr]"])
                isa_temp = interp(row_low["OAT ISA [°C]"], row_high["OAT ISA [°C]"])

            isa_dev = temperature - isa_temp
            ktas_corr_percent = np.interp(isa_dev, [-15, 0, 15], [1.01, 1.0, 0.98])
            fuel_corr_percent = np.interp(isa_dev, [-15, 0, 15], [1.03, 1.0, 0.975])

            delta_weight = 650 - weight
            ktas_weight_corr = ktas * (1 + 0.033 * (delta_weight / 100))
            ktas_final = ktas_weight_corr * ktas_corr_percent
            fuel_final = fuel_flow * fuel_corr_percent

            wind_corr = wind_component(tack, wind_dir, wind_speed)
            wind_type = "(Gegenwind +)" if wind_corr < 0 else "(Rückenwind -)"
            gs_final = max(ktas_final + wind_corr, 30)

            time_cruise = remaining_distance / gs_final
            fuel_cruise = time_cruise * fuel_final

            # Fixe Zusatzverbräuche
            fuel_departure = 2.0
            fuel_landing = 1.0
            fuel_reserve = 45 / 60 * fuel_final

            # Alternate Berechnung: 600 kg, 2000 RPM, 4000 ft
            alt_df = df[(df["Propeller RPM"] == 2000) & (df["Pressure Altitude [ft]"] == 4000)]
            if not alt_df.empty:
                row = alt_df.iloc[0]
                alt_speed = row["KTAS"] * (1 + 0.033 * (650 - 600) / 100)
                alt_flow = row["Fuel Consumption [l/hr]"]
                alt_time = alternate_distance / alt_speed
                alt_fuel = alt_time * alt_flow
            else:
                alt_time = 0
                alt_fuel = 0

            total_time = time_cruise + climb_time + alt_time
            total_fuel = fuel_cruise + climb_fuel + fuel_departure + fuel_landing + fuel_reserve + additional_fuel + alt_fuel

            h = int(total_time)
            m = int(round((total_time - h) * 60))

            st.success("Ergebnisse")
            st.write(f"**ISA Temp @ Alt:** {isa_temp:.1f} °C  |  **OAT-Abweichung:** {isa_dev:+.1f} °C")
            st.write(f"**Windkomponente:** {wind_corr:.1f} kt {wind_type}")
            st.write(f"**Climb:** {format_time(climb_time)}, {climb_dist:.1f} NM, {climb_fuel:.1f} l")
            st.write(f"**Cruise GS:** {gs_final:.1f} kt  |  Fuel Flow: {fuel_final:.2f} l/h")
            st.write(f"**Cruise:** {format_time(time_cruise)}, {fuel_cruise:.1f} l")
            st.write("---")
            st.write(f"**Alternate:** {format_time(alt_time)}, {alt_fuel:.1f} l")
            st.write(f"**Start:** {fuel_departure:.1f} l | Landung: {fuel_landing:.1f} l | Reserve: {fuel_reserve:.1f} l")
            st.write(f"**Zusätzlich:** {additional_fuel:.1f} l")
            st.write("---")
            st.write(f"**Gesamtdauer:** {format_time(total_time)}")
            st.write(f"**Gesamtverbrauch:** {total_fuel:.1f} Liter")
