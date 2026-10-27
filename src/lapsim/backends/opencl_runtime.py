"""Small owned-resource OpenCL 1.2 adapter using an installed system driver.

No installation, CPU fallback, global context or implicit device selection.
The Khronos C API and device compiler are supplied by the installed driver.
This deliberately limited adapter supports FP64, one input/output buffer and
profiled kernels; it is not a general replacement for PyOpenCL.
"""

from __future__ import annotations

import ctypes as ct
from ctypes.util import find_library
from dataclasses import dataclass
from hashlib import sha256
import os
from time import perf_counter
from typing import Any

import numpy as np


class OpenCLError(RuntimeError):
    """Unavailable device or rejected operation; callers must not fall back silently."""


def _check(code: int, operation: str) -> None:
    if code != 0:
        raise OpenCLError(f"{operation} failed with OpenCL status {code}")


@dataclass(frozen=True)
class Device:
    platform: int
    handle: int
    name: str
    vendor: str
    driver: str
    version: str
    fp64: bool


class _API:
    def __getattr__(self, name: str) -> Any:
        # ctypes exposes dynamically typed C function pointers. Signatures are
        # bound explicitly below before any pointer crosses the FFI boundary.
        if name.startswith('cl'):
            return getattr(self.lib,name)
        raise AttributeError(name)

    def __init__(self) -> None:
        path = os.path.join(os.environ["SystemRoot"], "System32", "OpenCL.dll") if os.name == "nt" else find_library("OpenCL")
        if not path:
            raise OpenCLError("No installed OpenCL loader; no runtime was installed")
        try:
            self.lib = ct.WinDLL(path) if os.name == "nt" else ct.CDLL(path)
        except OSError as error:
            raise OpenCLError("Installed OpenCL loader is unavailable") from error
        p, z, u, i, q = ct.c_void_p, ct.c_size_t, ct.c_uint, ct.c_int, ct.c_ulonglong
        self._bind("clGetPlatformIDs", i, [u, ct.POINTER(p), ct.POINTER(u)])
        self._bind("clGetDeviceIDs", i, [p, q, u, ct.POINTER(p), ct.POINTER(u)])
        self._bind("clGetDeviceInfo", i, [p, u, z, p, ct.POINTER(z)])
        self._bind("clCreateContext", p, [p, u, ct.POINTER(p), p, p, ct.POINTER(i)])
        self._bind("clCreateCommandQueue", p, [p, p, q, ct.POINTER(i)])
        self._bind("clCreateProgramWithSource", p, [p, u, ct.POINTER(ct.c_char_p), ct.POINTER(z), ct.POINTER(i)])
        self._bind("clBuildProgram", i, [p, u, ct.POINTER(p), ct.c_char_p, p, p])
        self._bind("clGetProgramBuildInfo", i, [p, p, u, z, p, ct.POINTER(z)])
        self._bind("clCreateKernel", p, [p, ct.c_char_p, ct.POINTER(i)])
        self._bind("clCreateBuffer", p, [p, q, z, p, ct.POINTER(i)])
        self._bind("clSetKernelArg", i, [p, u, z, p])
        self._bind("clEnqueueNDRangeKernel", i, [p, p, u, ct.POINTER(z), ct.POINTER(z), ct.POINTER(z), u, ct.POINTER(p), ct.POINTER(p)])
        self._bind("clEnqueueReadBuffer", i, [p, p, u, z, z, p, u, ct.POINTER(p), ct.POINTER(p)])
        self._bind("clEnqueueWriteBuffer", i, [p, p, u, z, z, p, u, ct.POINTER(p), ct.POINTER(p)])
        self._bind("clGetEventProfilingInfo", i, [p, u, z, p, ct.POINTER(z)])
        self._bind("clFinish", i, [p])
        for name in ("Event", "MemObject", "Kernel", "Program", "CommandQueue", "Context"):
            self._bind("clRelease" + name, i, [p])

    def _bind(self, name, result, arguments) -> None:
        function = getattr(self.lib, name)
        function.restype, function.argtypes = result, arguments
        setattr(self, name, function)

    def text(self, device, key) -> str:
        size = ct.c_size_t()
        _check(self.clGetDeviceInfo(device, key, 0, None, ct.byref(size)), "device info size")
        value = ct.create_string_buffer(size.value)
        _check(self.clGetDeviceInfo(device, key, size, value, None), "device info")
        return value.value.decode("utf-8", errors="replace")

    def devices(self) -> list[Device]:
        count = ct.c_uint()
        _check(self.clGetPlatformIDs(0, None, ct.byref(count)), "platform enumeration")
        platforms = (ct.c_void_p * count.value)()
        _check(self.clGetPlatformIDs(count, platforms, None), "platform enumeration")
        result = []
        for platform in platforms:
            number = ct.c_uint()
            code = self.clGetDeviceIDs(platform, 4, 0, None, ct.byref(number))  # GPU only
            if code == -1:  # CL_DEVICE_NOT_FOUND
                continue
            _check(code, "GPU enumeration")
            handles = (ct.c_void_p * number.value)()
            _check(self.clGetDeviceIDs(platform, 4, number, handles, None), "GPU enumeration")
            for handle in handles:
                fp64 = ct.c_ulonglong()
                status = self.clGetDeviceInfo(handle, 0x1032, ct.sizeof(fp64), ct.byref(fp64), None)
                result.append(Device(platform, handle, self.text(handle, 0x102B),
                    self.text(handle, 0x102C), self.text(handle, 0x102D),
                    self.text(handle, 0x102F), status == 0 and fp64.value != 0))
        return result


def gpu_devices() -> list[Device]:
    """Read installed GPU capabilities without creating a context or kernel."""
    return _API().devices()


