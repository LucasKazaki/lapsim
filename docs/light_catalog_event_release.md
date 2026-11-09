# Installed catalog and skidpad commands

The ordinary development distribution is `python-lapsim` version
`0.1.0+light20261108.1`. Its internal version distinguishes this candidate from
the older `0.1.0` wheel. Exact source, wheel and dependency hashes belong to the
external release index; the version string alone is not runtime qualification.

The wheel retains all nine catalog bundles, their approximation descriptions,
source traces and AMZ notices. It also retains the Controller Lab and torque
configurator assets. Installed operation uses immutable packaged resources and
an explicitly selected external directory for studies and exports.

```text
python -m lapsim.torque_configurator serve --work-dir C:\EV-work\studies
```

The existing [catalog search command](tournament_catalog_cli.md) supports one
saved course or a bounded fresh batch of all nine. Its ordinary controllers are
`fixed`, `traction`, `yaw_pi` and `tire_reserve`; it does not select the portable
seven-policy registry. Failed, paused and unrun cells remain in its index.

The installed skidpad command runs the actual ordered event with explicit
scenario choices and preserves full vehicle provenance and telemetry:

```text
lapsim-skidpad --sequence --entry-length-m 2 --exit-length-m 3 --starting-speed-mps 5 --cone-penalty-policy raw-only --output-dir C:\EV-work\skidpad-run-1
```

The example entry/exit lengths are scenario choices, not official dimensions.
See [the event contract](fsae_skidpad_sequence.md) for timed phases, declared
incidents and conflicting penalty sources. There are no official points or
cross-course rankings. Nonpublic vehicle profiles require explicit input data;
public defaults do not discover private intake automatically.
The installed legacy circle command also requires a new external output directory
before computation; it cannot write its checkout default into packaged resources.

The separate frozen portable distribution remains dev25. Its original guarded
FSI one-lap worker, seven policy candidates, source/environment contracts and
admission requirements are unchanged. Use a separate isolated environment for
that worker; installing the ordinary UI and numerical dependencies does not
register an original guard, qualify a policy or admit another course. Skidpad
still requires ordered physical gates/checkpoints before portable dispatch.

The release carries a Windows CPython 3.12 x86-64 dependency recipe. Those wheel
tags and official artifact hashes are checked as packaging facts. Actual Windows
installation, complete runtime observation, original input authentication, native
containment/cleanup and the separately owned one-command launcher remain their
own acceptance requirements. No arbitrary future source update is qualified.
