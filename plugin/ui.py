from __future__ import absolute_import
from __future__ import print_function
##################################
##################################
# Configuration GUI
from . import _
from . import plugin
import os, tarfile
import enigma
import shutil
import re
from Components.config import config, configfile, getConfigListEntry, ConfigSelection, ConfigYesNo
from Screens.Screen import Screen
from Components.ConfigList import ConfigListScreen
from Components.About import about
from Components.ActionMap import ActionMap
from Components.Button import Button
from Components.Label import Label
from Components.MenuList import MenuList
from Components.ScrollLabel import ScrollLabel
from Components.Sources.StaticText import StaticText
from Screens.ChoiceBox import ChoiceBox
from Screens.MessageBox import MessageBox
from Tools.FuzzyDate import FuzzyTime
from Screens.Standby import getReasons
from Tools.BoundFunction import boundFunction
from time import mktime


def writeLog(text, mode="a"):
    try:
        with open("/tmp/autobackup.log", mode) as f:
            f.write(text)
    except Exception as ex:
        print("[AutoBackup] Failed to write log:", ex)


FRIENDLY = {
	"/media/hdd": _("Harddisk"),
	"/media/usb": _("USB"),
	"/media/cf": _("CF"),
	"/media/mmc1": _("SD"),
	}


ARCHIVE_FILTERS_RESTORE = {
	"mac": True,
	"hostname": True,
	"image": True,
	"slot": True,
	"alphabetical": False,
}
ARCHIVE_FILTERS_MANUAL = {
	"mac": True,
	"hostname": False,
	"image": False,
	"slot": False,
	"alphabetical": False,
}
ARCHIVE_FILTERS_RESTORE_FALLBACK = {
	"mac": True,
	"hostname": False,
	"image": False,
	"slot": False,
	"alphabetical": False,
}

def getLocationChoices():
	result = []
	for line in open('/proc/mounts', 'r'):
		items = line.split()
		if items[1].startswith('/media'):
			desc = FRIENDLY.get(items[1], items[1])
			if items[0].startswith('//'):
				desc += ' (*)'
			result.append((items[1], desc))
		elif items[1] == '/' and items[0].startswith('/dev/'):
			# Box that has a rootfs mounted from a device
			desc = _("root")
			# On a 7025, that'd be the harddisk or CF
			if items[0].startswith('/dev/hdc'):
				desc = _("CF")
			elif items[0].startswith('/dev/hda'):
				desc = _("Harddisk")
			result.append((items[1], desc))
	return result


def getStandardFiles():
	return [os.path.normpath(n.strip()) for n in open('/usr/lib/enigma2/python/Plugins/Extensions/AutoBackup/backup.cfg', 'r')]


def getSelectedFiles():
	result = getStandardFiles()
	try:
		result += [os.path.normpath(n.strip()) for n in open('/etc/backup.cfg', 'r')]
	except:
		# ignore missing user cfg file
		pass
	return result


def saveSelectedFiles(files):
	standard = getStandardFiles()
	try:
		f = open('/etc/backup.cfg', 'w')
		for fn in files:
			fn = os.path.normpath(fn)
			if fn not in standard:
				f.write(fn + '\n')
		f.close()
	except Exception as ex:
		print("[AutoBackup] Failed to write /etc/backup.cfg", ex)


def getMacAddress():
	try:
		with open("/sys/class/net/eth0/address", "r") as f:
			return f.read().strip().replace(":", "").lower()
	except:
		return "nomac"


def getHostName():
	try:
		with open("/etc/hostname", "r") as f:
			return f.read().strip()
	except:
			return about.getHardwareTypeString()


def getHardwareName():
	return about.getHardwareTypeString()


def getImageName():
	return about.getImageTypeString()


def getImageShortName(image=None):
	"""Convert an 'OpenPLi type <version>' image string to a short image name."""
	if image is None:
		image = about.getImageTypeString()

	parts = image.split()
	n_parts = len(parts)
	if n_parts == 3:
		version = parts[1].lower()
		major, minor = parts[2].split(".", 1)
		return "%s%02d%02d" % (version, int(major), int(minor))
	elif n_parts == 2:
		return parts[1].lower()
	return image.lower().replace(" ", "")

def getOEVersion():
	return about.getOEVersionString()


def getEnigmaVersion():
	return about.getEnigmaVersionString()


def getCurrentSlot():
	try:
		from Tools.Multiboot import getCurrentImage
		return getCurrentImage()
	except:
		return None


# here we define which backup archive filename formats are accepted
def isArchiveName(filename):
	if not filename.endswith(".tar.gz"):
		return False

	# new format: YYYYMMDD_HHMM...
	if re.match(r"^\d{8}_\d{4}\.", filename):
		return True

	# old format: backup.YYYYMMDD_HHMM...
	if re.match(r"^backup\.\d{8}_\d{4}\.", filename):
		return True

	return False


def padSize(size, width):
    s = str(size)
    return "  " * (width - len(s)) + s


def getArchiveDateTime(filename):
	match = re.search(r"(?:^|backup\.)(\d{8})_(\d{2})(\d{2})", filename)
	if not match:
		return _("Unknown time")

	date = match.group(1)
	hour = match.group(2)
	minute = match.group(3)

	try:
		t = mktime((
			int(date[:4]), int(date[4:6]), int(date[6:8]),
			int(hour), int(minute),
			0, 0, 0, -1
		))
		return " ".join(FuzzyTime(t, inPast=True))
	except:
		return _("Unknown time")

