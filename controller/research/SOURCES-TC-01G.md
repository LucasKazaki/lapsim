# TC-01G sources — sample-time alignment envelope

Accessed 2026-10-03.

## Project pins

- `projects/enme408-torque-control/reference/kinematic_ediff.py`
  blob `304e50e04a5d3e9a6d07aaa78ae4456da27af1ed`.
- `projects/enme408-torque-control/reference/kinematic_observer.py`
  blob `e8721a7b7c6f4382995bbf1f773276d3e9f2290b`.
- `projects/enme408-torque-control/research/TC-01B.md`
  blob `477fba61d6687f725ee14bbaa3230d672d36f593`.
- `projects/enme408-torque-control/research/SOURCES-TC-01F.md`
  blob `8b1c12f2f683710d2e5cf8a8b9701fe50d5879bb`.

## STM32F4 primary source

STMicroelectronics `stm32f4xx-hal-driver`, current master commit
`1f6451c3e07728b4c830744de380e56bf5bc0026`, committed 2026-06-05,
BSD-3-Clause license blob `479c4f682608052abf9c99e8b71fb6bc2d8d15d7`.

- ADC header `Inc/stm32f4xx_hal_adc.h`, blob
  `c79a073e913dc6bd23b29561db4916755c75ff22`.
  The regular channel configuration defines an explicit sequencer rank and
  per-channel sampling time. Conversion time is documented as sampling time plus
  resolution-dependent processing cycles. This establishes that samples within
  a scanned ADC sequence need not represent one simultaneous physical instant.
- CAN header `Inc/stm32f4xx_hal_can.h`, blob
  `b4c229b209c494669ce05cdef1d4e62ad8c9079d`.
  The receive header exposes a timestamp captured at start of frame reception
  when Time Triggered Communication Mode is enabled. This is receiver-arrival
  evidence, not automatically producer sample time.
- STM32F405 product/documentation catalogue currently lists RM0090 for the
  STM32F405/415 family. Family capability is not evidence of the Terps Racing
  board configuration.

Repository:
https://github.com/STMicroelectronics/stm32f4xx-hal-driver

STM32F405 documentation:
https://www.st.com/en/microcontrollers-microprocessors/stm32f4-series/documentation.html

## Electronic-differential/control context

Julio-Rodriguez, Santana-Diaz, Ramirez-Mendoza,
"Individual Drive-Wheel Energy Management for Rear-Traction Electric Vehicles
with In-Wheel Motors," Applied Sciences 11(10):4679, published 2021-05-20,
DOI 10.3390/app11104679, CC BY 4.0.
https://www.mdpi.com/2076-3417/11/10/4679

The paper's EDS uses wheel angular speed, steering angle, throttle input and
longitudinal speed. It supports the relevance of coherent steering/speed inputs
to a geometry-based electronic differential. Its vehicle parameters, sensor
timing and experimental thresholds are not transferred to Terps Racing.

Sun, Lee, Tian,
"Torque Vectoring Control Strategies for Distributed Electric Drive Formula SAE
Racing Car," SAE 2021-01-0373, published 2021-04-06,
DOI 10.4271/2021-01-0373.
https://saemobilus.sae.org/papers/torque-vectoring-control-strategies-distributed-electric-drive-formula-sae-racing-car-2021-01-0373

This remains the architecture reference separating upper direct-yaw-moment
control from lower torque distribution. TC-01G does not request yaw moment.

## Formula SAE

Formula SAE Series Resources:
https://www.fsaeonline.com/cdsweb/gen/DocumentResources.aspx

Current observed resource: `2027 Formula SAE Rules`, Version `V1`.
TC-01G derives no sample-age, rate, controller, sensor or safety threshold from
the rules resource.

## Mathematical applicability

TC-01G uses deterministic rate bounds, not probability distributions:
if a signal derivative is bounded by `r` over an age `dt`, its unknown
change magnitude is bounded by `r * dt`. The kinematic-reference envelope is
then evaluated with conservative interval arithmetic over the allowed
center-speed and same-turn-direction steering box.

The proof deliberately blocks a steering-age interval that crosses zero because
left/right wheel identity changes there. Raw timebase provenance, clock wrap,
CAN FIFO residence and producer timestamps must already be established by the
earlier TC-02/TC-03 evidence work.

None of these sources establish Terps Racing signal ages, steering rate,
longitudinal/wheel acceleration bounds, geometry, CAN mapping or a diagnostic
threshold.
