# VBUS Albedo Measurements

Campbell Scientific datalogger program and support files for measuring albedo
while walking the VBUS mobile albedo cart across a site. The cart uses paired
LI-COR LI-200R pyranometers and Garmin GPS to record spatially referenced
10-second albedo averages.

## Files to Track

- `VBUS_albedo_cart.cr1x` - current CR1000X walking albedo measurement program.
- `*.CR1X`, `*.cr1x`, `*.CR3` - CRBasic/logger program files.
- `*.DEF`, `*.TDF`, `*.SCW` - Campbell configuration and Short Cut support files.

## Wiring

This wiring matches `VBUS_albedo_cart.cr1x`.

### Pyranometers

The program reads two LI-COR LI-200R pyranometers as differential millivolt
signals. Each sensor needs its current signal converted to voltage with the
installed shunt resistor or LI-COR millivolt adapter.

| Sensor | Program variable | CR1000X input | Signal high | Signal low | Shunt value in code |
| --- | --- | --- | --- | --- | --- |
| Down Facing LI-200R | `LI200R_mV`, `SW_Down` | Differential channel 1 | Diff 1 H / U1 | Diff 1 L / U2 | `1003 ohms` |
| Up Facing LI-200R | `LI200R_Up_mV`, `SW_Up` | Differential channel 4 | Diff 4 H / U7 | Diff 4 L / U8 | `999 ohms` |

In the program variable names, `SW_Down` and `SW_Up` refer to sensor
orientation. The down-facing sensor measures reflected shortwave from the
surface, and the up-facing sensor measures incoming shortwave from the sky.
Albedo is calculated as `SW_Down / SW_Up`.

Place each shunt resistor across that sensor's high and low signal terminals.
If irradiance is negative in sunlight, swap that sensor's high/low leads or
change the corresponding multiplier sign in the program.

```text
Down Facing LI-200R  -> shunt/adapter -> Diff 1 H / U1
                                      -> Diff 1 L / U2

Up Facing LI-200R    -> shunt/adapter -> Diff 4 H / U7
                                      -> Diff 4 L / U8
```

### Garmin GPS16X-HVS

The GPS is read on `ComC1` at `38400` baud. The program configures the C1/C2
pair for the GPS receiver with `PortPairConfig(C1, 2)`.

| GPS16X-HVS lead | CR1000X terminal |
| --- | --- |
| Red | `12V` |
| Black | `G` |
| Yellow | `G` |
| Blue | `G` |
| Clear/shield | `G` |
| Grey | `C1` |
| White | `C2` |

```text
Garmin GPS16X-HVS
  Red          -> 12V
  Black/Yellow/Blue/Clear -> G
  Grey         -> C1
  White        -> C2
```

## Files Ignored

Logger output and converted data files are ignored by default:

- `*.dat`
- `TOA5_*.dat`

Keep raw field data backed up separately, and only force-add a data file when it
is small and needed to document a specific code change.

## Useful Commands

```powershell
git status
git add .
git commit -m "Update walking albedo averaging interval"
```
