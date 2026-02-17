import math


def calculate_safety_distance(
    f_mhz,
    p_watt,
    q_factor,
    loop_diameter_m=1.0,
    loop_area_m2=0.78,
) -> str:
    """Calculates the minimum safety distance for a Magnetic Loop antenna based on H-field limits."""
    f_hz = f_mhz * 1e6
    radius = loop_diameter_m / 2
    area = math.pi * (radius**2)
    l_henry = 1.55e-6
    i_loop = math.sqrt((p_watt * q_factor) / (2 * math.pi * f_hz * l_henry))

    # Capacitor voltage at resonance: V_c = I_loop * X_L (X_L = X_C at resonance)
    x_l = 2 * math.pi * f_hz * l_henry
    v_cap = i_loop * x_l

    # Immissionsgrenzwert IGW (public exposure limit)
    if f_mhz < 1.0:
        h_limit_igw = 1.6
    elif 1.0 <= f_mhz <= 30.0:
        h_limit_igw = 0.73 / f_mhz
    else:
        h_limit_igw = 0.16

    # Anlagengrenzwert OMEN (installation limit) - 5x stricter than IGW
    h_limit_omen = h_limit_igw / 5.0

    r_meters_igw = ((i_loop * area) / (2 * math.pi * h_limit_igw)) ** (1 / 3)
    r_meters_omen = ((i_loop * area) / (2 * math.pi * h_limit_omen)) ** (1 / 3)

    # Calculate radiation resistance and efficiency for small loop antenna
    # R_rad = 31171 x (A/λ²)² Ω  (for circular loop)
    # R_loss = 2πfL / Q
    # η = R_rad / (R_rad + R_loss)
    # P_radiated = P_input x η
    c = 299792458  # speed of light m/s
    wavelength = c / f_hz

    # Radiation resistance (small loop formula)
    r_rad = 31171 * ((loop_area_m2 / (wavelength**2)) ** 2)

    # Loss resistance from Q factor
    omega_l = 2 * math.pi * f_hz * l_henry
    r_loss = omega_l / q_factor

    # Efficiency and radiated power
    efficiency = (r_rad / (r_rad + r_loss)) * 100.0
    p_radiated = p_watt * (r_rad / (r_rad + r_loss))

    lines = [
        f"Antenna Q Factor: {q_factor:.0f}",
        f"Antenna SWR: todo",
        f"Antenna Bandwith 3dB: todo kHz",
        f"TX Frequency: {f_mhz:.3f} MHz",
        f"TX Power Transmitter: {p_watt:.0f} W",
        f"Antenna Efficiency: {efficiency:.1f} %",
        f"Antenna P Radiated: {p_radiated:.2f} W",
        f"Antenna Loop Current: {i_loop:.1f} A rms",
        f"Antenna Cap Voltage: {v_cap:.0f} V rms",
        f"H-Limit IGW: {h_limit_igw:.3f} A/m",
        f"<b>Safety Distance IGW: {r_meters_igw:.2f} m</b>",
        f"H-Limit OMEN: {h_limit_omen:.3f} A/m",
        f"Safety Distance <a href='https://github.com/petermaerki/fork_nanovna-saver/blob/antenna_tuner/src/NanoVNASaver/antenna_peter/SAFETY_INFO.md'>OMEN</a>: {r_meters_omen:.2f} m",

    ]
    return "<br/>\n".join(lines)