def validateArchiveParameters(info, filters):
	archiveInfo = {}

	for line in info.splitlines():
		if "=" in line:
			key, value = line.split("=", 1)
			archiveInfo[key.strip()] = value.strip()

	current = {
		"mac": getMacAddress(),
		"hostname": getHostName(),
		"image": getImageName(),
		"slot": "slot%d" % getCurrentSlot() if getCurrentSlot() is not None else "",
	}

	mismatch = []
	for key, value in current.items():
		# skip disabled parameter filters
		if not filters.get(key):
			continue

		# validate only parameters available in autobackup.info
		if key not in archiveInfo:
			continue

		if archiveInfo[key] != value:
			mismatch.append(key)

	return mismatch


class Config(ConfigListScreen, Screen):
	skin = """
<screen position="center,center" size="560,450" title="AutoBackup Configuration" >
	<ePixmap name="red"    position="0,0"   zPosition="2" size="140,40" pixmap="skin_default/buttons/red.png" transparent="1" alphatest="on" />
	<ePixmap name="green"  position="140,0" zPosition="2" size="140,40" pixmap="skin_default/buttons/green.png" transparent="1" alphatest="on" />
	<ePixmap name="yellow" position="280,0" zPosition="2" size="140,40" pixmap="skin_default/buttons/yellow.png" transparent="1" alphatest="on" />
	<ePixmap name="blue"   position="420,0" zPosition="2" size="140,40" pixmap="skin_default/buttons/blue.png" transparent="1" alphatest="on" />

	<widget name="key_red" position="0,0" size="140,40" valign="center" halign="center" zPosition="4"  foregroundColor="white" font="Regular;20" transparent="1" shadowColor="background" shadowOffset="-2,-2" />
	<widget name="key_green" position="140,0" size="140,40" valign="center" halign="center" zPosition="4"  foregroundColor="white" font="Regular;20" transparent="1" shadowColor="background" shadowOffset="-2,-2" />
	<widget name="key_yellow" position="280,0" size="140,40" valign="center" halign="center" zPosition="4"  foregroundColor="white" font="Regular;20" transparent="1" shadowColor="background" shadowOffset="-2,-2" />
	<widget name="key_blue" position="420,0" size="140,40" valign="center" halign="center" zPosition="4"  foregroundColor="white" font="Regular;20" transparent="1" shadowColor="background" shadowOffset="-2,-2" />

	<widget name="config" position="10,40" size="540,200" scrollbarMode="showOnDemand" />
	<widget name="statusbar" position="10,250" size="470,20" font="Regular;18" />
	<widget name="description" position="10,280" size="540,46" font="Regular;20" valign="center"/>
	<widget name="status" position="10,330" size="540,130" font="Console;14" />

	<ePixmap alphatest="on" pixmap="skin_default/icons/clock.png" position="480,383" size="14,14" zPosition="3"/>
	<widget font="Regular;18" halign="left" position="505,380" render="Label" size="55,20" source="global.CurrentTime" transparent="1" valign="center" zPosition="3">
		<convert type="ClockToText">Default</convert>
	</widget>
</screen>"""

	def __init__(self, session, args=0):
		self.session = session
		self.skinName = ["Config_AutoBackup", "Config"]
		self.setup_title = _("AutoBackup Configuration")
		Screen.__init__(self, session)
		self.cfg = config.plugins.autobackup
		choices = getLocationChoices()
		if choices:
			currentwhere = self.cfg.where.value
			defaultchoice = choices[0][0]
			for k, v in choices:
				if k == currentwhere:
					defaultchoice = k
					break
		else:
			defaultchoice = ""
			choices = [("", _("Nowhere"))]
		self.cfgwhere = ConfigSelection(default=defaultchoice, choices=choices)

		self.createSetup()
		ConfigListScreen.__init__(self, self.list, session=session, on_change=self.changedEntry)

		self["key_red"] = Button(_("Cancel"))
		self["key_green"] = Button(_("Save"))
		self["key_yellow"] = Button(_("Manual"))
		self["key_blue"] = Button(_("Restore"))
		self["key_menu"] = StaticText(_("MENU"))
		self["description"] = Label()
		self["statusbar"] = Label()
		self["status"] = ScrollLabel('', showscrollbar=False)
		self["setupActions"] = ActionMap(["SetupActions", "ColorActions", "MenuActions"],
		{
			"red": self.cancel,
			"green": self.save,
			"yellow": self.dobackup,
			"blue": self.dorestore,
			"save": self.save,
			"cancel": self.cancel,
			"ok": self.ok,
			"menu": self.menu,
		}, -2)
		self.onChangedEntry = []
		self.data = ''
		self.container = enigma.eConsoleAppContainer()
		self.container.appClosed.append(self.appClosed)
		self.container.dataAvail.append(self.dataAvail)

		writeLog("","w")

		self.archiveAfterBackup = False  # temporary for create archive too
		self.cfgwhere.addNotifier(self.changedWhere)
		self.onClose.append(self.__onClose)
		self.setTitle(_("AutoBackup Configuration"))
		self.activeArchiveFilters = None

	def createSetup(self):
		self.list = []
		self.list.append((_("Backup location"), self.cfgwhere, _("Directory where backup files are created.")))
		self.list.append((_("Experimental: Archive information priority"), self.cfg.method, _("Select whether archive information is read from autobackup.info first or from the archive filename first."))),
		self.list.append((_("Daily automatic backup"), self.cfg.enabled, _("Automatically creates a backup every day at the specified time.")))
		if self.cfg.enabled.value:
			self.list.append((4 * " " + _("Automatic start time"), self.cfg.wakeup, _("Time when the daily automatic backup starts.")))
		self.list.append((_("Create Autoinstall"), self.cfg.autoinstall, _("Creates an Autoinstall file with a list of installed packages.")))
		self.list.append((_("EPG cache backup"), self.cfg.epgcache, _("Saves the contents of the EPG cache to a file before creating a backup.")))
		self.list.append((_("Save previous backup"), self.cfg.prevbackup, _("Saves the previous backup before creating a new one.")))
		self.list.append((_("Create backup archive after backup"), self.cfg.backuparchive, _("Automatically creates a backup archive after every successful backup, both manual and scheduled."))) # temporary for create archiv too

	# for summary:
	def changedEntry(self):
		current = self["config"].getCurrent()
		if current and current[1] in (self.cfg.enabled,):
			self.createSetup()
			self["config"].list = self.list
			self["config"].l.setList(self.list)

		for x in self.onChangedEntry:
			x()

	def getCurrentEntry(self):
		return self["config"].getCurrent()[0]

	def getCurrentValue(self):
		return str(self["config"].getCurrent()[1].getText())

	def createSummary(self):
		from Screens.Setup import SetupSummary
		return SetupSummary

	def changedWhere(self, cfg):
		if not cfg.value:
			self["status"].setText(_("No suitable media found, insert USB stick, flash card or harddisk."))
		else:
			config.plugins.autobackup.where.value = cfg.value
			path = os.path.join(cfg.value, 'backup')
			try:
				if os.path.isfile(os.path.join(path, ".timestamp")) and os.path.isfile(os.path.join(path, "PLi-AutoBackup.tar.gz")):
					st = os.stat(os.path.join(path, ".timestamp"))
					self["status"].setText(_("Last backup date") + ": " + " ".join(FuzzyTime(st.st_mtime, inPast=True)))
				else:
					self["status"].setText(_("No backup present"))
			except Exception as ex:
				print("Failed to stat %s: %s" % (path, ex))
				self["status"].setText(_("No backup present"))

	def __onClose(self):
		self.cfgwhere.notifiers.remove(self.changedWhere)

	def ok(self):
		if hasattr(self, "keySelect"):
			self.keySelect()
		else:
			self.save()

	def save(self):
		config.plugins.autobackup.where.value = self.cfgwhere.value
		config.plugins.autobackup.where.save()
		self.saveAll()
		self.close(True, self.session)

	def cancel(self):
		if self["config"].isChanged():
			self.session.openWithCallback(
				self.cancelConfirmed,
				MessageBox,
				_("Discard unsaved changes?"),
				type=MessageBox.TYPE_YESNO,
				default=False
			)
			return

		for x in self["config"].list:
			x[1].cancel()
		self.close(False, self.session)

	def cancelConfirmed(self, answer):
		if answer:
			for x in self["config"].list:
				x[1].cancel()
			self.close(False, self.session)

	def menu(self):
		lst = [
			(_("Select files to backup"), self.selectFiles, _("Select files and folders to include in the backup. Basic backup items are already selected.")),
			(_("Run a backup now"), self.dobackup, _("Create a backup of the current settings.")),
			(_("Backup EPG cache"), self.doepgcachebackup, _("Save current contents of EPG cache to a file.")),
			(_("Run autoinstall"), self.doautoinstall, _("Install all plugins listed in the 'autoinstall' file. Already installed plugins are skipped.")),
			(_("Remove autoinstall list"), self.doremoveautoinstall, _("Remove the 'autoinstall' file from a backup.")),
			(_("Restore"), self.dorestore, _("Restore settings from the current backup.")),
			(_("Create archive with current settings"), self.doArchiveCurrentBackup, _("Create a separate archive with current settings and autoinstall list without overwriting the existing backup. The hostname and slot number are added to the archive name.")),
			(_("Restore previous backup"), self.doRestorePreviousManual, _("Restore settings from a selected archive. MAC address is verified, archive is extracted and settings are restored.")),
		]
		self.session.openWithCallback(self.menuDone, ChoiceBox, list=lst)

	def menuDone(self, result):
		if not result or not result[1]:
			return
		result[1]()

	def selectFiles(self):
		self.session.open(BackupSelection)

	def showOutput(self):
		self["status"].setText(self.data)

	def dobackup(self):
		if not self.cfgwhere.value:
			return

		self.archiveAfterBackup = self.cfg.backuparchive.value  # temporary for create archive too

		self.saveAll()
		# Write config file before creating the backup so we have it all
		configfile.save()
		if config.plugins.autobackup.epgcache.value:
			self.doepgcachebackup()
		self.data = ''
		self.showOutput()
		self["statusbar"].setText(_('Running...'))
		cmd = plugin.backupCommand()
		if self.container.execute(cmd):
			print("[AutoBackup] failed to execute")
			self.archiveAfterBackup = False  # temporary for create archive too
			self.showOutput()

	def dorestore(self):
		if 1:
			self.doRestoreNew()
		else:
			backupList = []
			foundBackupLocations = [media for media in os.listdir("/media/") if os.path.isdir(os.path.join("/media/", media))]
			for backupMedia in foundBackupLocations:
				path = "/media/%s/backup/" % backupMedia
				if os.path.isfile(path + "PLi-AutoBackup.tar.gz") and os.path.isfile(path + ".timestamp"):
					try:
						st = os.stat(os.path.join(path, ".timestamp"))
						backupList.append(("/media/%s " % backupMedia + _("from: ") + " ".join(FuzzyTime(st.st_mtime, inPast=True)), "/media/%s" % backupMedia, st.st_mtime))
					except Exception as ex:
						print("Failed to stat %s: %s" % (path, ex))

			if not backupList:
				self.session.open(MessageBox, _("No settings backups found"), type=MessageBox.TYPE_ERROR, timeout=10)
				return
			backupList.sort(key=lambda b: b[2], reverse=True)
			self.session.openWithCallback(self.dorestorenow_reason, MessageBox, _("Choose settings backup which should be restored.\nDo you really want to restore these settings and restart?"), list=backupList)

	def dorestorenow_reason(self, path):
		if not path:
			return
		reason = getReasons(self.session)
		if reason:
			text = reason + "\n" + _("Do you want to restore your settings?")
			self.session.openWithCallback(boundFunction(self.dorestorenow, path), MessageBox, text, simple=True)
		else:
			self.dorestorenow(path)

	def dorestorenow(self, path, answer=True):
		if not path or not answer:
			return
		self.data = ''
		self.showOutput()
		self["statusbar"].setText(_('Running...'))
		cmd = '/etc/init.d/settings-restore.sh ' + path + ' ; killall -9 enigma2'
		if self.container.execute(cmd):
			print("[AutoBackup] failed to execute")
			self.showOutput()

	def doautoinstall(self):
		backupList = []
		foundBackupLocations = [media for media in os.listdir("/media/") if os.path.isdir(os.path.join("/media/", media))]
		for backupMedia in foundBackupLocations:
			path = "/media/%s/backup/" % backupMedia
			if os.path.isfile(path + "autoinstall") and os.path.isfile(path + ".timestamp"):
				try:
					st = os.stat(os.path.join(path, ".timestamp"))
					backupList.append(("/media/%s " % backupMedia + _("from: ") + " ".join(FuzzyTime(st.st_mtime, inPast=True)), "/media/%s" % backupMedia, st.st_mtime))
				except Exception as ex:
					print("Failed to stat %s: %s" % (path, ex))

		if not backupList:
			self.session.open(MessageBox, _("No autoinstall list found"), type=MessageBox.TYPE_ERROR, timeout=10)
			return
		backupList.sort(key=lambda b: b[2], reverse=True)
		self.session.openWithCallback(self.doautoinstallnow, MessageBox, _("Choose a backup.\nThis will reinstall all plugins from your backup.\nDo you really want to reinstall?"), list=backupList)

	def doautoinstallnow(self, path):
		if not path:
			return
		self.data = ''
		self.showOutput()
		self["statusbar"].setText(_('Running...'))
		cmd = 'opkg update && while read f o; do opkg install $o $f; done < ' + path + '/backup/autoinstall'
		if self.container.execute(cmd):
			print("[AutoInstall] failed to execute")
			self.showOutput()

	def doremoveautoinstall(self):
		backupList = []
		foundBackupLocations = [media for media in os.listdir("/media/") if os.path.isdir(os.path.join("/media/", media))]
		for backupMedia in foundBackupLocations:
			path = "/media/%s/backup/" % backupMedia
			if os.path.isfile(path + "autoinstall") and os.path.isfile(path + ".timestamp"):
				try:
					st = os.stat(os.path.join(path, ".timestamp"))
					backupList.append(("/media/%s " % backupMedia + _("from: ") + " ".join(FuzzyTime(st.st_mtime, inPast=True)), "/media/%s" % backupMedia, st.st_mtime))
				except Exception as ex:
					print("Failed to stat %s: %s" % (path, ex))

		if not backupList:
			self.session.open(MessageBox, _("No autoinstall list found"), type=MessageBox.TYPE_ERROR, timeout=10)
			return
		backupList.sort(key=lambda b: b[2], reverse=True)
		self.session.openWithCallback(self.doremoveautoinstallnow, MessageBox, _("Choose a backup.\nThis will delete autoinstall list.\nDo you really want to continue?"), list=backupList)

	def doremoveautoinstallnow(self, path):
		if not path:
			return
		path = os.path.join(path, 'backup', "autoinstall")
		try:
			os.unlink(path)
		except:
			pass
		try:
			macaddr = open('/sys/class/net/eth0/address').read().strip().replace(':', '')
			os.unlink(path + macaddr)
		except:
			pass

	def doepgcachebackup(self):
		enigma.eEPGCache.getInstance().save()

	def appClosed(self, retval):
		print("[AutoBackup] done:", retval)

		if not retval and self.archiveAfterBackup: # temporary for create archive too
			self.archiveAfterBackup = False
			self.doArchiveCurrentBackup()
			return

		if retval:
			txt = _("Failed")
		else:
			txt = _("Done")
		self.showOutput()
		self.data = ''
		self["statusbar"].setText(txt)
		self.changedWhere(self.cfgwhere)

	def dataAvail(self, s):
		s = s.decode()
		print("[AutoBackup]", s.strip())
		self["status"].appendText(s)

		writeLog(s, "a")

	def doRestoreNew(self):
		backupDir = os.path.join(self.cfgwhere.value, "backup")

		if self.activeArchiveFilters is None:
			self.activeArchiveFilters = ARCHIVE_FILTERS_RESTORE.copy()

		archives = getArchives(backupDir, self.activeArchiveFilters)
		if archives:
			filename, backupFile = archives[0][:2]
			backupList = [("%s %s %s" % (self.cfgwhere.value, _("from: "), getArchiveDateTime(filename)), True)]
			self.session.openWithCallback(
				boundFunction(self.doRestorePreviousConfirmed, backupFile, backupDir),
				MessageBox,
				_("Choose settings backup which should be restored.\nDo you really want to restore these settings and restart?"),
				list=backupList
			)
		else:
			# retry with less strict filters - f.eg. using MAC only - and let the user choose from available archives
			self.activeArchiveFilters = ARCHIVE_FILTERS_RESTORE_FALLBACK.copy()
			self.doRestorePrevious()

	def doRestorePreviousManual(self):
		self.activeArchiveFilters = ARCHIVE_FILTERS_MANUAL.copy()
		self.doRestorePrevious()

	def doRestorePrevious(self, selectedIndex=None):
		backupDir = os.path.join(self.cfgwhere.value, "backup")
		if self.activeArchiveFilters is None:
			self.activeArchiveFilters = ARCHIVE_FILTERS_RESTORE.copy()
		self.session.openWithCallback(
			self.doRestorePreviousClosed,
			ArchiveList,
			backupDir,
			self.activeArchiveFilters,
			selectedIndex,
			self
		)

	def doRestorePreviousClosed(self, result):
		self.activeArchiveFilters = None

	def doRestorePreviousNow(self, backupDir, result, archiveList):
		selection, self.activeArchiveFilters, selectedIndex = result

		backupFile = selection[1]

		currentMac = getMacAddress()
		backupMac = self.checkPreviousBackup(backupFile)

		with tarfile.open(backupFile, "r:gz") as tar:
			files = []
			hasArchiveInfo = False
			for member in tar.getmembers():
				if member.name == "autobackup.info":
					hasArchiveInfo = True
				if not member.issym() and not member.islnk():
					size = padSize(member.size, 8)
					files.append("\c00b0b0b0%s B\C  %s" % (size, member.name))
			contents = "\n".join(sorted(files, key=str.lower))

		if hasArchiveInfo:
			archiveInfo = self.readAutoBackupInfo(backupFile)
			mismatch = validateArchiveParameters(archiveInfo, {
				"mac": True,
				"hostname": True,
				"image": True,
				"slot": True,
			})
			info = self.formatAutoBackupInfo(archiveInfo, mismatch)
		else:
			mismatch = []
			info = _(" - no backup information available")

		if mismatch:
			info = "%s\n\n%s" % (_(" - red values do not match this receiver"), info)

		choices = [
			(_("Cancel"), "cancel"),
			(_("Restore settings now"), "restore"),
			(_("Delete this archive"), "delete"),
		]

		warning = ""

		if backupMac != currentMac:
			warning = _("Backup was created for another receiver.\nCurrent receiver MAC: %s\n\n") % currentMac

		if backupMac != currentMac:
			picon = MessageBox.TYPE_ERROR
		elif mismatch:
			picon = MessageBox.TYPE_WARNING
		else:
			picon = MessageBox.TYPE_YESNO

		self.session.openWithCallback(
			boundFunction(
				self.doRestorePreviousAction,
				backupFile,
				backupDir,
				selectedIndex,
				archiveList
			),
			MessageBox,
			warning +
			_("Backup information") +
			":\n\n" + info +
			"\n\n" + _("Archive contents") +
			":\n" + contents +
			"\n\n" + _("What do you want to do?"),
			list=choices,
			picon = picon
		)
		return

	def doArchiveCurrentBackup(self):
		if not self.cfgwhere.value:
			return

		self.data = ''
		self.showOutput()
		self["statusbar"].setText(_('Running...'))

		archive = ArchiveCreator(self.cfgwhere.value)
		cmd = archive.buildCommand()

		if self.container.execute(cmd):
			print("[AutoBackup] failed to execute")
			self.showOutput()

	def doRestorePreviousAction(self, backupFile, backupDir, selectedIndex, archiveList, action):
		if action == "restore":
			archiveList.close(None)
			self.doRestorePreviousConfirmed(backupFile, backupDir, True)
		elif action == "delete":
			self.session.openWithCallback(
				boundFunction(
					self.doDeletePreviousConfirmed,
					backupFile,
					selectedIndex,
					archiveList
				),
				MessageBox,
				_("Do you really want to delete this backup archive?") + "\n\n" + os.path.basename(backupFile),
				type=MessageBox.TYPE_YESNO,
				default=False
			)

	def doDeletePreviousConfirmed(self, backupFile, selectedIndex, archiveList, answer):
		if not answer:
			return
		try:
			os.remove(backupFile)
		except Exception as ex:
			print("[AutoBackup] Failed to delete backup %s: %s" % (backupFile, ex))
			self.session.open(
				MessageBox,
				_("Failed to delete backup."),
				type=MessageBox.TYPE_ERROR,
				timeout=10
			)
			return
		archiveList.removeArchive(selectedIndex)

	def doRestorePreviousConfirmed(self, backupFile, backupDir, answer):
		if not answer:
			return

		self.data = ''
		self.showOutput()
		self["statusbar"].setText(_('Running...'))

		cmd = (
			'tar -tzf "%s" && '
			'tar -xzf "%s" -C "%s" '
			'--exclude="PLi-AutoBackup.tar.gz" '
			'--exclude="autoinstall" '
			'&& /etc/init.d/settings-restore.sh %s ; killall -9 enigma2'
		) % (backupFile, backupFile, backupDir, self.cfgwhere.value)

		if self.container.execute(cmd):
			print("[AutoBackup] failed to execute")
		self.showOutput()

	def formatAutoBackupInfo(self, archiveInfo, mismatch=None):
		mismatch = set(mismatch or [])
		result = []

		for line in archiveInfo.splitlines():
			if "=" not in line:
				result.append(line)
				continue

			key, value = line.split("=", 1)
			key = key.strip()
			formatted = "%s:\t%s" % (key, value.strip())

			if key in mismatch:
				formatted = "\c00ff4040%s\C" % formatted

			result.append(formatted)

		return "\n".join(result)

	def readAutoBackupInfo(self, backupFile):
		try:
			with tarfile.open(backupFile, "r:gz") as tar:
				f = tar.extractfile("autobackup.info")
				if f:
					return f.read().decode("utf-8")
		except Exception as ex:
			print("[AutoBackup] Failed to read autobackup.info:", ex)

		return _("- unable to read autobackup.info")

	def checkPreviousBackup(self, backupFile):
		try:
			with tarfile.open(backupFile, "r:gz") as tar:
				for name in tar.getnames():
					base = os.path.basename(name)
					if base.endswith(".tar.gz"):
						base = base[:-7]
					if len(base) >= 12:
						mac = base[-12:]
						if all(c in "0123456789abcdefABCDEF" for c in mac):
							return mac.lower()
		except Exception as ex:
			print("[AutoBackup] Failed to check backup: %s" % ex)
		return None


