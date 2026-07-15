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

FRIENDLY = {
	"/media/hdd": _("Harddisk"),
	"/media/usb": _("USB"),
	"/media/cf": _("CF"),
	"/media/mmc1": _("SD"),
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
	if image is None:
		image = about.getImageTypeString()

	parts = image.split()
	if len(parts) == 3:
		version = parts[1].lower()
		major, minor = parts[2].split(".", 1)
		return "%s%02d%02d" % (version.lower(), int(major), int(minor))
	elif len(parts) == 2:
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


def isArchiveName(filename):
	return filename.endswith(".tar.gz") and (
		filename.startswith("backup.") or
		re.match(r"^[0-9a-fA-F]{12}\.", filename) or
		re.match(r"^\d{8}_\d{4}\.", filename)
	)


class Config(ConfigListScreen, Screen):
	skin = """
<screen position="center,center" size="560,400" title="AutoBackup Configuration" >
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
	<widget name="status" position="10,280" size="540,130" font="Console;14" />

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
		cfg = config.plugins.autobackup
		choices = getLocationChoices()
		if choices:
			currentwhere = cfg.where.value
			defaultchoice = choices[0][0]
			for k, v in choices:
				if k == currentwhere:
					defaultchoice = k
					break
		else:
			defaultchoice = ""
			choices = [("", _("Nowhere"))]
		self.cfgwhere = ConfigSelection(default=defaultchoice, choices=choices)
		configList = [
			getConfigListEntry(_("Backup location"), self.cfgwhere),
			getConfigListEntry(_("Daily automatic backup"), cfg.enabled),
			getConfigListEntry(_("Automatic start time"), cfg.wakeup),
			getConfigListEntry(_("Create Autoinstall"), cfg.autoinstall),
			getConfigListEntry(_("EPG cache backup"), cfg.epgcache),
			getConfigListEntry(_("Save previous backup"), cfg.prevbackup),
			]
		ConfigListScreen.__init__(self, configList, session=session, on_change=self.changedEntry)
		self["key_red"] = Button(_("Cancel"))
		self["key_green"] = Button(_("Save"))
		self["key_yellow"] = Button(_("Manual"))
		self["key_blue"] = Button(_("Restore"))
		self["key_menu"] = StaticText(_("MENU"))
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
		self.cfgwhere.addNotifier(self.changedWhere)
		self.onClose.append(self.__onClose)
		self.setTitle(_("AutoBackup Configuration"))

		self.archiveFilters = {
			"mac": True,
			"hostname": False,
			"image": False,
			"slot": False,
			"alphabetical": False,
		}

	# for summary:
	def changedEntry(self):
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
			(_("Restore previous backup"), self.doRestorePrevious, _("Restore settings from a selected archive. MAC address is verified, archive is extracted and settings are restored.")),
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

		# remove existing autobackup.info if present.
		infoFile = os.path.join(self.cfgwhere.value, "backup", "autobackup.info")
		try:
			os.remove(infoFile)
		except OSError:
			pass

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
			self.showOutput()

	def dorestore(self):
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

	def doRestorePrevious(self):
		backupDir = os.path.join(self.cfgwhere.value, "backup")
		self.session.openWithCallback(self.doRestorePreviousNow, ArchiveList, backupDir, self.archiveFilters)

	def doRestorePreviousNow(self, result):
		if not result:
			return

		selection, self.archiveFilters = result
		backupFile = selection[1]
		backupDir = os.path.join(self.cfgwhere.value, "backup")

		currentMac = open("/sys/class/net/eth0/address").read().strip().replace(":", "").lower()
		backupMac = self.checkPreviousBackup(backupFile)

		with tarfile.open(backupFile, "r:gz") as tar:
			files = []
			for member in tar.getmembers():
				if not member.issym() and not member.islnk():
					files.append(8 * " " + member.name)
			contents = "\n".join(sorted(files, key=str.lower))

		info = self.formatAutoBackupInfo(self.readAutoBackupInfo(backupFile))

		if backupMac == currentMac:
			choices = [
				(_("Cancel"), "cancel"),
				(_("Restore settings now"), "restore"),
				(_("Delete this archive"), "delete"),
			]
			warning = ""
			picon = MessageBox.TYPE_YESNO
		else:
			choices = [
				(_("Cancel"), "cancel"),
				(_("Delete this archive"), "delete"),
			]
			warning = _("This backup was created for another receiver.\nCurrent receiver MAC: %s") % currentMac + "\n\n"
			picon = MessageBox.TYPE_ERROR

		self.session.openWithCallback(
			boundFunction(self.doRestorePreviousAction, backupFile, backupDir),
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
		try:
			from Tools.Multiboot import getCurrentImage
			slot = getCurrentImage()
		except:
			slot = None

		mac = getMacAddress()
		hostname = getHostName()
		image = getImageShortName()
		slot = getCurrentSlot()

		slotSuffix = ""
		if slot is not None:
			slotSuffix = ".slot%02d" % slot

		self.data = ''
		self.showOutput()
		self["statusbar"].setText(_('Running...'))

		realBackupDir = self.cfgwhere.value
		tmpBackupDir = "/tmp/autobackup.%d" % os.getpid()

		if os.path.isdir(tmpBackupDir):
			shutil.rmtree(tmpBackupDir)

		os.makedirs(os.path.join(tmpBackupDir, "backup"))
		self.createAutoBackupInfo(os.path.join(tmpBackupDir, "backup"))

		cmd = (
			'%s && '
			'cd "%s/backup" && '
			'tar -czf "%s/backup/$(date +%%Y%%m%%d_%%H%%M).%s.%s.%s%s.tar.gz" '
			'PLi-AutoBackup*.tar.gz autoinstall* autobackup.info; '
			'rm -rf "%s"'
		) % (
			plugin.backupCommand(tmpBackupDir, fullArchive=True),
			tmpBackupDir,
			realBackupDir,
			mac,
			hostname,
			image,
			slotSuffix,
			tmpBackupDir
		)

		if self.container.execute(cmd):
			print("[AutoBackup] failed to execute")
			self.showOutput()

	def createAutoBackupInfo(self, backupDir):
		if not os.path.isdir(backupDir):
			os.makedirs(backupDir)

		infoFile = os.path.join(backupDir, "autobackup.info")
		slot = getCurrentSlot()

		with open(infoFile, "w") as f:
			f.write("mac=%s\n" % getMacAddress())
			f.write("hostname=%s\n" % getHostName())
			f.write("hardware=%s\n" % getHardwareName())
			f.write("image=%s\n" % getImageName())
			f.write("oe=%s\n" % getOEVersion())
			f.write("enigma=%s\n" % getEnigmaVersion())
			if slot is not None:
				f.write("slot=slot%d\n" % slot)


	def doRestorePreviousAction(self, backupFile, backupDir, action):
		if action == "restore":
			self.doRestorePreviousConfirmed(backupFile, backupDir, True)
		elif action == "delete":
			self.session.openWithCallback(
				boundFunction(self.doDeletePreviousConfirmed, backupFile),
				MessageBox,
				_("Do you really want delete this backup archive?") + "\n\n" + backupFile,
				type=MessageBox.TYPE_YESNO,
				default=False
			)
		else:
			self.doRestorePrevious()

	def doDeletePreviousConfirmed(self, backupFile, answer):
		if not answer:
			self.doRestorePrevious()
			return
		try:
			os.remove(backupFile)
		except Exception as ex:
			print("[AutoBackup] Failed to delete backup %s: %s" % (backupFile, ex))
			self.session.open(MessageBox, _("Failed to delete backup."), type=MessageBox.TYPE_ERROR, timeout=10)
			return
		self.doRestorePrevious()

	def formatAutoBackupInfo(self, info):
		result = []
		for line in info.splitlines():
			result.append(line.replace("=", ":\t", 1))
		return "\n".join(result)

	def doRestorePreviousConfirmed(self, backupFile, backupDir, answer):
		if not answer:
			self.doRestorePrevious()
			return

		self.data = ''
		self.showOutput()
		self["statusbar"].setText(_('Running...'))

		cmd = 'tar -tzf "%s" && tar -xzf "%s" -C "%s" && /etc/init.d/settings-restore.sh %s ; killall -9 enigma2' % (backupFile, backupFile, backupDir, self.cfgwhere.value)

		if self.container.execute(cmd):
			print("[AutoBackup] failed to execute")
		self.showOutput()

	def readAutoBackupInfo(self, backupFile):
		try:
			with tarfile.open(backupFile, "r:gz") as tar:
				f = tar.extractfile("autobackup.info")
				if f:
					return f.read().decode("utf-8")
		except Exception as ex:
			print("[AutoBackup] Failed to read autobackup.info:", ex)

		return _("No backup information available.")

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


class ArchiveList(Screen):
	skin = """
	<screen position="center,center" size="900,432" title="Backup archive list">
		<ePixmap pixmap="skin_default/buttons/red.png" position="0,0" size="140,40" alphatest="on" />
		<ePixmap pixmap="skin_default/buttons/green.png" position="140,0" size="140,40" alphatest="on" />
		<widget source="key_red" render="Label" position="0,0" zPosition="1" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="1" />
		<widget source="key_green" render="Label" position="140,0" zPosition="1" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="#1f771f" transparent="1" />
		<widget name="list" position="10,40" size="880,350" scrollbarMode="showOnDemand" />
		<ePixmap pixmap="div-h.png" position="0,392" zPosition="10" size="900,2" />
		<ePixmap pixmap="buttons/key_menu.png" position="10,394" size="52,38" alphatest="on" />
		</screen>
	"""

	def __init__(self, session, backupDir, filters):
		Screen.__init__(self, session)
		self.skinName = ["ArchiveList"]

		self.backupDir = backupDir
		self.archiveFilters = filters.copy()

		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Select"))
		self["list"] = MenuList([])

		self["actions"] = ActionMap(
			["OkCancelActions", "ColorActions", "DirectionActions", "MenuActions"],
			{
				"cancel": self.exit,
				"red": self.exit,
				"green": self.select,
				"ok": self.select,
				"up": self["list"].up,
				"down": self["list"].down,
				"left": self["list"].pageUp,
				"right": self["list"].pageDown,
				"menu": self.openFilter,
			},-1
		)

		self.loadArchives()

	def loadArchives(self):
		archives = []

		if os.path.isdir(self.backupDir):
			for filename in os.listdir(self.backupDir):
				if not isArchiveName(filename):
					continue

				fullpath = os.path.join(self.backupDir, filename)

				if not self.archiveMatchesFilter(fullpath, filename):
					continue

				try:
					st = os.stat(fullpath)
					archives.append((filename, fullpath, st.st_mtime))
				except Exception as ex:
					print("[AutoBackup] Failed to stat %s: %s" % (fullpath, ex))

		if self.archiveFilters["alphabetical"]:
			archives.sort(key=lambda archive: archive[0].lower())
		else:
			archives.sort(key=lambda archive: archive[2], reverse=True)
		self["list"].setList(archives)

		if not archives:
			self.session.open(MessageBox, _("No backup archives match the selected filters."), type=MessageBox.TYPE_INFO, timeout=5)

	def readArchiveInfo(self, archiveFile, filename):
		info = {}

		match = re.match(r"^\d{8}_\d{4}\.([0-9a-fA-F]{12})\.([^.]+)\.([^.]+)(?:\.slot(\d+))?\.tar\.gz$", filename)

		if match:
			info["mac"] = match.group(1).lower()
			info["hostname"] = match.group(2)
			info["image"] = match.group(3)
			if match.group(4) is not None:
				info["slot"] = "slot%d" % int(match.group(4))

		# if information is not available from the archive name, read it from autobackup.info.
		try:
			with tarfile.open(archiveFile, "r:gz") as tar:
				try:
					f = tar.extractfile("autobackup.info")
					if f:
						for line in f.read().decode("utf-8").splitlines():
							if "=" in line:
								key, value = line.split("=", 1)
								key = key.strip()
								value = value.strip()
								if key not in info:
									if key == "image":
										value = getImageShortName(value)
									info[key] = value
				except KeyError:
					pass

				# fallback for older archives: try to extract MAC address from filenames inside the archive
				if "mac" not in info:
					for name in tar.getnames():
						base = os.path.basename(name)
						match = re.search(r"([0-9a-fA-F]{12})\.tar\.gz$", base)
						if match:
							info["mac"] = match.group(1).lower()
							break

		except Exception as ex:
			print("[AutoBackup] Failed to read archive information from %s: %s" % (archiveFile, ex))

		return info

	def archiveMatchesFilter(self, fullpath, filename):
		if not any(self.archiveFilters.values()):
			return True

		info = self.readArchiveInfo(fullpath, filename)

		if self.archiveFilters["mac"]:
			if info.get("mac", "").lower() != getMacAddress().lower():
				return False

		if self.archiveFilters["hostname"]:
			if info.get("hostname", "") != getHostName():
				return False

		if self.archiveFilters["image"]:
			if info.get("image", "") != getImageShortName():
				return False

		if self.archiveFilters["slot"]:
			currentSlot = getCurrentSlot()
			archiveSlot = info.get("slot")

			if currentSlot is None:
				if archiveSlot:
					return False
			elif archiveSlot != "slot%d" % currentSlot:
				return False

		return True

	def openFilter(self):
		self.session.openWithCallback(
			self.filterClosed,
			ArchiveFilter,
			self.archiveFilters
		)

	def filterClosed(self, filters):
		if filters is None:
			return

		self.archiveFilters = filters
		self.loadArchives()

	def select(self):
		self.close((self["list"].getCurrent(), self.archiveFilters.copy()))

	def exit(self):
		self.close(None)

class ArchiveFilter(ConfigListScreen, Screen):
	skin = """
	<screen position="center,center" size="560,305" title="Archive filters">
		<ePixmap pixmap="skin_default/buttons/red.png" position="0,0" size="140,40" alphatest="on" />
		<ePixmap pixmap="skin_default/buttons/green.png" position="140,0" size="140,40" alphatest="on" />
		<widget source="key_red" render="Label" position="0,0" zPosition="1" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="1" />
		<widget source="key_green" render="Label" position="140,0" zPosition="1" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="#1f771f" transparent="1" />
		<widget name="config" position="10,50" size="540,200" scrollbarMode="showOnDemand" />
		<ePixmap pixmap="div-h.png" position="0,252" zPosition="10" size="900,2" />
		<widget name="description" position="10,255" size="540,46" font="Regular;20" valign="center"/>
	</screen>"""

	def __init__(self, session, filters):
		Screen.__init__(self, session)

		self.filterMac = ConfigYesNo(default=filters.get("mac", True))
		self.filterHostname = ConfigYesNo(default=filters.get("hostname", False))
		self.filterImage = ConfigYesNo(default=filters.get("image", False))
		self.filterSlot = ConfigYesNo(default=filters.get("slot", False))
		self.filterAlphabetical = ConfigYesNo(default=filters.get("alphabetical", False))

		configList = []

		configList.append((_("Current receiver MAC"), self.filterMac, _("Match the current receiver MAC address using the archive name, info file or filenames in the archive.")))
		configList.append((_("Current hostname"), self.filterHostname, _("Match the current hostname using the archive name or the info file.")))
		configList.append((_("Current image"), self.filterImage, _("Match the current image name using the archive name or the info file.")))
		configList.append((_("Current slot"), self.filterSlot, _("Match the current slot number using the archive name or the info file.")))
		configList.append((_("Sort alphabetically"), self.filterAlphabetical, _("Sort archives alphabetically instead of by creation time.")))
		ConfigListScreen.__init__(self, configList, session=session)

		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Apply"))

		self["actions"] = ActionMap(
			["OkCancelActions", "ColorActions"],
			{
				"cancel": self.cancel,
				"red": self.cancel,
				"green": self.apply,
				"ok": self.apply,
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
