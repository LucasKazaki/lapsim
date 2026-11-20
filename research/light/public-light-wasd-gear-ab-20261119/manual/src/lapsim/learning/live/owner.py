"""Actual Windows child-side custody checks for the existing supervised owner.

No fake admission flag or observer is accepted here. Construction requires a
real constrained Job, the original live creator handle and a finite deadline.
This is the episode's child-side port, NOT a replacement for the parent's real
shared FileLock, observation pump, Job watchdog, launch/GO ordering, terminal
observation, attributable empty-tree proof and checked handle closure.

There is intentionally no standalone CLI or permissive fallback. The fixed
parent GO call site must retain those original controls before using attach().
"""
from dataclasses import dataclass
from math import isfinite
import os
import threading
import time


class OwnerUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ChildLimits:
    cpu_affinity_mask: int
    process_memory_bytes: int
    job_memory_bytes: int
    evidence_bytes: int

    def __post_init__(self):
        for value in (self.cpu_affinity_mask, self.process_memory_bytes,
                      self.job_memory_bytes, self.evidence_bytes):
            if type(value) is not int or value <= 0:
                raise ValueError('positive finite fixed integer bounds required')
        if self.cpu_affinity_mask.bit_count() > 2:
            raise ValueError('one logical CPU required for initial serial smoke test')
        if (self.cpu_affinity_mask.bit_length() > 64
                or self.job_memory_bytes > 1073741824
                or self.evidence_bytes > 167772160):
            raise ValueError('bounded at-most-two-CPU/1GiB/evidence limit exceeded')
        if self.process_memory_bytes > self.job_memory_bytes:
            raise ValueError('process memory cannot exceed aggregate Job memory')