class ArchiveCreator:
	def __init__(self, destination):
		self.destination = destination
		self.tmpBackupDir = "/tmp/autobackup.%d" % os.getpid()
		self.mac = getMacAddress()
		self.hostname = getHostName()
		self.image = getImageShortName()
		self.slot = getCurrentSlot()

	def createInfo(self):
		backupDir = os.path.join(self.tmpBackupDir, "backup")

		if not os.path.isdir(backupDir):
			os.makedirs(backupDir)

		infoFile = os.path.join(backupDir, "autobackup.info")

		with open(infoFile, "w") as f:
			f.write("mac=%s\n" % self.mac)
			f.write("hostname=%s\n" % self.hostname)
			f.write("hardware=%s\n" % getHardwareName())
			f.write("image=%s\n" % getImageName())
			f.write("oe=%s\n" % getOEVersion())
			f.write("enigma=%s\n" % getEnigmaVersion())
			if self.slot is not None:
				f.write("slot=slot%d\n" % self.slot)

	def buildCommand(self):
		slotSuffix = ""
		if self.slot is not None:
			slotSuffix = ".slot%02d" % self.slot

		if os.path.isdir(self.tmpBackupDir):
			shutil.rmtree(self.tmpBackupDir)

		os.makedirs(os.path.join(self.tmpBackupDir, "backup"))
		self.createInfo()

		return (
			'%s && '
			'cd "%s/backup" && '
			'tar -czf "%s/backup/$(date +%%Y%%m%%d_%%H%%M).%s.%s.%s%s.tar.gz" '
			'PLi-AutoBackup????????????.tar.gz autoinstall???????????? autobackup.info; '
			'rm -rf "%s"'
		) % (
			plugin.backupCommand(self.tmpBackupDir, fullArchive=True),
			self.tmpBackupDir,
			self.destination,
			self.mac,
			self.hostname,
			self.image,
			slotSuffix,
			self.tmpBackupDir
		)


