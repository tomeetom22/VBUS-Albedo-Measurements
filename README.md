# VBUS Albedo Measurements

Campbell Scientific datalogger program and support files for measuring albedo
while walking the VBUS mobile albedo cart across a site. The cart uses paired
LI-COR LI-200R pyranometers and Garmin GPS to record spatially referenced
10-second albedo averages.

## Files to Track

- `VBUS_albedo_cart.cr1x` - current CR1000X walking albedo measurement program.
- `*.CR1X`, `*.cr1x`, `*.CR3` - CRBasic/logger program files.
- `*.DEF`, `*.TDF`, `*.SCW` - Campbell configuration and Short Cut support files.

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
