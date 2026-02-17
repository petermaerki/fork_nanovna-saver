import sys

servo_min_t = 0.4
servo_max_t = 1.1

"""

Karte: https://ns6t.net/azimuth/azimuth.html
Das Servo kann eine Position von servo_min_t bis servo_max_t gemessen in Turns annehmen.
1 Turn entspricht 360 Grad.
Ein kleiner Turn-Wert bedeutet eine kleinere Himmelsrichtung.
Die aktuelle Himmelsrichtung wird gemessen: heading_actual_deg.
Die Ziel-Himmelsrichtung ist: heading_target_deg.
Die Funktion servo_targed_t soll die Servo-Position zurückgeben,
die eingestellt werden muss, damit die aktuelle Himmelsrichtung der Ziel-Himmelsrichtung
entspricht. Die Funktion soll eine lineare Interpolation verwenden, um die Servo-Position
zu berechnen.

Weil die Antenne spiegelsymmetrisch ist, gibt es zwei heading_deg Positionen.

heading_0_180_deg = heading_180_360_deg + 180
Die heading_0_180_deg ist die Position, die kleiner als 180 Grad ist.
Die heading_180_360_deg ist die Position, die größer als 180 Grad ist.

die Funktion servo_target_t berechnet die soll Servo-Position.
Es gibt Fälle wo es zwei mögliche Servo-Positionen gibt. Es soll jene Position zurückgegeben werden, die näher an der aktuellen Servo-Position liegt.
  """