def getRequiredArchiveInfo(filters):
	return [key for key in ("mac", "hostname", "image", "slot") if filters[key]]


def readArchiveInfoFromName(filename):
	info = {}

	match = re.match(
		r"^\d{8}_\d{4}\.([0-9a-fA-F]{12})\.([^.]+)\.([^.]+)(?:\.slot(\d+))?\.tar\.gz$",
		filename
	)

	if match:
		info["mac"] = match.group(1).lower()
		info["hostname"] = match.group(2)
		info["image"] = match.group(3)

		if match.group(4) is not None:
			info["slot"] = "slot%d" % int(match.group(4))

	return info


def readArchiveInfoFromTar(archiveFile, required):
	info = {}

	try:
		with tarfile.open(archiveFile, "r:gz") as tar:
			try:
				f = tar.extractfile("autobackup.info")
				if f:
					for line in f.read().decode("utf-8").splitlines():
						if "=" not in line:
							continue

						key, value = line.split("=", 1)
						key = key.strip()
						value = value.strip()

						if key == "image":
							value = getImageShortName(value)

						info[key] = value
			except KeyError:
				pass

			# Fallback for older archives: try to extract MAC
			# address from filenames inside the archive.
			if "mac" in required and "mac" not in info:
				for name in tar.getnames():
					base = os.path.basename(name)
					match = re.search(r"([0-9a-fA-F]{12})\.tar\.gz$", base)

					if match:
						info["mac"] = match.group(1).lower()
						break

	except Exception as ex:
		print("[AutoBackup] Failed to read archive information from %s: %s" % (archiveFile, ex))

	return info

