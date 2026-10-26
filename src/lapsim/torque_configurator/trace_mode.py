"""Explicit versioned trace/storage allocations; never a physics tolerance."""
from dataclasses import dataclass


@dataclass(frozen=True)
class TraceMode:
    version:int
    maximum_frames:int
    maximum_clock_ms:int|None
    trace_bytes:int
    selected_bytes:int
    aggregate_bytes:int

    def schema(self,kind):return f'lapsim.torque-{kind}.v{self.version}'


MODES={1:TraceMode(1,201,None,1_000_000,8_000_000,64_000_000),
       2:TraceMode(2,6001,60000,4_000_000,32_000_000,96_000_000),
       3:TraceMode(3,60001,600000,40_000_000,256_000_000,512_000_000)}


def trace_mode(*,full_lap=False,ten_lap=False):
    if type(full_lap) is not bool or type(ten_lap) is not bool or full_lap and ten_lap:
        raise ValueError('Choose one explicit Boolean lap/ten-lap trace mode')
    return MODES[3 if ten_lap else 2 if full_lap else 1]
