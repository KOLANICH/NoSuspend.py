#!/usr/bin/env python3
import os, sys
import unittest
import itertools, re
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from collections import OrderedDict, defaultdict
dict=OrderedDict

import subprocess

from NoSuspend import *

if sys.platform == "win32":
	stringsStatesMapping={
		enm.name.replace("_REQUIRED", ""):enm for enm in EXECUTION_STATE if enm.name.endswith("_REQUIRED")
	}
	
	powerctlReqRx=re.compile("("+"|".join(stringsStatesMapping.keys())+"):\\r?\\n(.+)")
	powerctlReqRx2=re.compile("^\\[PROCESS\\] (.+)$")
	
	diskPrefixRx=re.compile("^\\\\Device\\\\HarddiskVolume(\\d+)\\\\(.+)")
	import win32api
	numbersDriveLettersMapping = {k:v for k,v in enumerate(win32api.GetLogicalDriveStrings().split('\000')[:-1])}
	
	def driveNumberPath2LetterPath(drivePath):
		m=diskPrefixRx.match(drivePath).groups()
		return os.path.normpath(numbersDriveLettersMapping[int(m[0])]+m[1])
	
	cmd="powercfg -REQUESTS"
	
	def getProcessesInStates():
		with subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE) as proc:
			proc.wait()
			res=proc.stdout.read()
		processesInStates=defaultdict(lambda: EXECUTION_STATE(0))
		for m in powerctlReqRx.findall(res):
			mm=powerctlReqRx2.match(m[1])
			state=stringsStatesMapping[m[0]]
			if mm:
				procPath=driveNumberPath2LetterPath(mm.group(1))
				processesInStates[procPath]|=state
		return processesInStates
	
	interpPath=os.path.normpath(sys.executable)
	
	class TestsWin(unittest.TestCase):
		def testMain(self):
			for state in (stringsStatesMapping.values()):
				with NoSuspend(state):
					states=getProcessesInStates()
				self.assertEqual(state, states[interpPath])

if __name__ == '__main__':
	unittest.main()
