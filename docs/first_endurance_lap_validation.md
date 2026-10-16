# First endurance-lap analysis

The active distance-domain recorded-control workflow is
[`analysis/endurance/analyze_endurance.py`](../analysis/endurance/analyze_endurance.py).
See [its instructions](../analysis/endurance/README.md) for inputs and outputs.
The former `scripts/validate_first_endurance_lap.py` is absent from this revision.

```powershell
python analysis/endurance/analyze_endurance.py --help
```

Executing the analysis requires the recorded lap, high-rate controls, corrected
IMU and track inputs identified by those options. Use authorized local inputs;
their presence in repository history does not establish redistribution rights.
No new measured-data correlation was run for this documentation repair.

[The earlier SOC report](first_lap_soc_validation.md) is historical evidence.
Its brake-free model description and numerical results do not describe the
current pressure-to-brake-torque implementation or establish current accuracy.