class SupervisedChildOwner:
    """Single process/thread; borrowed creator handle never closed by this port.

    attach() is an internal GO seam, not an admission API. The parent's actual
    reservation, lease and source-authenticated supervision remain mandatory.
    Parent death/Job kill/deadline/custody loss permanently stops this instance.
    The parent must kill and prove its own tree on failure, before lease release.
    """
    __slots__ = ('operation_id', '_limits', '_parent', '_parent_pid', '_parent_created',
                 '_pid', '_thread', '_deadline', '_api', '_types', '_failure',
                 '_evidence', '_closed', '_custody')

    @classmethod
    def attach(cls, *, operation_id, creator_handle, creator_pid,
               creator_creation_filetime, deadline_monotonic, limits):
        if os.name != 'nt' or cls is not SupervisedChildOwner:
            raise OwnerUnavailable('original Windows supervised child only')
        if (type(operation_id) is not str or not 1 <= len(operation_id) <= 128
                or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in operation_id)
                or type(creator_handle) is not int or creator_handle <= 0
                or type(creator_pid) is not int or creator_pid <= 0
                or type(creator_creation_filetime) is not int or creator_creation_filetime <= 0
                or type(deadline_monotonic) not in (int, float)
                or not isfinite(deadline_monotonic) or type(limits) is not ChildLimits):
            raise OwnerUnavailable('exact real creator identity/deadline/limits required')
        remaining = deadline_monotonic - time.monotonic()
        if not 0 < remaining <= 14400:
            raise OwnerUnavailable('finite enclosing14400s deadline required')
        # Declarations and calls are reached only under a real future admitted GO.
        import ctypes as C
        from ctypes import wintypes as W
        k = C.WinDLL('kernel32', use_last_error=True)
        class IO(C.Structure):
            _fields_ = [(n, C.c_ulonglong) for n in
                ('ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
                 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]
        class BASIC(C.Structure):
            _fields_ = [('PerProcessUserTimeLimit', C.c_longlong), ('PerJobUserTimeLimit', C.c_longlong),
                ('LimitFlags', W.DWORD), ('MinimumWorkingSetSize', C.c_size_t),
                ('MaximumWorkingSetSize', C.c_size_t), ('ActiveProcessLimit', W.DWORD),
                ('Affinity', C.c_size_t), ('PriorityClass', W.DWORD), ('SchedulingClass', W.DWORD)]
        class EXTENDED(C.Structure):
            _fields_ = [('BasicLimitInformation', BASIC), ('IoInfo', IO),
                ('ProcessMemoryLimit', C.c_size_t), ('JobMemoryLimit', C.c_size_t),
                ('PeakProcessMemoryUsed', C.c_size_t), ('PeakJobMemoryUsed', C.c_size_t)]
        functions = {}
        declarations = {
            'GetCurrentProcess': ([], W.HANDLE),
            'GetProcessId': ([W.HANDLE], W.DWORD),
            'GetProcessTimes': ([W.HANDLE, C.POINTER(W.FILETIME), C.POINTER(W.FILETIME),
                                  C.POINTER(W.FILETIME), C.POINTER(W.FILETIME)], W.BOOL),
            'IsProcessInJob': ([W.HANDLE, W.HANDLE, C.POINTER(W.BOOL)], W.BOOL),
            'QueryInformationJobObject': ([W.HANDLE, C.c_int, W.LPVOID, W.DWORD, C.POINTER(W.DWORD)], W.BOOL),
            'GetProcessAffinityMask': ([W.HANDLE, C.POINTER(C.c_size_t), C.POINTER(C.c_size_t)], W.BOOL),
            'GetPriorityClass': ([W.HANDLE], W.DWORD),
            'WaitForSingleObject': ([W.HANDLE, W.DWORD], W.DWORD),
        }
        for name, (args, result) in declarations.items():
            f = getattr(k, name)
            f.argtypes, f.restype = args, result
            functions[name] = f
        self = cls.__new__(cls)
        self.operation_id, self._limits = operation_id, limits
        self._parent, self._parent_pid, self._parent_created = creator_handle, creator_pid, creator_creation_filetime
        self._pid, self._thread = os.getpid(), threading.get_ident()
        self._deadline, self._api, self._types = deadline_monotonic, functions, (C, W, EXTENDED)
        self._failure, self._evidence, self._closed = None, 0, False
        self._custody = (operation_id, limits, creator_handle, creator_pid,
                         creator_creation_filetime, self._pid, self._thread, deadline_monotonic,
                         tuple(functions.items()), self._types)
        self.require_owner_live()
        return self

    def require_owner_live(self):
        if self._failure is not None:
            raise self._failure
        try:
            if (self._closed or os.getpid() != self._pid or threading.get_ident() != self._thread
                    or time.monotonic() >= self._deadline):
                raise OwnerUnavailable('owner closed, wrong process/thread or original deadline expired')
            if self._custody != (self.operation_id, self._limits, self._parent, self._parent_pid,
                    self._parent_created, self._pid, self._thread, self._deadline,
                    tuple(self._api.items()), self._types):
                raise OwnerUnavailable('retained owner custody changed')
            C, W, EXTENDED = self._types
            f = self._api
            if f['GetProcessId'](self._parent) != self._parent_pid:
                raise OwnerUnavailable('creator handle identity differs')
            times = [W.FILETIME() for _ in range(4)]
            if not f['GetProcessTimes'](self._parent, *(C.byref(t) for t in times)):
                raise OwnerUnavailable('creator identity time unavailable')
            created = times[0].dwLowDateTime | (times[0].dwHighDateTime << 32)
            if created != self._parent_created or f['WaitForSingleObject'](self._parent, 0) != 0x102:
                raise OwnerUnavailable('creator changed, exited or wait uncertain')
            current, member = f['GetCurrentProcess'](), W.BOOL()
            if not f['IsProcessInJob'](current, None, C.byref(member)) or not member.value:
                raise OwnerUnavailable('actual constrained Job membership absent')
            info, returned = EXTENDED(), W.DWORD()
            if (not f['QueryInformationJobObject'](None, 9, C.byref(info), C.sizeof(info), C.byref(returned))
                    or returned.value != C.sizeof(info)):
                raise OwnerUnavailable('actual enclosing Job limits unavailable')
            b = info.BasicLimitInformation
            required = 0x2000 | 0x8 | 0x10 | 0x20 | 0x100 | 0x200
            limit = self._limits
            if (b.LimitFlags & required != required or b.ActiveProcessLimit != 1
                    or b.Affinity != limit.cpu_affinity_mask or b.PriorityClass != 0x4000
                    or info.ProcessMemoryLimit != limit.process_memory_bytes
                    or info.JobMemoryLimit != limit.job_memory_bytes):
                raise OwnerUnavailable('actual Job CPU/memory/process/priority limits differ')
            process_mask, system_mask = C.c_size_t(), C.c_size_t()
            if (not f['GetProcessAffinityMask'](current, C.byref(process_mask), C.byref(system_mask))
                    or process_mask.value != limit.cpu_affinity_mask
                    or f['GetPriorityClass'](current) != 0x4000):
                raise OwnerUnavailable('actual process CPU affinity/priority differ')
            if time.monotonic() >= self._deadline:
                raise OwnerUnavailable('original deadline expired during ownership checks')
        except BaseException as error:
            self._failure = error
            raise

    def remaining_seconds(self):
        self.require_owner_live()
        return self._deadline-time.monotonic()

    def reserve_evidence(self, size):
        self.require_owner_live()
        if type(size) is not int or size < 0 or self._evidence + size > self._limits.evidence_bytes:
            error = OwnerUnavailable('operation-wide evidence bound exhausted')
            self._failure = error
            raise error
        self._evidence += size

    def stop(self):
        """Local stop only. Parent owns Job/tree/actor/lease cleanup and admission."""
        self._closed = True