# Monitoring Detectors

This page provides an overview of the anomaly detectors running in the SCADA system. During the hackathon, these detectors monitor whether the data received by the SCADA remains consistent with the expected behaviour of the wind farm.

Some detectors check for values outside broad physical limits. Others compare a turbine against a simple physical model, its own setpoints, or the behaviour of the rest of the wind farm. A single noisy sample is usually not sufficient to raise an alarm: several detectors require a suspicious condition to persist for a short time.

Most angle logic uses the shortest wraparound distance:

$$
d(a,b)=\left|\operatorname{wrap}_{[-180,180)}(b-a)\right|
$$

Therefore, \(359^\circ\) and \(1^\circ\) are treated as \(2^\circ\) apart.

## Expected Power

Alarm: `Pmeas != Pexpected`

This detector checks whether a turbine is producing approximately the amount of power expected from the wind, with the observed yaw offset angle, and its current control mode. To avoid reacting to one noisy sample, it compares short-window averages over the available 10-sample history buffers.

The controller first estimates yaw-adjusted available power:

$$
P_{\mathrm{avail}}
= \min\left(
\frac{1}{2}\eta\rho A C_p v^3 \cos^3(e_{\mathrm{yaw}}),
P_{\mathrm{rated}}
\right)
$$

Here \(v\) is wind speed, \(A=\pi R^2\) is the swept rotor area, and \(e_{\mathrm{yaw}}\) is the angle between the wind direction and turbine yaw. The \(\cos^3(e_{\mathrm{yaw}})\) term captures the loss from pointing away from the wind. If the wind is below cut-in or at or above cut-out speed, the available power is taken as zero.

The expected power then depends on the controller mode:

$$
P_{\mathrm{expected}} =
\begin{cases}
P_{\mathrm{avail}}, & \text{Komega}^2 \text{ mode} \\
\min(P_{\mathrm{setpoint}}, P_{\mathrm{avail}}), & \text{down-regulation mode} \\
0, & \text{disabled or shutdown}
\end{cases}
$$

The alarm triggers if average measured power stays too far away from average expected power for \(5\,\mathrm{s}\):

$$
\left|\overline{P}_{\mathrm{measured}}
- \overline{P}_{\mathrm{expected}}\right|
>
\max\left(500\,\mathrm{kW},
0.05\,\overline{P}_{\mathrm{expected}}\right)
$$

## Yaw Orientation Dynamics

Alarm: `Orientation`

A turbine cannot instantly rotate to a new yaw angle. This detector predicts where the turbine should be pointing if it moves toward its yaw setpoint at the allowed yaw rate, currently \(5^\circ/\mathrm{s}\):

$$
\theta_{\mathrm{pred}}(t+\Delta t)
= \operatorname{norm}\left(
\theta(t)
+ \operatorname{clamp}\left(
\operatorname{wrap}(\theta_{\mathrm{set}}-\theta(t)),
-r_{\mathrm{yaw}}\Delta t,
r_{\mathrm{yaw}}\Delta t
\right)
\right)
$$

with \(r_{\mathrm{yaw}}=5^\circ/\mathrm{s}\).

When a fresh yaw measurement arrives, it is suspicious if it is more than \(8^\circ\) away from the prediction:

$$
d(\theta_{\mathrm{pred}},\theta_{\mathrm{measured}}) > 8^\circ
$$

This detector identifies yaw values that jump, move too quickly, or otherwise do not follow the commanded yaw motion.

## Power, Torque, and Rotor Speed

Alarm: `P != ω * Tgen`

Power, generator torque, and rotor speed are tied together. The controller uses:

$$
P_{\mathrm{expected}}
= \eta \cdot \mathrm{rpm}\cdot\frac{2\pi}{60}\cdot
T_{\mathrm{gen}}\cdot G
$$

where \(G\) is the gearbox ratio. The check is skipped when the power and RPM timestamps are more than \(1\,\mathrm{s}\) apart. Otherwise, the alarm is raised when:

$$
\left|P_{\mathrm{measured}}-P_{\mathrm{expected}}\right|
> 400\,\mathrm{kW}
$$

For participants, the relevant point is that power, torque, and RPM must remain mutually consistent.

## Farm Total Power

Alarm: `Prec != Pmeas`

This is a broad farm-level consistency check. The detector compares the average locally measured farm power with the sum of the average received turbine powers. It uses the recent 10-sample history buffers, so brief spikes are smoothed out:

$$
\left|
\sum_i \overline{P}_{\mathrm{received},i}
- \overline{P}_{\mathrm{total,measured}}
\right|
> 10\,\mathrm{MW}
$$

Only turbines with fresh received power are included in the received-power sum. This check catches large mismatches between the reported farm production and the locally measured farm production.

## Wind Direction and Wind Changes

Alarms: `WD Consistency`, `WD change`, `WS Change`

The simplest wind-direction check compares each turbine's wind direction with the global wind direction using the same wraparound angle distance:

$$
d(\mathrm{wd}_{\mathrm{turbine}},\mathrm{wd}_{\mathrm{global}})
> 25^\circ
$$

That threshold is intentionally wide. It is intended to catch clearly incompatible direction values, not ordinary local variation.

The controller also watches for abrupt wind changes in the short history buffers. These checks need at least 5 samples and must be suspicious 3 checks in a row.

For wind speed:

