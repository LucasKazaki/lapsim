# TC-02F portable verification receipt

Date: 2026-10-01
Portable environment: Python 3.13.5 on Linux 6.18.44 x86_64.
Evidence level: synthetic portable reference only.

Commands:

```text
python -m unittest -v test_allocator.py test_command_guard.py test_fault_state.py
python -m py_compile allocator.py command_guard.py fault_state.py test_allocator.py test_command_guard.py test_fault_state.py
```

Observed: 48/48 tests passed, 0 failed, 0 skipped; `py_compile` exit 0.

SHA-256:

```text
78e3ab41f06c1e504ba0519a4b1a7b60a6ff27a7598ccc38e7edd76916b4c960  allocator.py
f7fc68668d5a184e91d956be3c98dd960ac8d59de8c85f77e1a5e8bd4117aa51  test_allocator.py
49d77723048eedec0790af3cf9aaebdfce9cf768193aa028695ca819f6e3315b  command_guard.py
003363baccf22a629227a316f7409340a03815cc8614ef5bc3ed5c767baaf12a  test_command_guard.py
f2873dfe96fcd408f00d8c0185b88fe4e1b0726311afd458b812a3818bd8841c  fault_state.py
4330b451419e57feb20b0182bc2e975cf497157a19f1f865b18ccaa5c8f596f2  test_fault_state.py
```

This is not branch CI, native MCU timing, bus validation, vehicle validation, rule compliance, team approval, or independent review.
