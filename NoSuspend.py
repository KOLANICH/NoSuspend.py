__all__ = ["SuspendInhibitionState", "NoSuspend"]

__author__ = "KOLANICH"
__license__ = "Unlicense"
__copyright__ = r"""
This is free and unencumbered software released into the public domain.

Anyone is free to copy, modify, publish, use, compile, sell, or
distribute this software, either in source code form or as a compiled
binary, for any purpose, commercial or non-commercial, and by any
means.

In jurisdictions that recognize copyright laws, the author or authors
of this software dedicate any and all copyright interest in the
software to the public domain. We make this dedication for the benefit
of the public at large and to the detriment of our heirs and
successors. We intend this dedication to be an overt act of
relinquishment in perpetuity of all present and future rights to this
software under copyright law.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.

For more information, please refer to <https://unlicense.org/>
"""

import typing
import sys
import warnings
from collections import defaultdict
from enum import IntFlag
from enum import _decompose as _enumDecompose  # if you use an older python, which library, you can upgrade this library from the newest one, it worked for me when I have used the lib from 3.6.1 on 3.4

class SuspendInhibitionState(IntFlag):
	"""Made compatible to the one used by Microsoft"""

	none = 0
	suspend = 1
	display = 2

class NoSuspend:
	"""Use it as context manager to set state"""

	__slots__ = ("flag", "inherit")

	STATE_ENUM = SuspendInhibitionState
	def __init__(self, suspend: bool = True, display: bool = False, inherit: bool = True, **kwargs):
		self.flag = self.__class__.STATE_ENUM(
			suspend * self.__class__.STATE_ENUM.suspend |
			display * self.__class__.STATE_ENUM.display
		)
		for k, v in kwargs.items():
			if hasattr(self.__class__.STATE_ENUM, k) and isinstance(v, bool):
				self.flag |= getattr(self.__class__.STATE_ENUM, k) * v
		self.inherit = inherit
	@staticmethod
	def getCurrentState():
		raise NotImplementedError()
	def __enter__(self):
		raise NotImplementedError()
	def __exit__(self, exc_type, exc_value, traceback):
		raise NotImplementedError()

class NoSuspendDummy(NoSuspend):
	"""A dummy class doing nothing. Can be used for OSes without suspension on idle."""

	__slots__ = ()

	def __init__(self, *args, **kwargs):
		pass
	@staticmethod
	def getCurrentState():
		return SuspendInhibitionState.none
	@staticmethod
	def setThreadExecutionState(es: (SuspendInhibitionState, int)):
		return SuspendInhibitionState.none
	def __enter__(self):
		return SuspendInhibitionState.none
	def __exit__(self, exc_type, exc_value, traceback):
		pass

class NoSuspendNotAvailable(NoSuspendDummy):
	"""Used when the library cannot prevent suspension in the the environment. If prevention of suspension is mission critical, you should check if issubclass(NoSuspend, NoSuspendNotAvailable)"""

	__slots__ = ()

class NoSuspendNotImplemented(NoSuspendNotAvailable):
	"""Used when the library cannot prevent suspension in the the environment because it is not implemented for that environment. If prevention of suspension is mission critical, you should check if issubclass(NoSuspend, NoSuspendNotAvailable)"""

	__slots__ = ()

	def __enter__(self):
		warnings.warn("Suspension prevention is not implemented in this lib for this environment. Help is welcome.")
		return super().__enter__()

class NoSuspendDependenciesAreMissing(NoSuspendNotAvailable):
	"""Used when the library cannot prevent suspension in the the environment because the env has dependencies missing. If prevention of suspension is mission critical, you should check if NoSuspend is issubclass(NoSuspend, NoSuspendNotAvailable)"""

	__slots__ = ()

	def __enter__(self):
		warnings.warn("Suspension prevention is not implemented in this lib for this environment. Help is welcome.")
		return super().__enter__()