def mergeMissingArchiveInfo(info, fallbackInfo):
	for key, value in fallbackInfo.items():
		if key not in info:
			info[key] = value

	return info

def readArchiveInfoName(archiveFile, filename, filters):
	required = getRequiredArchiveInfo(filters)
	info = readArchiveInfoFromName(filename)

	# All information required by the active filters
	# was found in the archive name.
	if all(key in info for key in required):
		return info

	archiveInfo = readArchiveInfoFromTar(archiveFile, required)
	return mergeMissingArchiveInfo(info, archiveInfo)

def readArchiveInfoFile(archiveFile, filename, filters):
	required = getRequiredArchiveInfo(filters)
	info = readArchiveInfoFromTar(archiveFile, required)

	filenameInfo = readArchiveInfoFromName(filename)
	return mergeMissingArchiveInfo(info, filenameInfo)


def archiveMatchesFilters(fullpath, filename, filters):
		if not any(filters[key] for key in ("mac", "hostname", "image", "slot")):
			return True
		readArchiveInfo = (readArchiveInfoFile if config.plugins.autobackup.method.value else readArchiveInfoName)
		info = readArchiveInfo(fullpath, filename, filters)

		if filters["mac"] and info.get("mac", "").lower() != getMacAddress().lower():
			return False

		if filters["hostname"] and info.get("hostname", "") != getHostName():
			return False

		if filters["image"] and info.get("image", "") != getImageShortName():
			return False

		if filters["slot"]:
			currentSlot = getCurrentSlot()
			archiveSlot = info.get("slot")

			if currentSlot is None:
				if archiveSlot:
					return False
			elif archiveSlot != "slot%d" % currentSlot:
				return False

		return True