$$
\left|v_{\mathrm{new}}-\operatorname{median}(v_{\mathrm{previous}})\right|
> 3\,\mathrm{m/s}
$$

and:

$$
\max(v_{\mathrm{history}})-\min(v_{\mathrm{history}})
> 4\,\mathrm{m/s}
$$

For wind direction:

$$
d\left(\mathrm{wd}_{\mathrm{new}},
\operatorname{circularMean}(\mathrm{wd}_{\mathrm{previous}})\right)
> 25^\circ
$$

and:

$$
\operatorname{angularSpread}(\mathrm{wd}_{\mathrm{history}}) > 40^\circ
$$

The circular mean is used in the change detector so directions near \(0^\circ\) and \(360^\circ\) behave properly.

## Telemetry Freeze or Replay

Alarm: `Telemetry Freeze`

This detector looks for active signals that stop changing. This can happen when telemetry is frozen, replayed, or replaced with a constant but plausible-looking value.

It checks for wind speed, wind direction, RPM, power, and generator torque. A signal becomes suspicious when both

- The signal is active: wind speed \(>1\,\mathrm{m/s}\), wind direction \(>0^\circ\), RPM \(>0.5\), power \(>1000\,\mathrm{W}\), or torque \(>50\,\mathrm{Nm}\), depending on the signal.
- The observed range is exactly zero, where the range is
$$
\operatorname{range}(x)=\max(x)-\min(x)
$$

For wind direction, the detector uses angular spread around the circular mean. The frozen condition must last for \(1.5\,\mathrm{s}\) before the alarm is raised.

## Drivetrain Under-Response

Alarm: `Small ω/Tgen`

This detector checks whether the drivetrain response is plausible given the wind
speed and yaw angle.

First, the controller estimates the effective wind speed seen by the rotor:

$$
v_{\mathrm{eff}}=\max\left(0, v\cos(e_{\mathrm{yaw}})\right)
$$

Then it estimates the expected rotor speed from the optimal tip-speed ratio:

$$
\mathrm{rpm}_{\mathrm{expected}}
= \operatorname{clamp}\left(
\frac{\lambda_{\mathrm{opt}}v_{\mathrm{eff}}}{R}
\frac{60}{2\pi},
\mathrm{rpm}_{\min},
\mathrm{rpm}_{\mathrm{rated}}
\right)
$$

The corresponding generator torque is:

$$
T_{\mathrm{expected}}
=
\frac{P_{\mathrm{expected}}}
{\eta\,\omega_{\mathrm{rotor}}\,G}
$$

The detector raises an alarm if RPM is below 70% of expected or torque is below 60% of expected for \(5\,\mathrm{s}\). The torque check only applies when expected power is at least \(500\,\mathrm{kW}\).

A more severe aerodynamic collapse only needs to last \(1.5\,\mathrm{s}\). That collapse means:

$$
\mathrm{rpm}_{\mathrm{measured}} < 0.15\,\mathrm{rpm}_{\mathrm{expected}}
$$

and:

$$
|T_{\mathrm{measured}}|
<
\max\left(200\,\mathrm{Nm}, 0.15\,T_{\mathrm{aero}}\right)
$$

This catches cases where the reported power or operating mode implies that the turbine should be responding, while the drivetrain telemetry indicates little or no response.

## Static Bounds

Alarm: `Static Bounds`

This detector is the first line of defence against impossible values. Fresh measurements, within \(3\,\mathrm{s}\), are checked against broad engineering
limits:

- Wind speed: \(0 \le v \le 1.5\,v_{\mathrm{cutout}}\).
- Wind direction and yaw: \(0^\circ \le \theta \le 360^\circ\).
- Yaw: within \(60^\circ\) of global wind direction when wind speed is at or above cut-in.
- RPM: \(0 \le \mathrm{rpm} \le 1.5 \times \,\mathrm{rpm}_{\mathrm{rated}}\).
- Power: \(-0.10\,P_{\mathrm{rated}} \le P \le 1.25\,P_{\mathrm{rated}}\).
- Generator torque: \(-0.10\,T_{\max} \le T \le 1.50\,T_{\max}\).

## Fleet Peer Outlier

Alarm: `Outliers`

When all 9 turbines are connected and operating, the controller compares each turbine against the rest of the farm. Turbines without fresh power or RPM are left out of the ratio calculation, and the detector needs at least 7 usable turbines to proceed.

To make the comparison fair, it first normalizes power and RPM by the expected values for each turbine:

$$
r_P=\frac{P_{\mathrm{measured}}}{P_{\mathrm{expected}}},
\qquad
r_{\mathrm{rpm}}=
\frac{\mathrm{rpm}_{\mathrm{measured}}}
{\mathrm{rpm}_{\mathrm{expected}}}
$$

Then it computes the fleet median and median absolute deviation:

$$
\operatorname{MAD}(r)
=\operatorname{median}\left(\left|r_i-\operatorname{median}(r)\right|\right)
$$

A turbine is suspicious when either normalized value is far away from the fleet:

$$
\left|r_P-\operatorname{median}(r_P)\right|
>
\max\left(0.30,4\,\operatorname{MAD}(r_P)\right)
$$

or:

$$
\left|r_{\mathrm{rpm}}-\operatorname{median}(r_{\mathrm{rpm}})\right|
>
\max\left(0.25,4\,\operatorname{MAD}(r_{\mathrm{rpm}})\right)
$$

The outlier must persist for \(8\,\mathrm{s}\). 