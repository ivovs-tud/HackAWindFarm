# Hack a Wind Farm Python Attack Interface

This repository provides a Python interface for interacting with the Hack a Wind Farm supervisory controller. It lets participants observe selected communication channels and, when enabled, perform false data injection (FDI) attacks against selected turbine signals. 

The interface is specific to the Hack a Wind Farm hackathon setup and is not intended as a general-purpose IEC 61850, SCADA, or wind farm control library. See the ``docs`` folder for an introduction to wind farms and an in-depth description of the hardware setups.

## Requirements

The only Python dependency is ZeroMQ:

```bash
pip install pyzmq
```

## Quick Start

1. Open [example.py](example.py).
2. Set `SERVER_IP` and `PORT` to match the supervisory controller you have been assigned. In most cases, only `SERVER_IP` needs to change.
3. Configure which signals you want to read with `tap_communication()`.
4. Configure which signals you want to overwrite with `fdi_communication()`.
5. Implement your attack logic in `attack_function()`.
6. Run the script:

```bash
python example.py
```

## Basic Usage

The main entry point is the `AttackInterface` class:

```python
from AttackInterface import AttackInterface

def attack_function(data_received, attacks, time_ms):
    attacks["Yaw"][0] = 30.0

attack_interface = AttackInterface()
attack_interface.connect("localhost", 9002)
attack_interface.configure(team_name="PythonAttackClient")

attack_interface.tap_communication(["Yaw", "Power"], [1, 0, 0, 0, 0, 0, 0, 0, 0])
attack_interface.fdi_communication("Yaw", [1, 0, 0, 0, 0, 0, 0, 0, 0])

attack_interface.start(attack_function)
```

The turbine selection argument is always a list of 9 values, one per turbine. Use `1` to enable the selected action for a turbine and `0` to disable it.

## Tapping Signals

Use `tap_communication()` to select which transmitted values your attack function can read.

```python
attack_interface.tap_communication("Yaw", [1, 1, 1, 1, 1, 1, 1, 1, 1])
attack_interface.tap_communication(["Yaw", "Power"], [1, 0, 0, 0, 0, 0, 0, 0, 0])
```

Tapped values are available in the `data_received` dictionary passed to `attack_function()`. Each dictionary entry is a list with one value per turbine. For example, `data_received["Yaw"][0]` contains the latest tapped yaw value for turbine 1.

All signal keys exist by default, but values are only updated for channels and turbines that you have enabled for tapping.

## False Data Injection

Use `fdi_communication()` to select which transmitted values your attack function can overwrite.

```python
attack_interface.fdi_communication("Yaw", [1, 1, 1, 1, 1, 1, 1, 1, 1])
attack_interface.fdi_communication(["Yaw", "Power"], [1, 0, 0, 0, 0, 0, 0, 0, 0])
```

Overwrite values are written through the `attacks` dictionary passed to `attack_function()`. It has the same structure as `data_received`: each key maps to a list of 9 turbine values.

If you enable FDI for a signal and turbine, the value currently stored in `attacks` will be used when the supervisory controller requests an overwrite value. Be careful to write sensible values for every enabled signal and turbine, or keep your enabled FDI set as small as possible.

## Attack Function

Your attack logic must be implemented as a function with three arguments:

```python
def attack_function(data_received, attacks, time_ms):
    pass
```

- `data_received`: latest values observed through enabled taps.
- `attacks`: values that will be sent back for enabled FDI channels.
- `time_ms`: milliseconds since the attack loop started.

For example:

```python
def attack_function(data_received, attacks, time_ms):
    yaw_turbine_1 = data_received["Yaw"][0]

    if time_ms > 10_000:
        attacks["Yaw"][0] = yaw_turbine_1 + 5.0
```

This example reads the latest yaw value for turbine 1 and, after 10 seconds, reports a yaw value that is 5 degrees higher than the observed value. **Note**: This example assumes that `Yaw` has been enabled both for tapping and for FDI on turbine 1. If `Yaw` is not enabled for tapping, then `data_received["Yaw"][0]` is not meaningful and should not be used as a real measurement. Similarly, if `Yaw` is not enabled for FDI, then writing to `attacks["Yaw"][0]` has no effect on the communication.

## Available Signals

_Measurements_: 
- **Wind Speed**: wind speed measured at the turbine.
- **Wind Direction**: wind direction relative to true north.
- **Rotor Speed**: rotor rotational speed.
- **Yaw**: current nacelle yaw angle relative to true north.
- **Blade Pitch**: blade pitch angle.
- **Power**: electrical power output.
- **Generator Torque**: generator torque measurement.

_Setpoints_:
- **Yaw Setpoint**: target yaw angle commanded by the controller, relative to true north.
- **Power Setpoint**: target power output commanded by the controller.

Use these exact strings as keys in `tap_communication()`, `fdi_communication()`, `data_received`, and `attacks`.

## Scoring Note

You are scored on how well your attack performs, but the number of tapped and attacked signals also matters. For the best score, enable only the channels and turbines that your strategy actually needs.
