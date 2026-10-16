# TC-03B20 source index — cross-clock timestamp alignment

Accessed 2026-10-04.

## NIST primary sources

1. J. C. Eidson and K. B. Lee, “Sharing a Common Sense of Time,” IEEE
   Instrumentation & Measurement Magazine, 2003. NIST publication page:
   https://www.nist.gov/publications/sharing-common-sense-time

   Claim used: distributed measurement/control systems can separate
   synchronization concerns from communication latency when components share
   synchronized real-time clocks. This supports treating clock alignment as
   evidence that must be established rather than inferred from raw timestamp
   values.

2. M. A. Weiss et al., “A Calibration of Timing Accuracy in the NIST
   Cyber-Physical Systems Testbed,” NIST Technical Note 2030, 2018.
   https://www.nist.gov/publications/calibration-timing-accuracy-nist-cyber-physical-systems-testbed-0

   Claim used: synchronization accuracy, stability, latency, and timestamping
   layer all require measurement and uncertainty characterization. The
   published testbed found materially different errors for synchronized clocks,
   unsupported embedded devices, and GPIO-level timestamping. Those numerical
   results are not transferred to Terps Racing.

## STMicroelectronics primary sources

- STM32F405/415 documentation catalogue:
  https://www.st.com/en/microcontrollers-microprocessors/stm32f405-415/documentation.html
  Current observed family documents include RM0090 and DS8626.

- Existing project source pin:
  `projects/enme408-torque-control/research/SOURCES-TC-03B12.md`
  records DS8626 Rev 12 (March 2026) oscillator-accuracy evidence and explicitly
  states that the actual Terps Racing oscillator source, calibration, operating
  envelope, and synchronization between clock domains are unverified.

Applicability: STM32 family clock specifications and NIST timing methodology
show why independent clocks need explicit alignment/error evidence. They do not
establish that the 2027-28 car has multiple ECUs, uses clock synchronization,
uses PTP/NTP/GNSS, or has any particular offset/skew value.

## Formula SAE

Official resources:
https://www.fsaeonline.com/cdsweb/gen/DocumentResources.aspx

Current observed resource: `2027 Formula SAE Rules`, Version `V1`.

No Formula SAE timing, timeout, synchronization, or torque threshold is encoded
by TC-03B20.
