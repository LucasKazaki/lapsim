# TC-02A local verification receipt

Date: 2026-10-01
Branch: `research/enme408-tc00-20261001`
Branch head before this note: `3796988018cc8fee2376056237e0afc81b0ab6cd`

The TC-02A prototype was evaluated only in an isolated Python sandbox against the exact TC-01A allocator currently on the branch.

Environment: Python 3.13.5, Linux 6.18.44 x86_64, standard library only.

Commands:

```text
python -m unittest -v test_allocator.py test_fault_state.py
python -m py_compile allocator.py fault_state.py test_allocator.py test_fault_state.py
```

Observed: 27/27 tests passed, 0 failed, 0 skipped; compilation check exited 0.

Prototype SHA-256:
- `fault_state.py`: `6bbc21deafb25a2a7fed51c2935f4fa8a7be2422491d454f9ef1cfe2440374f7`
- `test_fault_state.py`: `21a857c7a6b73734fb5684c86f04c83adba126c2de6ec9f6126f01c02b7ecf42`

The connected write path did not permit publishing those two executable prototype files. They are therefore not part of the GitHub branch or PR #66 and must not be counted as branch CI evidence. The checked-in TC-02A research note records the design and limitations.

No native MCU, CAN-bus, HIL, track, vehicle, or Agent Studio execution was performed.
