# TC-03A portable verification receipt

Pre-publication portable verification used Python 3.13.5 on Linux x86_64:

    python -m unittest -v test_team_evidence_packet.py
    python -m py_compile team_evidence_packet.py test_team_evidence_packet.py

Observed: 15/15 tests passed, 0 failed, 0 skipped; py_compile exited 0.

Remote readback at head 1e96c759a53162a40c54bc5bb9af3070d35fe896 succeeded for all four TC-03A files. Git blob IDs:

- team_evidence_packet.py: 79761b624b732ceb8a9567906cdef001941732bf
- test_team_evidence_packet.py: 0c89f4179a834a5da45b572b1b760370709e45ef
- team_evidence_request.example.json: 4923964b04e7beb0bcaa04ca85ca273660431855
- TC-03A.md: 1a90a57645f2ebc5ed7ac2230c6075edadcddefb

No GitHub Actions run was present for that head. Treat the portable local result and remote readback as separate evidence, not branch CI.