try:
	if sys.platform == "win32":
		import ctypes

		if sys.getwindowsversion().major >= 6:

			__all__.append("EXECUTION_STATE")
			class EXECUTION_STATE(IntFlag):
				"""The info is taken from https://docs.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate"""

				hidden = AWAYMODE_REQUIRED = 0x00000040
				CONTINUOUS = 0x80000000
				display = DISPLAY_REQUIRED = 0x00000002
				suspend = SYSTEM_REQUIRED = 0x00000001
				USER_PRESENT = 0x00000004
			class NoSuspendWinVistaPlus(NoSuspend):
				"""Use it as context manager to set state"""

				__slots__ = ("prev", "current")

				STATE_ENUM = EXECUTION_STATE
				def __init__(self, suspend: bool = True, display: bool = False, AWAYMODE_REQUIRED: bool = False, inherit: bool = True, **kwargs):
					super().__init__(suspend, display, inherit, AWAYMODE_REQUIRED=AWAYMODE_REQUIRED, **kwargs)
					self.flag |= self.__class__.STATE_ENUM.CONTINUOUS
					self.prev = None
					self.current = None

				@staticmethod
				def getCurrentState():
					return __class__.STATE_ENUM(ctypes.windll.kernel32.SetThreadExecutionState(0))

				@staticmethod
				def setThreadExecutionState(es: (EXECUTION_STATE, int)):
					return __class__.STATE_ENUM(ctypes.windll.kernel32.SetThreadExecutionState(int(es)))

				def __enter__(self):
					self.prev = __class__.getCurrentState()
					self.current = self.flag | (self.prev if self.inherit else 0)
					__class__.setThreadExecutionState(self.current)
					return self.current

				def __exit__(self, exc_type, exc_value, traceback):
					self.current = self.prev
					__class__.setThreadExecutionState(self.current)
					self.prev = None

			NoSuspend = NoSuspendWinVistaPlus
		else:
			from win32console import GetConsoleWindow

			WndProcFn = ctypes.WINFUNCTYPE(c_int, c_long, c_int, c_int, c_int)

			WM_POWERBROADCAST = 0x218
			BROADCAST_QUERY_DENY = 0x424d5144

			class PowerChangingState(IntEnum):
				"""The info is taken from https://docs.microsoft.com/en-us/windows/win32/power/wm-powerbroadcast?redirectedfrom=MSDN"""

				powerStatusChange = PBT_APMPOWERSTATUSCHANGE = 0xa
				resumeAutomatic = PBT_APMRESUMEAUTOMATIC = 0x12
				resumeSuspend = PBT_APMRESUMESUSPEND = 0x7
				suspend = PBT_APMSUSPEND = 0x4
				powerSettingChange = PBT_POWERSETTINGCHANGE = 0x8013

			hwnd = GetConsoleWindow()
			thread = None

			locks = set()

			def wndProc(hWnd, message, wParam, lParam):
				if message == WM_POWERBROADCAST:
					if locks and lParam & 0x1 and PowerChangingState(wParam) == PowerChangingState.suspend:
						return BROADCAST_QUERY_DENY
				return True

			def threadFunc():
				ctypes.windll.user32.SetWindowLongW(hwnd, GWL_WNDPROC, WndProcFn(wndProc))

			def startDaemonThreadIfNeeded():
				global thread
				if not thread:
					thread = threading.Thread(target=threadFunc, daemon=True)

			class NoSuspendWinXP(NoSuspend):
				__slots__ = ("thread", "hwnd")
				"""Use it as context manager to set state"""

				def __init__(self):
					super().__init__()

				def __enter__(self):
					locks.add(id(self))
					startDaemonThreadIfNeeded()
					return self.current

				def __exit__(self, exc_type, exc_value, traceback):
					locks.remove(id(self))

			NoSuspend = NoSuspendWinXP
	elif sys.platform == "linux":
		# have not extensively tested (yet)
		class DBusInhibitor:
			"""This class is used to create and release an inhibitions via a certain D-Bus  interface. The way it calls the methods is the most widespread and is compatible with freedesktop"""

			"""Inhibit method name of a specific D-Bus interface"""
			INHIBIT_METHOD_NAME = "Inhibit"

			"""Inhibition release method name of a specific D-Bus interface"""
			UNINHIBIT_METHOD_NAME = "UnInhibit"
			def __init__(self, additionalMethods: typing.Tuple[str] = tuple()):
				self.cookies = set()  # the cookies created by this inhibition. Used to release inhibitions
				self.additionalMethods = additionalMethods  # additional D-Bus methods
				self.ifc = {}

			def inhibit(self, appName: str, reason: str):
				"""Used to add an inhibition, returns the cookie which can be used to release it"""
				ck = self._inhibitCall(appName, reason)
				self.cookies.add(ck)
				return ck

			def uninhibit(self, cookie):
				"""Releases the inhibition given its cookie"""
				rv = self._uninhibitCall(cookie)
				self.cookies.remove(cookie)
				return rv

			def __del__(self):
				for ck in self.cookies:
					try:
						self._uninhibitCall(ck)
					except BaseException:
						pass


			def _inhibitCall(self, appName: str, reason: str):
				"""Redefine this method if you need to call the method creating an inhibition of a D-Bus interface another way"""
				return self.ifc[self.__class__.INHIBIT_METHOD_NAME](appName, reason)

			def _uninhibitCall(self, cookie: str):
				"""Redefine this method if you need to call the method releasing the inhibition of a D-Bus interface another way"""
				return self.ifc[self.__class__.UNINHIBIT_METHOD_NAME](cookie)

		class KDEInhibitor(DBusInhibitor):
			INHIBIT_METHOD_NAME = "AddInhibition"
			UNINHIBIT_METHOD_NAME = "ReleaseInhibition"

			def _inhibitCall(self, appName: str, reason: str):
				return ifc[self.__class__.INHIBIT_METHOD_NAME](1, appName, reason)

		class SystemDInhibitor(DBusInhibitor):
			INHIBIT_METHOD_NAME = "Inhibit"
			UNINHIBIT_METHOD_NAME = None

			class SystemD_INHIBITION(IntFlag):
				sleep = 1  # suspend and hibernation
				shutdown = 1 << 63  # power-off and reboot
				idle = 1 << 62  # system going into idle mode
				power_key = 1 << 61  # system power hardware key
				suspend_key = 1 << 60  # suspend key.
				hibernate_key = 1 << 59  # hardware hibernate key.
				lid_switch = 1 << 58  # hardware lid switch

			def _inhibitCall(self, appName: str, reason: str):
				what = SystemD_INHIBITION.sleep.name
				mode = "block"
				res = ifc[self.__class__.INHIBIT_METHOD_NAME](what, appName, reason, mode)
				return res.take()

			def _uninhibitCall(self, cookie: str):
				import os

				return os.close(cookie)

		class GnomeInhibitor(DBusInhibitor):
			class DBUS_INHIBITION(IntFlag):
				LOGGING_OUT = 1
				USER_SWITCHING = 2
				INHIBIT_SUSPEND = 4
				IDLE_SESSION = 8

			def _inhibitCall(self, appName: str, reason: str):
				return self.ifc[self.__class__.INHIBIT_METHOD_NAME](appName, GnomeSessionInhibitor.TOPLEVEL_XID, reason, self.__class__.DBUS_INHIBITION.INHIBIT_SUSPEND)

		# the DE names are just for convenience
		dbusPowerRelatedInterfaces = {
			"suspend": {
				"freedesktop": {
					# applications' names \/
					("org.freedesktop.PowerManagement", "org.kde.powerdevil", "org.xfce.PowerManager"): {
						# proxy path \/
						"/org/freedesktop/PowerManagement/Inhibit": DBusInhibitor(
							(
								# additional methods \/
								"HasInhibit",
								"GetInhibitors",
								"HasInhibitChanged",
							)
						),
					},
					"org.freedesktop.login1.Manager": {
						"/org/freedesktop/login1": SystemDInhibitor(( #https://www.freedesktop.org/wiki/Software/systemd/inhibit/
							"ListInhibitors",
							"BlockInhibited",
							"DelayInhibited"
						)),
					},
				},
				# TODO: org.lxqt.lxqt-powermanagement
				"kde": {
					"org.kde.kded": {
						"/org/kde/Solid/PowerManagement/PolicyAgent": KDEInhibitor()
					}
				},
				"mate": {
					"org.mate.SessionManager": {
						"/org/mate/SessionManager": GnomeInhibitor()
					},
				},
				"gnome": {
					"org.gnome.SessionManager": {
						"/org/gnome/SessionManager": GnomeInhibitor()
					},
					"org.gnome.PowerManager": {
						"/org/gnome/PowerManager": GnomeInhibitor()
					}
				},
			},
			"screensaver": {
				"freedesktop": {
					"org.freedesktop.ScreenSaver": {
						"/org/freedesktop/ScreenSaver": DBusInhibitor(("Lock", "SimulateUserActivity")),
					}
				},
				"gnome": {
					"org.gnome.ScreenSaver": {
						"/org/gnome/ScreenSaver": DBusInhibitor(("Lock", "Cycle", "SimulateUserActivity", "Throttle", "UnThrottle", "SetActive", "GetActive", "GetActiveTime", "GetSessionIdle", "GetSessionIdleTime"))
					}
				},
			},
		}

		from dbus import SessionBus, SystemBus
		def obtainDbusInterfaces(cfg):
			res = {}
			buses = [busCtor() for busCtor in (SystemBus, SessionBus)]

			for DEName, appNames in cfg.items():
				deRes = {}
				for appAliases, proxyPaths in appNames.items():
					for proxyPath, inhibitor in proxyPaths.items():
						if isinstance(appAliases, str):
							appAliases = [appAliases]
						proxy = None
						for appName in appAliases:
							for bus in buses:
								try:
									proxy = bus.get_object(appName, proxyPath)
									#print("Found proxy", DEName, appName, proxyPath)
									break
								except Exception as ex:
									#print(ex)
									continue
							if proxy:
								break
						if proxy:
							proxyName = proxyPath.split("/")[-1]
							methodsNames = [inhibitor.INHIBIT_METHOD_NAME, inhibitor.UNINHIBIT_METHOD_NAME]
							methodsNames.extend(inhibitor.additionalMethods)
							for methodName in methodsNames:
								#if ifName in proxy:
								try:
									inhibitor.ifc[methodName] = getattr(proxy, methodName)
									#print("Found", DEName, proxyName, methodName)
								except Exception as ex:
									#print(ex)
									continue
							deRes[proxyName] = inhibitor
				if deRes:
					res[DEName] = deRes
			return res

		powerRelatedIfcs = {k: obtainDbusInterfaces(group) for k, group in dbusPowerRelatedInterfaces.items()}
		class NoSuspendLinux(NoSuspend):
			def __init__(self, suspend: bool = True, display: bool = False, inherit: bool = True, appName: str = "Python NoSuspend", reason: str = "NoSuspend was called", **kwargs):
				super().__init__(suspend, display, inherit, appName="Python NoSuspend", reason=reason, **kwargs)

				if not inherit:
					warnings.warn("Inherit is set to false, which means completely redefining the state, including reverting inhibitions. It is hardly possible, because it requires determinig the inhibitions belonging to the current thread, releasing them and then on restore restoring them. We can't do the first part. At least for now. I don't quit need that, so help is welcome.")

				self.cookies = defaultdict(list)
				self.appName = appName
				self.reason = reason
			def __enter__(self):
				for gr in _enumDecompose(type(self.flag), self.flag)[0]:
					grNm = gr.name
					if grNm in powerRelatedIfcs:
						for deName, de in powerRelatedIfcs[grNm].items():
							for inhibiterName, inhibiter in de.items():
								ck = inhibiter.inhibit(self.appName, self.reason)
								self.cookies[grNm].append((inhibiter, ck))
					else:
						warnings.warn("The suspension for `" + grNm + "` is not set (either not implemented, or not available in the environment), ignoring")

				return self.flag

			def __exit__(self, exc_type, exc_value, traceback):
				for group in self.cookies.values():
					for cancelCall in group:
						inhibiter = cancelCall[0]
						cookie = cancelCall[1:]
						inhibiter.uninhibit(*cookie)
				self.cookies = []
			def __del__(self):
				for ck in self.cookies:
					try:
						self.uninhibit(ck)
					except BaseException:
						pass

		NoSuspend = NoSuspendLinux
	else:
		NoSuspend = NoSuspendNotImplemented
except ImportError:
	NoSuspend = NoSuspendDependenciesAreMissing

def main():
	if len(sys.argv) < 2:
		print("python -m NoSuspend <command>")
	else:
		commandLine = " ".join(sys.argv[1:])
		from subprocess import Popen

		with NoSuspend(appName="NoSuspend CLI", reason=commandLine):
			with Popen(commandLine, shell=True) as proc:
				proc.wait()
				sys.exit(proc.returncode)


if __name__ == "__main__":
	main()