def servo_targed_t(
    servo_t_actual: float = 0.6,
    heading_actual_deg: int = 90,
    heading_target_deg: int = 100,
    servo_min_t: float = 0.4,
    servo_max_t: float = 1.1,
    debug: bool = True,
) -> float:
    if debug:
        print(
            "inputs -> servo_t_actual: {servo_t_actual:.3f}, heading_actual_deg: {heading_actual_deg:d}, "
            "heading_target_deg: {heading_target_deg:d}, range_t: [{servo_min_t:.3f}, {servo_max_t:.3f}]".format(
                servo_t_actual=servo_t_actual,
                heading_actual_deg=int(heading_actual_deg),
                heading_target_deg=int(heading_target_deg),
                servo_min_t=servo_min_t,
                servo_max_t=servo_max_t,
            )
        )
    span_t = servo_max_t - servo_min_t
    heading_actual_deg = int(heading_actual_deg) % 360
    heading_target_deg = int(heading_target_deg) % 360

    heading_alt_deg = (heading_target_deg + 180) % 360

    def delta_deg(from_deg: int, to_deg: int) -> int:
        return ((to_deg - from_deg + 540) % 360) - 180

    def clamp_t(t: float) -> float:
        if t < servo_min_t:
            return servo_min_t
        if t > servo_max_t:
            return servo_max_t
        return t

    def heading_from_t(t: float) -> float:
        return heading_actual_deg + (t - servo_t_actual) * 360

    servo_t_primary_raw = servo_t_actual + (
        delta_deg(heading_actual_deg, heading_target_deg) / 360
    )
    servo_t_alt_raw = servo_t_actual + (
        delta_deg(heading_actual_deg, heading_alt_deg) / 360
    )

    primary_ok = servo_min_t <= servo_t_primary_raw <= servo_max_t
    alt_ok = servo_min_t <= servo_t_alt_raw <= servo_max_t

    decision = ""
    if primary_ok and alt_ok:
        if abs(servo_t_primary_raw - servo_t_actual) <= abs(
            servo_t_alt_raw - servo_t_actual
        ):
            servo_choosen_ta = servo_t_primary_raw
            decision = "both ok, primary has shorter travel"
        else:
            servo_choosen_ta = servo_t_alt_raw
            decision = "both ok, alt has shorter travel"
    elif primary_ok:
        servo_choosen_ta = servo_t_primary_raw
        decision = "only primary ok"
    elif alt_ok:
        servo_choosen_ta = servo_t_alt_raw
        decision = "only alt ok"
    else:
        servo_t_primary = clamp_t(servo_t_primary_raw)
        servo_t_alt = clamp_t(servo_t_alt_raw)
        if abs(servo_t_primary - servo_t_actual) <= abs(
            servo_t_alt - servo_t_actual
        ):
            servo_choosen_ta = servo_t_primary
            decision = "both out of range, primary clamps closer"
        else:
            servo_choosen_ta = servo_t_alt
            decision = "both out of range, alt clamps closer"
    if debug:
        print(
            "normalize headings -> actual: {actual:d}, target: {target:d}, alt: {alt:d}".format(
                actual=heading_actual_deg,
                target=heading_target_deg,
                alt=heading_alt_deg,
            )
        )
        print(
            "primary raw t: {primary_raw:.3f}, alt raw t: {alt_raw:.3f}".format(
                primary_raw=servo_t_primary_raw,
                alt_raw=servo_t_alt_raw,
            )
        )
        print(
            "range ok -> primary: {primary_ok}, alt: {alt_ok}".format(
                primary_ok=primary_ok,
                alt_ok=alt_ok,
            )
        )
        print(
            "decision -> {decision}, chosen: {chosen:.3f}".format(
                decision=decision,
                chosen=servo_choosen_ta,
            )
        )
        sys.stdout.flush()

    if debug:
        _fig, ax = plt.subplots(figsize=(6, 4))
        y_min_line = heading_from_t(servo_min_t)
        y_max_line = heading_from_t(servo_max_t)
        ax.plot(
            [servo_min_t, servo_max_t],
            [y_min_line, y_max_line],
            color="black",
            linewidth=1,
        )

        def cross_lines(
            t: float, heading: float, color: str, label: str
        ) -> None:
            ax.axvline(t, color=color, linewidth=1.2, label=label)
            ax.axhline(heading, color=color, linewidth=1.2)

        cross_lines(servo_t_actual, heading_actual_deg, "blue", "actual")
        cross_lines(servo_t_primary_raw, heading_target_deg, "green", "target")
        cross_lines(servo_t_alt_raw, heading_alt_deg, "orange", "target alt")
        ax.scatter(
            [servo_choosen_ta],
            [heading_from_t(servo_choosen_ta)],
            color="red",
            label="chosen",
            zorder=5,
        )
        left_span = servo_min_t - 0.05 * span_t
        right_span = servo_max_t + 0.05 * span_t
        ax.axvspan(
            left_span,
            servo_min_t,
            color="lightgray",
            alpha=0.4,
            label="out of range",
        )
        ax.axvspan(servo_max_t, right_span, color="lightgray", alpha=0.4)
        ax.axvline(
            servo_min_t,
            color="dimgray",
            linewidth=2,
            linestyle="--",
            label="servo min/max",
        )
        ax.axvline(servo_max_t, color="dimgray", linewidth=2, linestyle="--")
        ax.set_xlim(left_span, right_span)
        y_candidates = [
            y_min_line,
            y_max_line,
            heading_actual_deg,
            heading_target_deg,
            heading_alt_deg,
            heading_from_t(servo_choosen_ta),
        ]
        y_min = min(y_candidates)
        y_max = max(y_candidates)
        ax.set_ylim(y_min - 10, y_max + 10)
        ax.set_xlabel("servo t")
        ax.set_ylabel("heading deg")
        ax.set_title("servo target sketch")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper left")
        ax.text(
            0.02,
            0.02,
            "decision: {decision}".format(decision=decision),
            transform=ax.transAxes,
            fontsize=8,
            va="bottom",
        )
        plt.tight_layout()
        plt.show()
    return servo_choosen_ta


def main():
    # servo_targed_t(servo_t_actual = 0.5, heading_actual_deg = 90, heading_target_deg = 10, servo_min_t = 0.4, servo_max_t = 1.1)
    # servo_targed_t(servo_t_actual = 0.6, heading_actual_deg = 90, heading_target_deg = 100, servo_min_t = 0.4, servo_max_t = 1.1)
    # servo_targed_t(servo_t_actual = 1.05,  heading_actual_deg = 0, heading_target_deg = 145, servo_min_t = 0.4, servo_max_t = 1.1)
    # servo_targed_t(servo_t_actual = 0.75,  heading_actual_deg = 90, heading_target_deg = 200, servo_min_t = 0.4, servo_max_t = 0.5)
    servo_targed_t(
        servo_t_actual=1.05,
        heading_actual_deg=0,
        heading_target_deg=845,
        servo_min_t=0.4,
        servo_max_t=1.1,
    )


if __name__ == "__main__":
    import matplotlib

    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt

    main()
