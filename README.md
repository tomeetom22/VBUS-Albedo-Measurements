# Albedo Testing

Campbell Scientific datalogger programs and support files for mobile albedo
testing with LI-COR LI-200R pyranometers and Garmin GPS.

## Files to Track

- `VBUS_albedo_cart.cr1x` - current CR1000X albedo cart program.
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
git commit -m "Initial albedo testing code"
```