def getArchives(backupDir, filters):
	archives = []

	if os.path.isdir(backupDir):
		for entry in os.scandir(backupDir):
			if not entry.is_file():
				continue
			if not isArchiveName(entry.name):
				continue
			if not archiveMatchesFilters(entry.path, entry.name, filters):
				continue

			match = re.search(r"\d{8}_\d{4}", entry.name)
			sortKey = match.group(0).replace("_", "")
			archives.append((entry.name, entry.path, sortKey))

	if filters["alphabetical"]:
		archives.sort(key=lambda archive: archive[0].lower(), reverse=True)
	else:
		archives.sort(key=lambda archive: archive[2], reverse=True)

	return archives


class ArchiveList(Screen):
	skin = """
	<screen position="center,center" size="900,400" title="Backup archive list">
		<ePixmap name="red"    position="0,0"   zPosition="2" size="140,40" pixmap="skin_default/buttons/red.png" transparent="1" alphatest="on" />
		<ePixmap name="green"  position="140,0" zPosition="2" size="140,40" pixmap="skin_default/buttons/green.png" transparent="1" alphatest="on" />
		<ePixmap name="yellow" position="280,0" zPosition="2" size="140,40" pixmap="skin_default/buttons/yellow.png" transparent="1" alphatest="on" />
		<ePixmap name="blue"   position="420,0" zPosition="2" size="140,40" pixmap="skin_default/buttons/blue.png" transparent="1" alphatest="on" />
		<widget source="key_red" render="Label" position="0,0" size="140,40" valign="center" halign="center" zPosition="4"  foregroundColor="white" font="Regular;20" transparent="1" shadowColor="background" shadowOffset="-2,-2" />
		<widget source="key_green" render="Label" position="140,0" size="140,40" valign="center" halign="center" zPosition="4"  foregroundColor="white" font="Regular;20" transparent="1" shadowColor="background" shadowOffset="-2,-2" />
		<widget source="key_yellow" render="Label" position="280,0" size="140,40" valign="center" halign="center" zPosition="4"  foregroundColor="white" font="Regular;20" transparent="1" shadowColor="background" shadowOffset="-2,-2" />
		<widget source="key_blue" render="Label" position="420,0" size="140,40" valign="center" halign="center" zPosition="4"  foregroundColor="white" font="Regular;20" transparent="1" shadowColor="background" shadowOffset="-2,-2" />
		<widget name="list" position="10,40" size="880,350" scrollbarMode="showOnDemand" />
		<widget name="message" position="10,40" size="880,350" font="Regular;20" halign="center" valign="center" transparent="1" />
	</screen>
	"""

	def __init__(self, session, backupDir, filters, selectedIndex, configScreen):
		Screen.__init__(self, session)
		self.skinName = ["ArchiveList"]
		self.setTitle(_("Backup archive list"))

		self.backupDir = backupDir
		self.archiveFilters = filters.copy()
		self.selectedIndex = selectedIndex
		self.configScreen = configScreen

		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Select"))
		self["key_blue"] = StaticText(_("Filters"))
		self["list"] = MenuList([])
		self["message"] = Label("")

		self["actions"] = ActionMap(
			["OkCancelActions", "ColorActions", "DirectionActions"],
			{
				"cancel": self.exit,
				"red": self.exit,
				"green": self.select,
				"blue": self.openFilter,
				"ok": self.select,
				"up": self["list"].up,
				"down": self["list"].down,
				"left": self["list"].pageUp,
				"right": self["list"].pageDown,
			},-1
		)

		self.loadArchives()
		self.onLayoutFinish.append(self.layoutFinished)

	def layoutFinished(self):
		self.restoreSelection()

	def restoreSelection(self):
		if self.selectedIndex is not None and self["list"].list:
			self["list"].moveToIndex(min(self.selectedIndex, len(self["list"].list) - 1))

	def loadArchives(self):
		archives = getArchives(self.backupDir, self.archiveFilters)
		self["list"].setList(archives)
		self["message"].setText("" if archives else _("No backup archives match the current filters.\n\nTry changing the filter settings."))

	def openFilter(self):
		self.session.openWithCallback(self.filterClosed, ArchiveFilter, self.archiveFilters)

	def filterClosed(self, filters):
		if filters is None:
			return
		if filters == self.archiveFilters:
			return

		reloadRequired = any(
			filters[key] != self.archiveFilters[key]
			for key in ("mac", "hostname", "image", "slot")
		)

		self.archiveFilters = filters

		if reloadRequired:
			# active filters changed, rebuild the archive list
			self.loadArchives()
		else:
			# only sorting changed, reorder the current list
			archives = list(self["list"].list)
			archives.reverse()
			self["list"].setList(archives)

		self.restoreSelection()

	def select(self):
		if not self["list"].list:
			return

		index = self["list"].getSelectedIndex()
		self.selectedIndex = index
		self.configScreen.doRestorePreviousNow(
			self.backupDir,
			(
				self["list"].getCurrent(),
				self.archiveFilters.copy(),
				index
			),
			self
		)

	def removeArchive(self, index):
		archives = list(self["list"].list)

		if 0 <= index < len(archives):
			del archives[index]

		self["list"].setList(archives)
		self["message"].setText(
			"" if archives else
			_("No backup archives match the current filters.\n\nTry changing the filter settings.")
		)

		if archives:
			self.selectedIndex = min(index, len(archives) - 1)
			self.restoreSelection()
		else:
			self.selectedIndex = None

	def exit(self):
		self.close(None)

