# Written by Niels Zeilemaker
# see LICENSE.txt for license information

import wx
import os

from Tribler.Main.Dialogs.SaveAs import SaveAs
from Tribler.Main.globals import DefaultDownloadStartupConfig
from Tribler.Main.vwxGUI.tribler_topButton import _set_font
from Tribler.Main.Dialogs.CreateTorrent import CreateTorrent
from Tribler.Main.vwxGUI.GuiUtility import GUIUtility

class AddTorrent(wx.Dialog):
    def __init__(self, parent, frame, libraryTorrents = None):
        wx.Dialog.__init__(self, parent, -1, 'Add an external .torrent', size=(500,200))
        
        self.frame = frame
        self.guiutility = GUIUtility.getInstance()
        self.toChannel = libraryTorrents != None
        self.defaultDLConfig = DefaultDownloadStartupConfig.getInstance()
        
        vSizer = wx.BoxSizer(wx.VERTICAL)
        
        firstLine = wx.StaticText(self, -1, 'Please use one of the provided methods to import an external .torrent')
        vSizer.Add(firstLine, 0, wx.EXPAND|wx.BOTTOM, 3)
        vSizer.AddSpacer((-1, 25))
        
        header = wx.StaticText(self, -1, 'Browse for local .torrent file or files')
        _set_font(header, fontweight=wx.FONTWEIGHT_BOLD)
        vSizer.Add(header, 0, wx.EXPAND|wx.BOTTOM, 3)
        vSizer.Add(wx.StaticText(self, -1, 'Use this option if you have downloaded a .torrent manually'), 0, wx.BOTTOM, 3)
        
        browseButton = wx.Button(self, -1, 'Browse')
        browseButton.Bind(wx.EVT_BUTTON, self.OnBrowse)
        
        browseDirectory = wx.Button(self, -1, 'Browse for Directory')
        browseDirectory.Bind(wx.EVT_BUTTON, self.OnBrowseDir)
        
        hSizer = wx.BoxSizer(wx.HORIZONTAL)
        hSizer.Add(browseButton, 0, wx.RIGHT, 3)
        hSizer.Add(browseDirectory)
        vSizer.Add(hSizer, 0, wx.ALIGN_RIGHT|wx.BOTTOM, 3)
        vSizer.Add(wx.StaticLine(self, -1), 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 10)
        
        header = wx.StaticText(self, -1, 'Url')
        _set_font(header, fontweight=wx.FONTWEIGHT_BOLD)
        vSizer.Add(header, 0, wx.EXPAND|wx.BOTTOM|wx.TOP, 3)
        vSizer.Add(wx.StaticText(self, -1, 'This could either be a direct http-link (starting with http://), or a magnet link'), 0, wx.BOTTOM, 3)
        
        hSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.magnet = wx.TextCtrl(self, -1)
        hSizer.Add(self.magnet, 1, wx.ALIGN_CENTER_VERTICAL)
        linkButton = wx.Button(self, -1, "Add")
        linkButton.Bind(wx.EVT_BUTTON, self.OnAdd)
        hSizer.Add(linkButton, 0, wx.LEFT, 3)
        vSizer.Add(hSizer, 0 , wx.EXPAND|wx.BOTTOM, 3)
        
        vSizer.Add(wx.StaticLine(self, -1), 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 10)
        if libraryTorrents != None:
            if len(libraryTorrents) > 0:
                header = wx.StaticText(self, -1, 'Choose one from you library')
                _set_font(header, fontweight=wx.FONTWEIGHT_BOLD)
                vSizer.Add(header, 0, wx.EXPAND|wx.BOTTOM|wx.TOP, 3)
                
                torrentNames = [torrent.name for torrent in libraryTorrents]
                
                hSizer = wx.BoxSizer(wx.HORIZONTAL)
                self.libraryChoice = wx.Choice(self, -1, choices=torrentNames)
                self.libraryChoice.torrents = libraryTorrents
                hSizer.Add(self.libraryChoice, 1, wx.ALIGN_CENTER_VERTICAL)
                
                linkButton = wx.Button(self, -1, "Add")
                linkButton.Bind(wx.EVT_BUTTON, self.OnLibrary)
                
                hSizer.Add(linkButton, 0, wx.LEFT, 3)
                vSizer.Add(hSizer, 0 , wx.EXPAND|wx.BOTTOM, 3)
            
            vSizer.Add(wx.StaticLine(self, -1), 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 10)
            header = wx.StaticText(self, -1, 'Create your own .torrents')
            _set_font(header, fontweight=wx.FONTWEIGHT_BOLD)
            vSizer.Add(header, 0, wx.EXPAND|wx.BOTTOM|wx.TOP, 3)
            vSizer.Add(wx.StaticText(self, -1, 'Using your own local files'), 0, wx.BOTTOM, 3)
            
            create = wx.Button(self, -1, 'Create')
            create.Bind(wx.EVT_BUTTON, self.OnCreate)
            vSizer.Add(create, 0, wx.ALIGN_RIGHT|wx.BOTTOM, 3)
            
            self.choose = None
            
        else:
            self.choose = wx.CheckBox(self, -1, "Let me choose a downloadlocation for these torrents")
            self.choose.SetValue(self.defaultDLConfig.get_show_saveas())
            vSizer.Add(self.choose, 0, wx.EXPAND|wx.TOP|wx.BOTTOM, 3)
        
        sizer = wx.BoxSizer()
        sizer.Add(vSizer, 1, wx.EXPAND|wx.ALL, 10)
        self.SetSizerAndFit(sizer)
        
    def OnAdd(self, event):
        input = self.magnet.GetValue().strip()
        if input.startswith("http://"):
            destdir = self.defaultDLConfig.get_dest_dir()
            if self.choose and self.choose.IsChecked():
                destdir = self._GetDestPath()
                if not destdir:
                    return
                
            if self.frame.startDownloadFromUrl(str(input), destdir):
                self.EndModal(wx.ID_OK)
            
        elif input.startswith("magnet:"):
            destdir = self.defaultDLConfig.get_dest_dir()
            if self.choose and self.choose.IsChecked():
                destdir = self._GetDestPath()
                if not destdir:
                    return
            
            if self.frame.startDownloadFromMagnet(str(input), destdir):
                self.EndModal(wx.ID_OK)
                
    def OnLibrary(self, event):
        selection = self.libraryChoice.GetCurrentSelection()
        if selection >= 0:
            torrent = self.libraryChoice.torrents[selection]
            
            if self.frame.startDownloadFromTorrent(torrent):
                self.EndModal(wx.ID_OK)
        
    def OnBrowse(self, event):
        dlg = wx.FileDialog(None, "Please select the .torrent file(s).", wildcard = "torrent (*.torrent)|*.torrent", style = wx.FD_OPEN|wx.FD_MULTIPLE)
        
        path = DefaultDownloadStartupConfig.getInstance().get_dest_dir() + os.sep
        dlg.SetPath(path)
        
        if dlg.ShowModal() == wx.ID_OK:
            filenames = dlg.GetPaths()
            dlg.Destroy()
            
            destdir = self.defaultDLConfig.get_dest_dir()
            if self.choose and self.choose.IsChecked():
                destdir = self._GetDestPath()
                if not destdir:
                    return
            
            if getattr(self.frame, 'startDownloads', False):
                self.frame.startDownloads(filenames, fixtorrent = True, destdir = destdir)
            else:
                for filename in filenames:
                    self.frame.startDownload(filename, fixtorrent = True, destdir = destdir)
                
            self.EndModal(wx.ID_OK)
        else:
            dlg.Destroy()
    
    def OnBrowseDir(self, event):
        dlg = wx.DirDialog(self, "Please select a directory contain the .torrent files", style = wx.wx.DD_DIR_MUST_EXIST)
        
        path = DefaultDownloadStartupConfig.getInstance().get_dest_dir() + os.sep
        dlg.SetPath(path)
        
        if dlg.ShowModal() == wx.ID_OK and os.path.isdir(dlg.GetPath()):
            filenames = []
            files = os.listdir(dlg.GetPath())
            
            for file in files:
                if file.endswith('.torrent'):
                    filenames.append(os.path.join(dlg.GetPath(), file))
            
            cancel = False
            if len(filenames) > 10:
                warning = wx.MessageDialog(self, "This will add %d .torrents, are you sure?"%len(filenames), "Please confirm Add", wx.OK|wx.CANCEL|wx.ICON_WARNING)
                if warning.ShowModal() != wx.ID_OK:
                    cancel = True
                    
                warning.Destroy()
                
            if not cancel:
                destdir = self.defaultDLConfig.get_dest_dir()
                if self.choose and self.choose.IsChecked():
                    destdir = self._GetDestPath()
                    if not destdir:
                        return
                    
                if getattr(self.frame, 'startDownloads', False):
                    self.frame.startDownloads(filenames, fixtorrent = True, destdir = destdir)
                else:
                    for filename in filenames:
                        self.frame.startDownload(filename, fixtorrent = True, destdir = destdir)
            
            dlg.Destroy()
            self.EndModal(wx.ID_OK)
            
        dlg.Destroy()
    
    def OnCreate(self, event):
        configfile = os.path.join(self.guiutility.utility.session.get_state_dir(), 'recent_trackers')
        trackers = self.guiutility.channelsearch_manager.torrent_db.getPopularTrackers()
        
        dlg = CreateTorrent(self, configfile, trackers, self.toChannel)
        if dlg.ShowModal() == wx.ID_OK:
            for destdir, torrentfilename in dlg.createdTorrents:
                #Niels: important do not pass fixtorrent to startDownload, used to differentiate between created and imported torrents
                self.frame.startDownload(torrentfilename = torrentfilename, destdir = destdir)
            
            dlg.Destroy()
            self.EndModal(wx.ID_OK)
            
        dlg.Destroy()
    
    def _GetDestPath(self):
        dlg = SaveAs(self, None, self.defaultDLConfig.get_dest_dir(), os.path.join(self.frame.utility.session.get_state_dir(), 'recent_download_history'))
        id = dlg.ShowModal()
        
        if id == wx.ID_OK:
            destdir = dlg.GetPath()
        else:
            destdir = None
        dlg.Destroy()
        return destdir