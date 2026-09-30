"""Win32 handle-based reads for regular project files (ADR 0004, read-only)."""
from __future__ import annotations

import os
import stat
from functools import lru_cache
from pathlib import Path
from typing import Tuple

REPARSE_NAME_SURROGATE = 0x20000000

_FILE_LIST_DIRECTORY = 0x0001
_FILE_TRAVERSE = 0x0020
_FILE_READ_ATTRIBUTES = 0x0080
_SYNCHRONIZE = 0x00100000
_GENERIC_READ = 0x80000000
_FILE_SHARE_READ = 0x1
_FILE_SHARE_WRITE = 0x2
_OPEN_EXISTING = 3
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_FILE_OPEN = 1
_FILE_DIRECTORY_FILE = 0x00000001
_FILE_SYNCHRONOUS_IO_NONALERT = 0x00000020
_FILE_NON_DIRECTORY_FILE = 0x00000040
_OBJ_CASE_INSENSITIVE = 0x00000040
_DIRECTORY_ACCESS = _FILE_LIST_DIRECTORY | _FILE_TRAVERSE | _FILE_READ_ATTRIBUTES | _SYNCHRONIZE
_PIN_SHARE = _FILE_SHARE_READ | _FILE_SHARE_WRITE


def is_link_like(path: Path, status: os.stat_result) -> bool:
    if stat.S_ISLNK(status.st_mode):
        return True
    if getattr(status, "st_reparse_tag", 0) & REPARSE_NAME_SURROGATE:
        return True
    return False


class _WindowsHandles:
    def __init__(self) -> None:
        import ctypes
        import msvcrt
        from ctypes import wintypes

        class UnicodeString(ctypes.Structure):
            _fields_ = [
                ("Length", wintypes.USHORT),
                ("MaximumLength", wintypes.USHORT),
                ("Buffer", wintypes.LPWSTR),
            ]

        class ObjectAttributes(ctypes.Structure):
            _fields_ = [
                ("Length", wintypes.ULONG),
                ("RootDirectory", wintypes.HANDLE),
                ("ObjectName", ctypes.POINTER(UnicodeString)),
                ("Attributes", wintypes.ULONG),
                ("SecurityDescriptor", ctypes.c_void_p),
                ("SecurityQualityOfService", ctypes.c_void_p),
            ]

        class IoStatusBlock(ctypes.Structure):
            _fields_ = [("Status", ctypes.c_void_p), ("Information", ctypes.c_size_t)]

        self.ctypes = ctypes
        self.wintypes = wintypes
        self.msvcrt = msvcrt
        self.UnicodeString = UnicodeString
        self.ObjectAttributes = ObjectAttributes
        self.IoStatusBlock = IoStatusBlock
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.ntdll = ctypes.WinDLL("ntdll")
        self.kernel32.CreateFileW.restype = wintypes.HANDLE
        self.ntdll.NtCreateFile.restype = ctypes.c_long
        self.ntdll.RtlNtStatusToDosError.restype = wintypes.ULONG
        self.ntdll.RtlNtStatusToDosError.argtypes = (ctypes.c_long,)

    def adopt(self, handle: int) -> int:
        try:
            descriptor = self.msvcrt.open_osfhandle(handle, 0)
        except OSError:
            self.kernel32.CloseHandle(self.wintypes.HANDLE(handle))
            raise
        self.msvcrt.setmode(descriptor, os.O_BINARY)
        return descriptor

    def open_root(self, path: Path) -> int:
        handle = self.kernel32.CreateFileW(
            str(path),
            _DIRECTORY_ACCESS,
            _PIN_SHARE,
            None,
            _OPEN_EXISTING,
            _FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OPEN_REPARSE_POINT,
            None,
        )
        if handle is None or handle == self.wintypes.HANDLE(-1).value:
            raise self.ctypes.WinError(self.ctypes.get_last_error())
        return self.adopt(handle)

    def open_relative(self, parent_fd: int, name: str, *, file: bool) -> int:
        ctypes = self.ctypes
        access = _GENERIC_READ if file else _DIRECTORY_ACCESS
        options = _FILE_NON_DIRECTORY_FILE if file else _FILE_DIRECTORY_FILE
        buffer = ctypes.create_unicode_buffer(name)
        length = len(name) * ctypes.sizeof(ctypes.c_wchar)
        object_name = self.UnicodeString(
            length,
            length + ctypes.sizeof(ctypes.c_wchar),
            ctypes.cast(buffer, self.wintypes.LPWSTR),
        )
        attributes = self.ObjectAttributes(
            ctypes.sizeof(self.ObjectAttributes),
            self.msvcrt.get_osfhandle(parent_fd),
            ctypes.pointer(object_name),
            _OBJ_CASE_INSENSITIVE,
            None,
            None,
        )
        handle = self.wintypes.HANDLE()
        status = self.ntdll.NtCreateFile(
            ctypes.byref(handle),
            access | _SYNCHRONIZE,
            ctypes.byref(attributes),
            ctypes.byref(self.IoStatusBlock()),
            None,
            0,
            _PIN_SHARE,
            _FILE_OPEN,
            options | _FILE_SYNCHRONOUS_IO_NONALERT | _FILE_FLAG_OPEN_REPARSE_POINT,
            None,
            0,
        )
        if status < 0:
            raise ctypes.WinError(self.ntdll.RtlNtStatusToDosError(status))
        return self.adopt(handle.value)


@lru_cache(maxsize=1)
def _handles() -> _WindowsHandles:
    return _WindowsHandles()


def read_regular_file(root: Path, relative: str) -> Tuple[bytes, float]:
    """Read a regular file under root without following reparse points in parents."""
    win = _handles()
    parts = Path(relative).parts
    descriptors: list[int] = []
    try:
        descriptors.append(win.open_root(root))
        for index, part in enumerate(parts):
            final = index == len(parts) - 1
            current = root.joinpath(*parts[: index + 1])
            descriptor = win.open_relative(descriptors[-1], part, file=final)
            descriptors.append(descriptor)
            actual = os.fstat(descriptor)
            if is_link_like(current, actual):
                raise OSError("link-like path is not allowed")
            if final:
                if not stat.S_ISREG(actual.st_mode) or actual.st_nlink != 1:
                    raise OSError("only regular files without hard links can be viewed")
                with os.fdopen(descriptor, "rb") as stream:
                    descriptors.pop()
                    return stream.read(), actual.st_mtime
            if not stat.S_ISDIR(actual.st_mode):
                raise OSError("path component is not a directory")
        raise OSError("empty relative path")
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
