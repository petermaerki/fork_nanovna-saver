# Technical Background & Safety Compliance

Electromagnetic Field Dynamics (Near-Field)
This application calculates the physical parameters of a high-Q resonant loop antenna. Unlike conventional antennas, a Magnetic Loop operates primarily by generating an intense Magnetic Near-Field (H-Field).

Due to the extremely high resonance quality (Q-factor), the circulating currents within the main inductor (the copper braid) can reach values significantly higher than the feedline current. This leads to:
• High Magnetic Flux Density: Concentrated in the immediate vicinity of the loop.
• Inductive Voltage Peaks: At the tuning capacitor, voltages reach levels that require specific dielectric strength (kV-range).

Computational Methodology
The calculation of the safety distance is based on the Inverse-Cube Law for magnetic dipoles in the near-field (1/r³).

Geometry Factor: The copper braid is modeled using an equivalent conductor radius to account for skin effect and reduced RF resistance.

Inductance & Reactance: These values are derived from the physical diameter and conductor surface area to determine the precise circulating current at a given power level.

Legal Standards (Switzerland)
The safety distances provided are calculated in accordance with the Swiss Ordinance on Protection against Non-Ionizing Radiation (NISV / ONIR).

Immissionsgrenzwerte (IGW): The primary safety boundary is based on the exposure limits for the general public, designed to prevent thermal and non-thermal biological effects.

Frequency Dependence: In the High Frequency (HF) range, the permissible magnetic field strength (H) is frequency-dependent (0.73 / f). The safety distance is dynamically adjusted as you tune your transceiver.

Precautionary Principle: Following Swiss regulatory logic, a safety margin (k-factor) is applied to account for environmental reflections and local field enhancements."""