class ArchiveFilter(ConfigListScreen, Screen):
	skin = """
	<screen position="center,center" size="560,328" title="Archive filters">
		<ePixmap pixmap="skin_default/buttons/red.png" position="0,0" size="140,40" alphatest="on" />
		<ePixmap pixmap="skin_default/buttons/green.png" position="140,0" size="140,40" alphatest="on" />
		<widget source="key_red" render="Label" position="0,0" size="140,40" valign="center" halign="center" zPosition="4"  foregroundColor="white" font="Regular;20" transparent="1" shadowColor="background" shadowOffset="-2,-2" />
		<widget source="key_green" render="Label" position="140,0" size="140,40" valign="center" halign="center" zPosition="4"  foregroundColor="white" font="Regular;20" transparent="1" shadowColor="background" shadowOffset="-2,-2" />
		<widget name="config" position="10,50" size="540,200" scrollbarMode="showOnDemand" />
		<ePixmap pixmap="div-h.png" position="0,252" zPosition="10" size="900,2" />
		<widget name="description" position="10,255" size="540,69" font="Regular;20" valign="center"/>
	</screen>"""

	def __init__(self, session, filters):
		Screen.__init__(self, session)
		self.setTitle(_("Archive filters"))

		self.filterMac = ConfigYesNo(default=filters.get("mac", True))
		self.filterHostname = ConfigYesNo(default=filters.get("hostname", False))
		self.filterImage = ConfigYesNo(default=filters.get("image", False))
		self.filterSlot = ConfigYesNo(default=filters.get("slot", False))
		self.filterAlphabetical = ConfigYesNo(default=filters.get("alphabetical", False))

		configList = []

		configList.append((_("Receiver MAC"), self.filterMac, _("Match the current receiver MAC address using the archive name, info file or filenames in the archive.")))
		configList.append((_("Hostname"), self.filterHostname, _("Match the current hostname using the archive name or the info file.")))
		configList.append((_("Image"), self.filterImage, _("Match the current image name using the archive name or the info file.")))
		configList.append((_("Slot"), self.filterSlot, _("Match the current slot number using the archive name or the info file.")))
		configList.append((_("Sort alphabetically"), self.filterAlphabetical, _("Sort archives alphabetically instead of by creation time.")))
		ConfigListScreen.__init__(self, configList, session=session)

		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Apply filters"))

		self["actions"] = ActionMap(
			["OkCancelActions", "ColorActions"],
			{
				"cancel": self.cancel,
				"red": self.cancel,
				"green": self.apply,
			}, -1
		)

		self["description"] = Label("")
		self["config"].onSelectionChanged.append(self.selectionChanged)
		self.selectionChanged()

	def selectionChanged(self):
		current = self["config"].getCurrent()
		if current and len(current) > 2:
			self["description"].setText(current[2])
		else:
			self["description"].setText("")

	def apply(self):
		self.close({
			"mac": self.filterMac.value,
			"hostname": self.filterHostname.value,
			"image": self.filterImage.value,
			"slot": self.filterSlot.value,
			"alphabetical": self.filterAlphabetical.value,
		})

	def cancel(self):
		self.close(None)


