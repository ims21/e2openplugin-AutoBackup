from . import _
import time
import os
import enigma
from Plugins.Plugin import PluginDescriptor
from Components.config import config, configfile, ConfigEnableDisable, ConfigSubsection, ConfigClock, ConfigOnOff, ConfigSelection, ConfigText

#Set default configuration
config.plugins.autobackup = ConfigSubsection()
config.plugins.autobackup.enabled = ConfigEnableDisable(default = False)
config.plugins.autobackup.frequency = ConfigSelection(default="daily", choices=[
	("1", _("Every hour")),
	("2", _("Every 2 hours")),
	("4", _("Every 4 hours")),
	("6", _("Every 6 hours")),
	("12", _("Every 12 hours")),
	("daily", _("Daily")),
	("monday", _("Every Monday")),
	("tuesday", _("Every Tuesday")),
	("wednesday", _("Every Wednesday")),
	("thursday", _("Every Thursday")),
	("friday", _("Every Friday")),
	("saturday", _("Every Saturday")),
	("sunday", _("Every Sunday")),
])
config.plugins.autobackup.wakeup = ConfigClock(default = ((3*60) + 0) * 60)
config.plugins.autobackup.lastbackup = ConfigText(default="0")
config.plugins.autobackup.autoinstall = ConfigOnOff(default = True)
config.plugins.autobackup.where = ConfigText(default = "/media/hdd")
config.plugins.autobackup.epgcache = ConfigOnOff(default = False)
config.plugins.autobackup.keeparchives = ConfigSelection(default="all", choices=[
	("1", "1"),
	("2", "2"),
	("5", "5"),
	("7", "7"),
	("10", "10"),
	("20", "20"),
	("50", "50"),
	("all", _("All")),
])
# for ENABLE_EXPERIMENTAL_FEATURES
config.plugins.autobackup.method = ConfigOnOff(default = True)
config.plugins.autobackup.measureTime = ConfigOnOff(default=False)


# Global variables
autoStartTimer = None
container = None

##################################
# Configuration GUI

BACKUP_SCRIPT = "/usr/lib/enigma2/python/Plugins/Extensions/AutoBackup/settings-backup.sh"


def backupCommand(where=None, fullArchive=False):
	cmd = BACKUP_SCRIPT
	if config.plugins.autobackup.autoinstall.value or fullArchive:
		cmd += " -a"
	cmd += " " + (where or config.plugins.autobackup.where.value)
	return cmd

def setLastBackupTime():
	config.plugins.autobackup.lastbackup.value = str(int(time.time()))
	config.plugins.autobackup.lastbackup.save()
	configfile.save()


def runBackup():
	global container
	if container is not None:
		print("[AutoBackup] backup already running")
		return False

	destination = config.plugins.autobackup.where.value
	if destination:
		try:
			archivePending = [True]
			archiveCreator = [None]

			def appClosed(retval):
				global container
				if not retval and archivePending[0]:
					archivePending[0] = False
					from .ui import ArchiveCreator
					archiveCreator[0] = ArchiveCreator(destination)
					backupDir = os.path.join(destination, "backup")
					archiveCreator[0].createInfo(backupDir)
					if container.execute(archiveCreator[0].buildArchiveCommand(backupDir, removeInfo=True)):
						print("[AutoBackup] failed to execute archive")
						container = None
					return
				if not retval:
					if archiveCreator[0] is not None:
						archiveCreator[0].removeOldArchives()
					setLastBackupTime()
				print("[AutoBackup] complete, result:", retval)
				container = None

			def dataAvail(data):
				if isinstance(data, bytes):
					data = data.decode("utf-8", errors="replace")
				print("[AutoBackup]", data.rstrip())

			print("[AutoBackup] start automatic backup")
			cmd = backupCommand(fullArchive=True)
			container = enigma.eConsoleAppContainer()
			container.appClosed.append(appClosed)
			container.dataAvail.append(dataAvail)
			if container.execute(cmd):
				raise Exception("failed to execute: " + cmd)
			return True
		except Exception as e:
			print("[AutoBackup] FAIL:", e)
			container = None
	return False

def main(session, **kwargs):
	from . import ui
	session.openWithCallback(doneConfiguring, ui.Config)


def doneConfiguring(session, retval):
	"user has closed configuration, check new values...."
	global autoStartTimer
	if autoStartTimer is not None:
		autoStartTimer.update()


