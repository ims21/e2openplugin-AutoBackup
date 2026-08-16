# Configuration GUI
from . import _
from . import plugin
import os, tarfile
import enigma
import shutil
import re
from Components.config import config, ConfigSelection, ConfigYesNo
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
from Tools.BoundFunction import boundFunction
from time import mktime, strftime, time


# Code guarded by this flag is temporary and will be removed later.
# It provides experimental timing and count information.
ENABLE_EXPERIMENTAL_FEATURES = True


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
	"enigma": True,
	"slot": True,
}
ARCHIVE_FILTERS_MANUAL = {
	"mac": True,
	"hostname": False,
	"image": False,
	"enigma": False,
	"slot": False,
}
ARCHIVE_FILTERS_RESTORE_FALLBACK = {
	"mac": True,
	"hostname": False,
	"image": False,
	"enigma": False,
	"slot": False,
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


def getEnigmaName(enigma=None):
	if enigma is None:
		enigma = getEnigmaVersion()
	return enigma[11:]


def getCurrentSlot():
	try:
		from Tools.Multiboot import getCurrentImage
		return getCurrentImage()
	except:
		return None


COLOR_RED = "ff4040"
COLOR_GREEN = "40a040"
COLOR_GRAY = "b0b0b0"
COLOR_LIGHTGREEN = "c0ffc0"

def colorText(rrggbb, text):
	return "\\c00%s%s\\C" % (rrggbb, text)



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
		"enigma": getEnigmaName(),
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

		archiveValue = archiveInfo[key]
		if key == "enigma":
			archiveValue = getEnigmaName(archiveValue)

		if archiveValue != value:
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
			"yellow": self.doBackup,
			"blue": self.doRestore,
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

		self.archivePending = False
		self.archiveCreator = None
		self.cfgwhere.addNotifier(self.changedWhere)
		self.onClose.append(self.__onClose)
		self.setTitle(_("AutoBackup Configuration"))
		self.activeArchiveFilters = None

	def createSetup(self):
		self.list = []
		self.list.append((_("Backup location"), self.cfgwhere, _("Directory where backup files are created.")))
		self.list.append((_("Automatic backup"), self.cfg.enabled, _("Automatically creates backups at the selected frequency and start time.")))
		if self.cfg.enabled.value:
			self.list.append((4 * " " + _("Backup frequency"), self.cfg.frequency, _("Select how often an automatic backup is created.")))
			self.list.append((4 * " " + _("Start time"), self.cfg.wakeup, _("Set the reference time for automatic backups.")))
			self.list.append((4 * " " + _("Backup mode"), self.cfg.backupmode, _("Create backup archives only, or also overwrite the local backup each time.")))
		self.list.append((_("Create Autoinstall"), self.cfg.autoinstall, _("Keep an Autoinstall file with a list of installed packages in the local backup.")))
		self.list.append((_("Save EPG cache"), self.cfg.epgcache, _("Saves the contents of the EPG cache to a file before creating a manual backup.")))
		self.list.append((_("Keep backup archives"), self.cfg.keeparchives, _("Select how many backup archives of each type are kept.")))

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
					self["status"].setText(_("Last local backup date") + ": " + " ".join(FuzzyTime(st.st_mtime, inPast=True)))
				else:
					self["status"].setText(_("No local backup present"))
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
		lst = []
		lst.append((_("Select files to backup"), self.selectFiles, _("Select files and folders to include in the backup. Basic backup items are already selected."))),
		lst.append((_("Run a backup now"), self.doBackup, _("Create a local backup and archive of the current settings (same as pressing the yellow button)."))),
		lst.append((_("Backup EPG cache"), self.doepgcachebackup, _("Save current contents of EPG cache to a file."))),
		lst.append((_("Run autoinstall"), self.doAutoinstall, _("Install all plugins listed in the 'autoinstall' file. Already installed plugins are skipped."))),
		lst.append((_("Remove autoinstall list"), self.doRemoveAutoinstall, _("Remove the 'autoinstall' file from a backup."))),
		lst.append((_("Restore"), self.doRestore, _("Restore settings from the current backup."))),
		lst.append((_("Create archive with current settings"), self.doArchiveCurrentSettings, _("Create a separate archive with current settings and autoinstall list without overwriting the existing backup. The hostname and slot number are added to the archive name."))),
		lst.append((_("Restore from archive"), self.doRestorePreviousManual, _("Restore settings from a selected archive. MAC address is verified, archive is extracted and settings are restored."))),

		self.session.openWithCallback(self.menuDone, ChoiceBox, list=lst)

	def menuDone(self, result):
		if not result or not result[1]:
			return
		result[1]()

	def selectFiles(self):
		self.session.open(BackupSelection)

	def showOutput(self):
		self["status"].setText(self.data)

	def doBackup(self):
		if not self.cfgwhere.value:
			return

		self.saveAll()
		# Write config file before creating the backup so we have it all
		plugin.prepareBackup()
		if config.plugins.autobackup.epgcache.value:
			self.doepgcachebackup()

		plugin.writeLog("Manual backup:\n", "w")
		self.data = ''
		self.showOutput()
		self["statusbar"].setText(_('Running...'))

		cmd = plugin.backupCommand(fullArchive=True)
		self.archivePending = True

		if self.container.execute(cmd):
			print("[AutoBackup] failed to execute")
			self.archivePending = False
			self.showOutput()

	def getBackupLocations(self):
			return [media for media in os.listdir("/media/") if os.path.isdir(os.path.join("/media/", media))]

	def doAutoinstall(self):
		backupList = []
		macaddr = getMacAddress()
		foundBackupLocations = self.getBackupLocations()
		for backupMedia in foundBackupLocations:
			path = "/media/%s/backup/" % backupMedia
			autoinstallFile = path + "autoinstall" + macaddr
			macMatched = os.path.isfile(autoinstallFile)
			if not macMatched:
				autoinstallFile = path + "autoinstall"
			if os.path.isfile(autoinstallFile) and os.path.isfile(path + ".timestamp"):
				try:
					st = os.stat(os.path.join(path, ".timestamp"))
					backupList.append(("/media/%s " % backupMedia + _("from: ") + " ".join(FuzzyTime(st.st_mtime, inPast=True)), (autoinstallFile, macMatched), st.st_mtime))
				except Exception as ex:
					print("Failed to stat %s: %s" % (path, ex))

		if not backupList:
			self.session.open(MessageBox, _("No 'autoinstall' file found"), type=MessageBox.TYPE_ERROR, timeout=10)
			return
		backupList.sort(key=lambda b: b[2], reverse=True)
		self.session.openWithCallback(self.doAutoinstallNow, MessageBox, _("Choose a backup.\n\nPlugins from the 'autoinstall' list will be installed. Already installed plugins will be skipped.\n\nDo you really want to continue?"), list=backupList)

	def doAutoinstallNow(self, result, answer=None):
		if not result:
			return
		autoinstallFile, macMatched = result
		if not macMatched and answer is None:
			self.session.openWithCallback(
				boundFunction(self.doAutoinstallNow, result),
				MessageBox,
				_("No 'autoinstall' file matching this receiver's MAC address was found.\n\nThe generic 'autoinstall' file may belong to another receiver.\n\nUse it anyway?"),
				type=MessageBox.TYPE_YESNO,
				default=False,
				picon=MessageBox.TYPE_ERROR
			)
			return
		if not macMatched and not answer:
			return
		self.data = ''
		self.showOutput()
		self["statusbar"].setText(_('Running...'))
		cmd = 'opkg update && while read -r f o; do case "$f" in ""|"#"*) continue ;; esac; opkg install $o $f; done < "%s"' % autoinstallFile
		if self.container.execute(cmd):
			print("[Autoinstall] failed to execute")
			self.showOutput()

	def doRemoveAutoinstall(self):
		backupList = []
		macaddr = getMacAddress()
		foundBackupLocations = self.getBackupLocations()
		for backupMedia in foundBackupLocations:
			path = "/media/%s/backup/" % backupMedia
			if (os.path.isfile(path + "autoinstall" + macaddr) or os.path.lexists(path + "autoinstall")) and os.path.isfile(path + ".timestamp"):
				try:
					st = os.stat(path + ".timestamp")
					backupList.append((
						"/media/%s " % backupMedia + _("from: ") + " ".join(FuzzyTime(st.st_mtime, inPast=True)),
						"/media/%s" % backupMedia,
						st.st_mtime
					))
				except Exception as ex:
					print("Failed to stat %s: %s" % (path, ex))

		if not backupList:
			self.session.open(MessageBox, _("No 'autoinstall' file found"), type=MessageBox.TYPE_ERROR, timeout=10)
			return

		backupList.sort(key=lambda b: b[2], reverse=True)
		self.session.openWithCallback(
			self.doRemoveAutoinstallNow,
			MessageBox,
			_("Choose a backup."),
			list=backupList
		)

	def doRemoveAutoinstallNow(self, path, action="choose", answer=None):
		if not path:
			return

		autoinstallPath = os.path.join(path, "backup", "autoinstall")
		macPath = autoinstallPath + getMacAddress()
		macExists = os.path.isfile(macPath)
		genericExists = os.path.lexists(autoinstallPath)
		genericIsLink = os.path.islink(autoinstallPath)
		brokenLink = genericIsLink and not os.path.exists(autoinstallPath)
		linkMatchesMac = genericIsLink and not brokenLink and os.path.realpath(autoinstallPath) == os.path.realpath(macPath)

		if action is None or action == "back":
			self.doRemoveAutoinstall()
			return

		if action == "choose":
			if not macExists:
				if brokenLink:
					actions = [
						(_("No"), "back"),
						(_("Delete"), "deleteGeneric")
					]
					self.session.openWithCallback(
						boundFunction(self.doRemoveAutoinstallNow, path),
						MessageBox,
						_("Delete 'autoinstall' list?"),
						list=actions
					)
					return

				self.session.openWithCallback(
					boundFunction(self.doRemoveAutoinstallNow, path, "deleteGeneric"),
					MessageBox,
					_("No 'autoinstall' list matching this receiver's MAC address was found.\n\nThe generic 'autoinstall' file may belong to another receiver.\n\nDelete it anyway?"),
					type=MessageBox.TYPE_YESNO,
					default=False,
					picon=MessageBox.TYPE_ERROR
				)
				return

			actions = [
				(_("No"), "back"),
				(_("Delete"), "deleteCurrent")
			]
			if genericExists and not linkMatchesMac and not brokenLink:
				actions.append((
					_("Delete including the generic 'autoinstall' file"),
					"deleteBoth"
				))
			self.session.openWithCallback(
				boundFunction(self.doRemoveAutoinstallNow, path),
				MessageBox,
				_("Delete 'autoinstall' list?"),
				list=actions
			)
			return

		if answer is False:
			self.doRemoveAutoinstall()
			return

		if action == "deleteBoth" and answer is None:
			self.session.openWithCallback(
				boundFunction(self.doRemoveAutoinstallNow, path, action),
				MessageBox,
				_("Do you really want to delete the generic 'autoinstall' file too?\n\nOn shared storage, it may belong to another receiver!"),
				type=MessageBox.TYPE_YESNO,
				default=False,
				picon=MessageBox.TYPE_ERROR
			)
			return

		if action == "deleteCurrent":
			files = (macPath,)
			if linkMatchesMac or brokenLink:
				files += (autoinstallPath,)
		elif action == "deleteGeneric":
			files = (autoinstallPath,)
		elif action == "deleteBoth":
			files = (macPath, autoinstallPath)
		else:
			return

		for filename in files:
			try:
				os.unlink(filename)
			except Exception as ex:
				print("Failed to delete '%s': %s" % (os.path.basename(filename), ex))

	def doepgcachebackup(self):
		enigma.eEPGCache.getInstance().save()

	def appClosed(self, retval):
		print("[AutoBackup] done:", retval)

		if self.archivePending:
			self.archivePending = False
			if not retval:
				self.doArchiveCurrentBackup()
				return

		if self.archiveCreator is not None:
			archiveCreator = self.archiveCreator
			self.archiveCreator = None
			if not retval:
				archiveCreator.removeOldArchives()
				plugin.setLastBackupTime()

		txt = _("Failed") if retval else _("Done")
		self.showOutput()
		self.data = ''
		self["statusbar"].setText(txt)
		self.changedWhere(self.cfgwhere)

	def dataAvail(self, s):
		if isinstance(s, bytes):
			s = s.decode("utf-8", errors="replace")
		print("[AutoBackup]", s.strip())
		self["status"].appendText(s)

		plugin.writeLog(s, "a")

	def doRestore(self):
		backupDir = os.path.join(self.cfgwhere.value, "backup")

		if self.activeArchiveFilters is None:
			self.activeArchiveFilters = ARCHIVE_FILTERS_RESTORE.copy()

		if ENABLE_EXPERIMENTAL_FEATURES:
			archives, elapsed, checked = getArchivesTimed(backupDir, self.activeArchiveFilters)
			if checked:
				timingText = _("\n\nChecked %s archives\n") % colorText(COLOR_LIGHTGREEN, "%d" % checked)
			else:
				timingText = "\n\n"
			if elapsed is not None:
				timingText += _("Search time: %s") % colorText(COLOR_LIGHTGREEN, "%.3f s" % elapsed)
		else:
			archives = getArchives(backupDir, self.activeArchiveFilters)

		if archives:
			filename, backupFile = archives[0][:2]
			text = filename[:-7] if filename.endswith(".tar.gz") else filename
			if not text.startswith("backup."):
				parts = text.split(".")
				if len(parts) > 1:
					parts[1] = colorText(COLOR_GREEN,"-mac-")
					text = ".".join(parts)
			if ENABLE_EXPERIMENTAL_FEATURES:
				text += timingText

			# for display details of the found archive - enable this 3 lines
			# archiveInfo, files, dummy = readArchiveDetails(backupFile)
			# details, dummy = formatArchiveDetails(archiveInfo, files)
			# text += "\n\n" + details

			backupList = [("%s %s %s" % (self.cfgwhere.value, _("from: "), getArchiveDateTime(filename)), True)]
			self.session.openWithCallback(
				boundFunction(self.doRestorePreviousConfirmed, backupFile, backupDir),
				MessageBox,
				_("Restore this backup archive and restart?\n\n\n\n%s") % text,
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

	def prepareCommand(self):
		if not self.cfgwhere.value:
			return False
		self.data = ''
		self.showOutput()
		self["statusbar"].setText(_('Running...'))
		return True

	def executeCommand(self, cmd):
		result = self.container.execute(cmd)
		if result:
			print("[AutoBackup] failed to execute")
			self.showOutput()
		return result

	def doArchiveCurrentBackup(self):
		if not self.prepareCommand():
			return
		archive = ArchiveCreator(self.cfgwhere.value)
		backupDir = os.path.join(self.cfgwhere.value, "backup")
		archive.createInfo(backupDir)
		self.archiveCreator = archive
		if self.executeCommand(archive.buildArchiveCommand(backupDir, removeInfo=True)):
			self.archiveCreator = None

	def doArchiveCurrentSettings(self):
		if not self.prepareCommand():
			return

		plugin.prepareBackup()

		archive = ArchiveCreator(self.cfgwhere.value)
		cmd = archive.buildCurrentSettingsCommand()
		self.archiveCreator = archive
		self.container.appClosed.remove(self.appClosed)
		self.container.appClosed.append(self.archiveCurrentSettingsClosed)
		if self.executeCommand(cmd):
			self.archiveCreator = None
			self.container.appClosed.remove(self.archiveCurrentSettingsClosed)
			self.container.appClosed.append(self.appClosed)

	def archiveCurrentSettingsClosed(self, retval):
		self.container.appClosed.remove(self.archiveCurrentSettingsClosed)
		self.container.appClosed.append(self.appClosed)

		archiveCreator = self.archiveCreator
		self.archiveCreator = None
		if not retval:
			if archiveCreator is not None:
				archiveCreator.removeOldArchives()
			self["statusbar"].setText(_("Done"))
			self["status"].setText(_("Backup archive created"))
		else:
			self["statusbar"].setText(_("Failed"))
			self["status"].setText(_("Archive creation failed"))

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

		plugin.writeLog("Restore:\n", "w")

		self.data = ''
		self.showOutput()
		self["statusbar"].setText(_('Running...'))

		cmd = 'tar -tzf "%s" && tar -xzf "%s" -C "%s" && /etc/init.d/settings-restore.sh %s && killall -9 enigma2' % (backupFile, backupFile, backupDir, self.cfgwhere.value)

		# Alternative restore without extracting symlinks:
		# cmd = (
		#	'tar -tzf "%s" && '
		#	'tar -xzf "%s" -C "%s" '
		#	'--exclude="PLi-AutoBackup.tar.gz" '
		#	'--exclude="autoinstall" '
		#	'&& /etc/init.d/settings-restore.sh %s && killall -9 enigma2'
		#	) % (backupFile, backupFile, backupDir, self.cfgwhere.value)

		if self.container.execute(cmd):
			print("[AutoBackup] failed to execute")
		self.showOutput()


class ArchiveCreator:
	def __init__(self, destination):
		self.destination = destination
		self.tmpBackupDir = "/tmp/autobackup.%d" % os.getpid()
		self.mac = getMacAddress()
		self.hostname = getHostName()
		self.image = getImageShortName()
		self.slot = getCurrentSlot()
		self.archiveName = None

	def createInfo(self, backupDir):
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

	def prepareArchive(self):
		if os.path.isdir(self.tmpBackupDir):
			shutil.rmtree(self.tmpBackupDir)

		backupDir = os.path.join(self.tmpBackupDir, "backup")
		os.makedirs(backupDir)
		self.createInfo(backupDir)

	def buildArchiveCommand(self, backupDir, removeInfo=False):
		slotSuffix = ""
		if self.slot is not None:
			slotSuffix = ".slot%02d" % self.slot

		removeInfoCommand = ""
		if removeInfo:
			removeInfoCommand = 'rm -f "%s/autobackup.info"' % backupDir
			if not config.plugins.autobackup.autoinstall.value:
				removeInfoCommand += ' "%s/autoinstall%s" "%s/autoinstall"' % (
					backupDir,
					self.mac,
					backupDir
				)
			removeInfoCommand += "; "

		backupFiles = "autobackup.info PLi-AutoBackup%s.tar.gz autoinstall%s" % (
			self.mac,
			self.mac
		)
		backupLinks = (
			'$(for link in PLi-AutoBackup.tar.gz autoinstall; do '
			'[ -L "$link" ] && echo "$link"; '
			'done)'
		)

		timestamp = strftime("%Y%m%d_%H%M")
		self.archiveName = "%s.%s.%s.%s%s.tar.gz" % (
			timestamp,
			self.mac,
			self.hostname,
			self.image,
			slotSuffix
		)

		return (
			'cd "%s" && '
			'tar -czf "%s/backup/%s" %s %s; '
			'archiveStatus=$?; '
			'%s'
			'rm -rf "%s"; '
			'exit $archiveStatus'
		) % (
			backupDir,
			self.destination,
			self.archiveName,
			backupFiles,
			backupLinks,
			removeInfoCommand,
			self.tmpBackupDir
		)

	def buildCurrentSettingsCommand(self):
		self.prepareArchive()

		return '%s && %s' % (
			plugin.backupCommand(self.tmpBackupDir, fullArchive=True),
			self.buildArchiveCommand(os.path.join(self.tmpBackupDir, "backup"))
		)

	def removeOldArchives(self):
		keepArchives = config.plugins.autobackup.keeparchives.value
		if keepArchives == "all" or self.archiveName is None:
			return

		match = re.match(r"^\d{8}_\d{4}(\..+)$", self.archiveName)
		if not match:
			return

		archivePattern = re.compile(
			r"^\d{8}_\d{4}%s$" % re.escape(match.group(1))
		)
		backupDir = os.path.join(self.destination, "backup")

		try:
			archives = [
				entry.name
				for entry in os.scandir(backupDir)
				if archivePattern.match(entry.name)
			]
		except Exception as ex:
			print("[AutoBackup] Failed to list backup archives: %s" % ex)
			return

		archives.sort(reverse=True)
		for archiveName in archives[int(keepArchives):]:
			archiveFile = os.path.join(backupDir, archiveName)
			try:
				os.remove(archiveFile)
				print("[AutoBackup] Removed old backup archive: %s" % archiveFile)
			except Exception as ex:
				print(
					"[AutoBackup] Failed to remove old backup archive %s: %s" %
					(archiveFile, ex)
				)


def getRequiredArchiveInfo(filters):
	return [key for key in ("mac", "hostname", "image", "enigma", "slot") if filters[key]]


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
		with tarfile.open(archiveFile, "r|gz") as tar:
			for member in tar:
				if member.name == "autobackup.info":
					f = tar.extractfile(member)
					if f:
						for line in f.read().decode("utf-8").splitlines():
							if "=" not in line:
								continue

							key, value = line.split("=", 1)
							key = key.strip()
							value = value.strip()

							if key == "image":
								value = getImageShortName(value)
							elif key == "enigma":
								value = getEnigmaName(value)

							info[key] = value

					# Only MAC can be obtained from another archive member.
					if "mac" not in required or "mac" in info:
						break

				elif "mac" in required and "mac" not in info:
					base = os.path.basename(member.name)
					match = re.search(r"([0-9a-fA-F]{12})\.tar\.gz$", base)

					if match:
						info["mac"] = match.group(1).lower()
						if all(key in info for key in required):
							break

	except Exception as ex:
		print("[AutoBackup] Failed to read archive information from %s: %s" % (archiveFile, ex))

	return info

def readArchiveDetails(backupFile):
	archiveInfo = None
	backupMac = None
	files = []

	with tarfile.open(backupFile, "r:gz") as tar:
		for member in tar.getmembers():
			if member.name == "autobackup.info":
				f = tar.extractfile(member)
				if f:
					archiveInfo = f.read().decode("utf-8")

			if not member.issym() and not member.islnk():
				files.append((
					member.name,
					member.size
				))

			if backupMac is None:
				base = os.path.basename(member.name)
				if base.endswith(".tar.gz"):
					base = base[:-7]
				if len(base) >= 12:
					mac = base[-12:]
					if all(c in "0123456789abcdefABCDEF" for c in mac):
						backupMac = mac.lower()

	# Prefer the MAC explicitly stored in autobackup.info.
	if archiveInfo:
		for line in archiveInfo.splitlines():
			if "=" not in line:
				continue
			key, value = line.split("=", 1)
			if key.strip() == "mac":
				backupMac = value.strip().lower()
				break

	return archiveInfo, files, backupMac

def formatArchiveMacWarning(backupMac):
	currentMac = getMacAddress()
	if backupMac != currentMac:
		return _(
			"Backup was created for another receiver.\n"
			"Current receiver MAC: %s\n\n"
		) % currentMac

	return ""

def formatAutoBackupInfo(archiveInfo, mismatch=None):
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
			formatted = colorText(COLOR_RED, formatted)

		result.append(formatted)

	return "\n".join(result)


def formatArchiveDetails(archiveInfo, files):
	if archiveInfo is not None:
		mismatch = validateArchiveParameters(archiveInfo, {
			"mac": True,
			"hostname": True,
			"image": True,
			"enigma": True,
			"slot": True,
		})
		info = formatAutoBackupInfo(archiveInfo, mismatch)
	else:
		mismatch = []
		info = _("autobackup.info file is missing in archive")

	infoLines = len(info.splitlines())
	info += "\n" * max(0, 7 - infoLines)

	contents = []
	for name, size in files:
		size = padSize(size, 8)
		contents.append(
			"%s  %s" % (
				colorText(COLOR_GRAY, "%s B" % size),
				name
			)
		)

	text = (
		info +
		"\n\n" + _("Archive contents") +
		":\n" + "\n".join(sorted(contents, key=str.lower))
	)

	return text, mismatch


def mergeMissingArchiveInfo(info, fallbackInfo):
	for key, value in fallbackInfo.items():
		if key not in info:
			info[key] = value

	return info


def readArchiveInfoFile(archiveFile, filename, filters):
	required = getRequiredArchiveInfo(filters)
	info = readArchiveInfoFromTar(archiveFile, required)

	if all(key in info for key in required):
		return info

	filenameInfo = readArchiveInfoFromName(filename)
	return mergeMissingArchiveInfo(info, filenameInfo)


def archiveMatchesFilters(fullpath, filename, filters, currentBoxInfo):
		if not any(filters[key] for key in ("mac", "hostname", "image", "enigma", "slot")):
			return True

		info = readArchiveInfoFile(fullpath, filename, filters)

		if filters["mac"] and info.get("mac", "").lower() != currentBoxInfo["mac"]:
			return False

		if filters["hostname"] and info.get("hostname", "") != currentBoxInfo["hostname"]:
			return False

		if filters["image"] and info.get("image", "") != currentBoxInfo["image"]:
			return False

		if filters["enigma"] and info.get("enigma", "") != currentBoxInfo["enigma"]:
			return False


		if filters["slot"]:
			currentSlot = currentBoxInfo["slot"]
			archiveSlot = info.get("slot")

			if currentSlot is None:
				if archiveSlot:
					return False
			elif archiveSlot != "slot%d" % currentSlot:
				return False

		return True

def getArchives(backupDir, filters, stats=None):
	archives = []
	currentBoxInfo = {}

	if filters["mac"]:
		currentBoxInfo["mac"] = getMacAddress().lower()
	if filters["hostname"]:
		currentBoxInfo["hostname"] = getHostName()
	if filters["image"]:
		currentBoxInfo["image"] = getImageShortName()
	if filters["enigma"]:
		currentBoxInfo["enigma"] = getEnigmaName()
	if filters["slot"]:
		currentBoxInfo["slot"] = getCurrentSlot()

	if ENABLE_EXPERIMENTAL_FEATURES:
		if stats is not None:
			stats["checked"] = 0

	if os.path.isdir(backupDir):
		for entry in os.scandir(backupDir):
			if not entry.is_file():
				continue
			if not isArchiveName(entry.name):
				continue
			if ENABLE_EXPERIMENTAL_FEATURES:
				if stats is not None:
					stats["checked"] += 1
			if not archiveMatchesFilters(entry.path, entry.name, filters, currentBoxInfo):
				continue

			match = re.search(r"\d{8}_\d{4}", entry.name)
			sortKey = match.group(0).replace("_", "")
			archives.append((entry.name, entry.path, sortKey))

	archives.sort(key=lambda archive: archive[2], reverse=True)

	return archives


# for ENABLE_EXPERIMENTAL_FEATURES
def getArchivesTimed(backupDir, filters):
	stats = {}

	started = time()
	archives = getArchives(backupDir, filters, stats)
	elapsed = time() - started

	return archives, elapsed, stats["checked"]


class ArchiveList(Screen):
	skin = """
	<screen position="center,center" size="1180,550" title="Backup archive list">
		<ePixmap name="red"    position="0,0"   zPosition="2" size="140,40" pixmap="skin_default/buttons/red.png" transparent="1" alphatest="on" />
		<ePixmap name="green"  position="140,0" zPosition="2" size="140,40" pixmap="skin_default/buttons/green.png" transparent="1" alphatest="on" />
		<ePixmap name="yellow" position="280,0" zPosition="2" size="140,40" pixmap="skin_default/buttons/yellow.png" transparent="1" alphatest="on" />
		<ePixmap name="blue"   position="420,0" zPosition="2" size="140,40" pixmap="skin_default/buttons/blue.png" transparent="1" alphatest="on" />

		<widget source="key_red" render="Label" position="0,0" size="140,40" valign="center" halign="center" zPosition="4" foregroundColor="white" font="Regular;20" transparent="1" shadowColor="background" shadowOffset="-2,-2" />
		<widget source="key_green" render="Label" position="140,0" size="140,40" valign="center" halign="center" zPosition="4" foregroundColor="white" font="Regular;20" transparent="1" shadowColor="background" shadowOffset="-2,-2" />
		<widget source="key_yellow" render="Label" position="280,0" size="140,40" valign="center" halign="center" zPosition="4" foregroundColor="white" font="Regular;20" transparent="1" shadowColor="background" shadowOffset="-2,-2" />
		<widget source="key_blue" render="Label" position="420,0" size="140,40" valign="center" halign="center" zPosition="4" foregroundColor="white" font="Regular;20" transparent="1" shadowColor="background" shadowOffset="-2,-2" />

		<widget name="list" position="10,40" size="650,500" scrollbarMode="showOnDemand" />
		<widget name="message" position="10,40" size="650,500" font="Regular;20" halign="center" valign="center" transparent="1" />

		<widget name="preview" position="680,40" size="490,500" font="Regular;20" scrollbarMode="showOnDemand" />
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
		self.backupMac = None
		self.reverseOrder = False

		self["key_red"] = StaticText(_("Delete"))
		self["key_green"] = StaticText(_("Restore"))
		self["key_yellow"] = StaticText(_("Reverse order"))
		self["key_blue"] = StaticText(_("Filters"))
		self["list"] = MenuList([])
		self["message"] = Label("")
		self["preview"] = ScrollLabel("")
		self["list"].onSelectionChanged.append(self.selectionChanged)

		self["actions"] = ActionMap(
			["OkCancelActions", "ColorActions", "DirectionActions"],
			{
				"cancel": self.exit,
				"red": self.delete,
				"green": self.select,
				"yellow": self.reverseList,
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
		if ENABLE_EXPERIMENTAL_FEATURES:
			archives, elapsed, checked = getArchivesTimed(self.backupDir, self.archiveFilters)
		else:
			archives = getArchives(self.backupDir, self.archiveFilters)

		if self.reverseOrder:
			archives.reverse()

		self["list"].setList(archives)
		title = _("Backup archive list")
		if ENABLE_EXPERIMENTAL_FEATURES and elapsed is not None:
			if checked:
				title += " - %s / %s" % (
					colorText(COLOR_LIGHTGREEN, str(len(archives))),
					colorText(COLOR_LIGHTGREEN, str(checked))
				)
			title += " - " + colorText(COLOR_LIGHTGREEN, "%.3f s" % elapsed)
		self.setTitle(title)
		self["message"].setText("" if archives else _("No backup archives match the current filters.\n\nTry changing the filter settings."))

		self.selectionChanged()

	def reverseList(self):
		archives = list(self["list"].list)
		if not archives:
			return
		current = self["list"].getCurrent()
		archives.reverse()
		self["list"].setList(archives)
		self.reverseOrder = not self.reverseOrder
		self["key_yellow"].setText(_("Original order") if self.reverseOrder else _("Reverse order"))
		if current in archives:
			self["list"].moveToIndex(archives.index(current))

	def openFilter(self):
		self.session.openWithCallback(self.filterClosed, ArchiveFilter, self.archiveFilters)

	def filterClosed(self, filters):
		if filters is None:
			return
		if filters == self.archiveFilters:
			return

		self.archiveFilters = filters

		self.loadArchives()
		self.restoreSelection()

	def select(self):
		current = self["list"].getCurrent()
		if not current:
			return

		backupFile = current[1]

		text = _("Restore this backup archive and restart?")
		if self.backupMac != getMacAddress():
			text = _("Restore this backup archive anyway and restart?")
			text = formatArchiveMacWarning(self.backupMac) + text
		text += "\n\n" + os.path.basename(backupFile)

		self.session.openWithCallback(
			boundFunction(
				self.restoreConfirmed,
				backupFile
			),
			MessageBox,
			text,
			type=MessageBox.TYPE_YESNO,
			picon=MessageBox.TYPE_ERROR if self.backupMac != getMacAddress() else MessageBox.TYPE_YESNO,
			default=False
		)

	def restoreConfirmed(self, backupFile, answer):
		if not answer:
			return

		self.close(None)
		self.configScreen.doRestorePreviousConfirmed(
			backupFile,
			self.backupDir,
			True
		)

	def delete(self):
		current = self["list"].getCurrent()
		if not current:
			return

		self.session.openWithCallback(
			boundFunction(
				self.configScreen.doDeletePreviousConfirmed,
				current[1],
				self["list"].getSelectedIndex(),
				self
			),
			MessageBox,
			_("Do you really want to delete this backup archive?") +
			"\n\n" + os.path.basename(current[1]),
			type=MessageBox.TYPE_YESNO,
			default=False
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

		self.selectionChanged()

	def exit(self):
		self.close(None)

	def selectionChanged(self):
		current = self["list"].getCurrent()

		if not current:
			self.backupMac = None
			self["preview"].setText("")
			return

		backupFile = current[1]

		try:
			archiveInfo, files, backupMac = readArchiveDetails(backupFile)
			self.backupMac = backupMac
			details, dummy = formatArchiveDetails(archiveInfo, files)
			self["preview"].setText(details)
		except Exception as ex:
			print(
				"[AutoBackup] Failed to preview archive %s: %s" %
				(backupFile, ex)
			)
			self.backupMac = None
			self["preview"].setText(
				_("Unable to read backup archive.")
			)


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
		self.filterEnigma = ConfigYesNo(default=filters.get("enigma", False))
		self.filterSlot = ConfigYesNo(default=filters.get("slot", False))

		configList = []

		configList.append((_("Receiver MAC"), self.filterMac, _("Match the current receiver MAC address using the archive name, info file or filenames in the archive.")))
		configList.append((_("Hostname"), self.filterHostname, _("Match the current hostname using the archive name or the info file.")))
		configList.append((_("Image"), self.filterImage, _("Match the current image name using the archive name or the info file.")))
		configList.append((_("Enigma"), self.filterEnigma, _("Match the current enigma name using the archive name or the info file.")))
		configList.append((_("Slot"), self.filterSlot, _("Match the current slot number using the archive name or the info file.")))
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
			"enigma": self.filterEnigma.value,
			"slot": self.filterSlot.value,
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