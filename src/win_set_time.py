# Reference to https://github.com/Delgan/win32-setctime
from ctypes import byref, get_last_error, wintypes, WinDLL, WinError

kernel32 = WinDLL("kernel32", use_last_error=True)

CreateFileW = kernel32.CreateFileW
SetFileTime = kernel32.SetFileTime
CloseHandle = kernel32.CloseHandle

CreateFileW.argtypes = (
    wintypes.LPWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPVOID,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
)
CreateFileW.restype = wintypes.HANDLE

SetFileTime.argtypes = (
    wintypes.HANDLE,
    wintypes.PFILETIME,
    wintypes.PFILETIME,
    wintypes.PFILETIME,
)
SetFileTime.restype = wintypes.BOOL

CloseHandle.argtypes = (wintypes.HANDLE,)
CloseHandle.restype = wintypes.BOOL
VOID_HANDLE = wintypes.HANDLE(-1).value


def from_timestamp(timestamp: float):
    timestamp = int(timestamp * 10000000) + 116444736000000000
    return byref(wintypes.FILETIME(timestamp, timestamp >> 32))


def set_times(filepath: str, create_timestamp: float, modify_timestamp: float, access_timestamp: float):
    handle = wintypes.HANDLE(CreateFileW(filepath, 256, 0, None, 3, 33554560, None))

    if handle.value == VOID_HANDLE:
        raise WinError(get_last_error())

    c_time = from_timestamp(create_timestamp)
    m_time = from_timestamp(modify_timestamp)
    a_time = from_timestamp(access_timestamp)

    if not wintypes.BOOL(SetFileTime(handle, c_time, a_time, m_time)):
        raise WinError(get_last_error())

    if not wintypes.BOOL(CloseHandle(handle)):
        raise WinError(get_last_error())