##################################
# Autostart section

class AutoStartTimer:
	STARTUP_DELAY = 120

	WEEKDAYS = (
		"monday",
		"tuesday",
		"wednesday",
		"thursday",
		"friday",
		"saturday",
		"sunday",
	)

	def __init__(self, session):
		self.session = session
		self.timer = enigma.eTimer()
		self.timer.callback.append(self.onTimer)
		self.wakeTime = -1
		self.startupCheck = config.plugins.autobackup.enabled.value
		if self.startupCheck:
			self.timer.startLongTimer(self.STARTUP_DELAY)

	def getScheduleTimes(self, now=None):
		if not config.plugins.autobackup.enabled.value:
			return -1, -1

		now = int(time.time()) if now is None else now
		localNow = time.localtime(now)
		clock = config.plugins.autobackup.wakeup.value
		frequency = config.plugins.autobackup.frequency.value

		def makeTime(dayOffset, hour):
			return int(time.mktime((
				localNow.tm_year,
				localNow.tm_mon,
				localNow.tm_mday + dayOffset,
				hour,
				clock[1],
				0,
				-1,
				-1,
				-1
			)))

		if frequency.isdigit():
			interval = int(frequency)
			hours = range(clock[0] % interval, 24, interval)
			candidates = [makeTime(dayOffset, hour) for dayOffset in (-1, 0, 1) for hour in hours]
		elif frequency == "daily":
			candidates = [makeTime(dayOffset, clock[0]) for dayOffset in (-1, 0, 1)]
		else:
			weekday = self.WEEKDAYS.index(frequency)
			candidates = [makeTime(dayOffset, clock[0]) for dayOffset in range(-7, 8)]
			candidates = [candidate for candidate in candidates if time.localtime(candidate).tm_wday == weekday]

		previous = [candidate for candidate in candidates if candidate <= now]
		following = [candidate for candidate in candidates if candidate > now]

		return (
			max(previous) if previous else -1,
			min(following) if following else -1
		)

	def checkMissedBackup(self):
		if not config.plugins.autobackup.enabled.value:
			return False

		previous = self.getScheduleTimes()[0]

		try:
			lastBackup = int(config.plugins.autobackup.lastbackup.value)
		except (TypeError, ValueError):
			lastBackup = 0

		if previous > lastBackup:
			print("[AutoBackup] no backup found since the last scheduled time")
			return runBackup()

		return False

	def update(self, atLeast=0):
		self.timer.stop()
		self.startupCheck = False
		now = int(time.time())
		unused, self.wakeTime = self.getScheduleTimes(now + atLeast)
		if self.wakeTime > 0:
			next = self.wakeTime - now
			# it could be that we do not have the correct system time yet,
			# limit the update interval to 1h, to make sure we try again soon
			if next > 3600:
				next = 3600
			# A non-positive value would stop the timer.
			if next <= 0:
				next = 60
			self.timer.startLongTimer(next)
		else:
			self.wakeTime = -1
		return self.wakeTime

	def onTimer(self):
		self.timer.stop()
		if self.startupCheck:
			self.startupCheck = False
			backupStarted = self.checkMissedBackup()
			self.update(60 if backupStarted else 0)
			return

		now = int(time.time())
		# If we're close enough, we're okay...
		atLeast = 0
		if self.wakeTime > 0 and abs(self.wakeTime - now) < 60:
			runBackup()
			atLeast = 60
		self.update(atLeast)


def autostart(reason, session=None, **kwargs):
	"called with reason=1 to during shutdown, with reason=0 at startup?"
	global autoStartTimer
	if reason == 0:
		if session is not None:
			if autoStartTimer is None:
				autoStartTimer = AutoStartTimer(session)


def checkmenu(menuid):
	return [(_("Auto backup"), main, "autobackup", 8)] if menuid == "setup" else []


def Plugins(**kwargs):
	description = _("Automatic settings backup")
	return [
		PluginDescriptor(
			name="AutoBackup",
			description=description,
			where=[PluginDescriptor.WHERE_AUTOSTART, PluginDescriptor.WHERE_SESSIONSTART],
			fnc=autostart
		),
		PluginDescriptor(
			name="Autobackup",
			description=description,
			where=PluginDescriptor.WHERE_MENU,
			needsRestart=False,
			fnc=checkmenu
		)
	]
