"""Process ownership checks. Never kill a process using a stored PID alone."""
import os
import signal
from pathlib import Path


def _windows_process(pid, expected=None, terminate=False):
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    handle = kernel.OpenProcess(0x1000 | 0x100000 | (1 if terminate else 0), False, int(pid))
    if not handle:
        if ctypes.get_last_error() == 5:
            raise PermissionError('Process ownership could not be verified')
        return None
    try:
        created, exited, system, user = (wintypes.FILETIME() for _ in range(4))
        if not kernel.GetProcessTimes(handle, *[ctypes.byref(item) for item in (created, exited, system, user)]):
            raise OSError('Could not verify process creation time')
        buffer = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(buffer))
        if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
            raise OSError('Could not verify process executable')
        identity = {'pid': int(pid), 'created': (created.dwHighDateTime << 32) | created.dwLowDateTime, 'executable': buffer.value}
        if expected is not None and identity != expected:
            raise ValueError('Process identity changed; refusing to terminate reused PID')
        if terminate:
            # The verified HANDLE pins the exact process across PID reuse.
            if not kernel.TerminateProcess(handle, 0):
                raise OSError('Could not stop owned process')
            kernel.WaitForSingleObject(handle, 5000)
        return identity
    finally:
        kernel.CloseHandle(handle)


def process_identity(pid):
    if os.name == 'nt':
        return _windows_process(pid)
    try:
        raw = Path(f'/proc/{int(pid)}/stat').read_text()
        return {'pid': int(pid), 'created': raw[raw.rfind(')') + 2:].split()[19],
                'executable': str(Path(f'/proc/{int(pid)}/exe').resolve(strict=True))}
    except FileNotFoundError:
        return None


def stop_owned_process(expected):
    if not expected or not isinstance(expected.get('pid'), int) or expected['pid'] <= 1:
        raise ValueError('Missing trustworthy process receipt')
    if os.name == 'nt':
        return _windows_process(expected['pid'], expected, terminate=True)
    # A pidfd pins the process on Linux too. Refuse unsupported platforms.
    fd = os.pidfd_open(expected['pid'])
    try:
        if process_identity(expected['pid']) != expected:
            raise ValueError('Process identity changed; refusing to stop')
        signal.pidfd_send_signal(fd, signal.SIGTERM)
    finally:
        os.close(fd)