class OpenCLKernel:
    """Explicit FP64 GPU context. Use as a context manager to release all resources."""

    def __init__(self, source: str, entry: str, *, device_name: str):
        if not isinstance(device_name, str) or not device_name.strip():
            raise ValueError("An explicit GPU device name is required")
        started = perf_counter()
        self.api = _API()
        self.context = self.queue = self.program = self.kernel = None
        choices = [d for d in self.api.devices() if device_name.casefold() in d.name.casefold()]
        if len(choices) != 1:
            raise OpenCLError(f"GPU selection {device_name!r} matched {len(choices)} devices")
        self.device = choices[0]
        if not self.device.fp64:
            raise OpenCLError("Selected GPU lacks required double-precision arithmetic")
        self.source_sha256 = sha256(source.encode()).hexdigest()
        error = ct.c_int()
        handle = ct.c_void_p(self.device.handle)
        try:
            self.context = self.api.clCreateContext(None, 1, ct.byref(handle), None, None, ct.byref(error))
            _check(error.value, "create context")
            self.queue = self.api.clCreateCommandQueue(self.context, handle, 2, ct.byref(error))  # profiling
            _check(error.value, "create profiling queue")
            sources = (ct.c_char_p * 1)(source.encode())
            self.program = self.api.clCreateProgramWithSource(self.context, 1, sources, None, ct.byref(error))
            _check(error.value, "create program")
            code = self.api.clBuildProgram(self.program, 1, ct.byref(handle), b"-cl-std=CL1.2", None, None)
            if code:
                length = ct.c_size_t()
                self.api.clGetProgramBuildInfo(self.program, handle, 0x1183, 0, None, ct.byref(length))
                log = ct.create_string_buffer(length.value)
                self.api.clGetProgramBuildInfo(self.program, handle, 0x1183, length, log, None)
                raise OpenCLError(f"GPU program build failed ({code}): {log.value.decode(errors='replace')}")
            self.kernel = self.api.clCreateKernel(self.program, entry.encode(), ct.byref(error))
            _check(error.value, "create kernel")
        except BaseException:
            self.close()
            raise
        self.initialization_s = perf_counter() - started

    def close(self) -> None:
        for attribute, kind in (("kernel", "Kernel"), ("program", "Program"),
                                ("queue", "CommandQueue"), ("context", "Context")):
            handle = getattr(self, attribute, None)
            if handle:
                getattr(self.api, "clRelease" + kind)(handle)
                setattr(self, attribute, None)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def execute(self, inputs: np.ndarray, output_columns: int) -> tuple[np.ndarray, dict]:
        """Synchronous bounded batch; reports allocation, transfer and device times."""
        if not self.kernel:
            raise OpenCLError("GPU context is closed")
        if inputs.dtype != np.float64 or inputs.ndim != 2 or not inputs.flags.c_contiguous:
            raise ValueError("GPU input must be a contiguous two-dimensional float64 array")
        if not 1 <= len(inputs) <= 65536 or not 1 <= output_columns <= 256:
            raise ValueError("GPU batch exceeds bounded shape")
        if not np.isfinite(inputs).all():
            raise ValueError("GPU input must be finite")
        started = perf_counter()
        outputs = np.empty((len(inputs), output_columns), dtype=np.float64)
        source = destination = event = None
        error = ct.c_int()
        try:
            source = self.api.clCreateBuffer(self.context, 4 | 32, inputs.nbytes,
                inputs.ctypes.data_as(ct.c_void_p), ct.byref(error))  # READ_ONLY | COPY_HOST_PTR
            _check(error.value, "create and upload input")
            destination = self.api.clCreateBuffer(self.context, 2, outputs.nbytes, None, ct.byref(error))
            _check(error.value, "allocate output")
            for index, buffer in enumerate((source, destination)):
                value = ct.c_void_p(buffer)
                _check(self.api.clSetKernelArg(self.kernel, index, ct.sizeof(value), ct.byref(value)), "set buffer argument")
            count = ct.c_uint(len(inputs))
            _check(self.api.clSetKernelArg(self.kernel, 2, ct.sizeof(count), ct.byref(count)), "set count")
            size = ct.c_size_t(len(inputs))
            event = ct.c_void_p()
            _check(self.api.clEnqueueNDRangeKernel(self.queue, self.kernel, 1, None,
                ct.byref(size), None, 0, None, ct.byref(event)), "launch GPU kernel")
            _check(self.api.clEnqueueReadBuffer(self.queue, destination, 1, 0, outputs.nbytes,
                outputs.ctypes.data_as(ct.c_void_p), 0, None, None), "read GPU output")
            beginning, ending = ct.c_ulonglong(), ct.c_ulonglong()
            _check(self.api.clGetEventProfilingInfo(event, 0x1282, 8, ct.byref(beginning), None), "profile start")
            _check(self.api.clGetEventProfilingInfo(event, 0x1283, 8, ct.byref(ending), None), "profile end")
        finally:
            if self.queue:
                self.api.clFinish(self.queue)
            if event and event.value:
                self.api.clReleaseEvent(event)
            for buffer in (destination, source):
                if buffer:
                    self.api.clReleaseMemObject(buffer)
        if not np.isfinite(outputs).all():
            raise OpenCLError("GPU produced nonfinite physics; result rejected")
        return outputs, {"allocation_transfer_kernel_read_release_s": perf_counter() - started,
                         "device_kernel_s": (ending.value - beginning.value) * 1e-9,
                         "backend": "OpenCL GPU FP64", "device": self.device.name,
                         "driver": self.device.driver, "kernel_sha256": self.source_sha256,
                         "cpu_fallback": False, "rows": len(inputs)}