class BackupSelection(Screen):
	skin = """
		<screen position="center,center" size="560,400" title="Select files/folders to backup">
			<ePixmap pixmap="skin_default/buttons/red.png" position="0,0" size="140,40" alphatest="on" />
			<ePixmap pixmap="skin_default/buttons/green.png" position="140,0" size="140,40" alphatest="on" />
			<ePixmap pixmap="skin_default/buttons/yellow.png" position="280,0" size="140,40" alphatest="on" />
			<widget source="key_red" render="Label" position="0,0" zPosition="1" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="1" />
			<widget source="key_green" render="Label" position="140,0" zPosition="1" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="#1f771f" transparent="1" />
			<widget source="key_yellow" render="Label" position="280,0" zPosition="1" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="#a08500" transparent="1" />
			<widget name="checkList" position="5,50" size="550,350" transparent="1" scrollbarMode="showOnDemand" />
		</screen>"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.skinName = ["BackupSelection_AutoBackup", "BackupSelection"]
		from Components.Sources.StaticText import StaticText
		from Components.FileList import MultiFileSelectList
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Save"))
		self["key_yellow"] = StaticText()
		selectedFiles = getSelectedFiles()
		defaultDir = '/'
		inhibitDirs = ["/bin", "/boot", "/dev", "/autofs", "/lib", "/proc", "/sbin", "/sys", "/hdd", "/tmp", "/mnt", "/media"]
		self.filelist = MultiFileSelectList(selectedFiles, defaultDir, inhibitDirs=inhibitDirs)
		self["checkList"] = self.filelist
		self.prev_files = selectedFiles
		self["actions"] = ActionMap(["DirectionActions", "OkCancelActions", "ShortcutActions"],
		{
			"cancel": self.exit,
			"red": self.exit,
			"yellow": self.changeSelectionState,
			"green": self.saveSelection,
			"ok": self.okClicked,
			"left": self.filelist.pageUp,
			"right": self.filelist.pageDown,
			"down": self.filelist.down,
			"up": self.filelist.up
		}, -1)
		if not self.selectionChanged in self.filelist.onSelectionChanged:
			self.filelist.onSelectionChanged.append(self.selectionChanged)
		self.onLayoutFinish.append(self.layoutFinished)

	def layoutFinished(self):
		idx = 0
		self["checkList"].moveToIndex(idx)
		self.setWindowTitle()
		self.selectionChanged()

	def setWindowTitle(self):
		self.setTitle(_("Select files/folders to backup"))

	def selectionChanged(self):
		current = self["checkList"].getCurrent()[0]
		text = ""
		if len(current) > 2:
			if current[2] is True:
				text = _("Deselect")
			else:
				text = _("Select")
		self["key_yellow"].setText(text)

	def changeSelectionState(self):
		self["checkList"].changeSelectionState()

	def saveSelection(self):
		saveSelectedFiles(self["checkList"].getSelectedList())
		self.close(None)

	def exit(self):
		if self.prev_files != [os.path.normpath(n.strip()) for n in self["checkList"].getSelectedList()]:
			self.session.openWithCallback(self.exitConfirm, MessageBox, _("Really close without saving settings?"))
		else:
			self.close(None)

	def exitConfirm(self, result):
		if result:
			self.close(None)

	def okClicked(self):
		if self.filelist.canDescent():
			self.filelist.descent()
