# generated by wx.Glade 0.6.3 on Thu Feb 05 15:42:50 2009
# 
# Arno: please edit TopSearchPanel.xrc in some XRC editor, then generate
# code for it using wxGlade (single python file mode), and copy the
# relevant parts from it into this file, see "MAINLY GENERATED" line below.
#
# We need this procedure as there is a bug in wxPython 2.8.x on Win32 that
# cause the painting/fitting of the panel to fail. All elements wind up in
# the topleft corner. This is a wx bug as it also happens in XRCED when you
# display the panel twice.
#

import sys
import wx
import os
from traceback import print_exc

# begin wx.Glade: extracode
# end wx.Glade

from bgPanel import bgPanel
from tribler_topButton import *
from GuiUtility import GUIUtility
from Tribler.Main.Utility.utility import Utility
from Tribler.__init__ import LIBRARYNAME

DEBUG = False

class TopSearchPanel(bgPanel):
    def __init__(self, *args, **kwds):
        if DEBUG:
            print >> sys.stderr , "TopSearchPanel: __init__"
        bgPanel.__init__(self,*args,**kwds)
        self.guiUtility = GUIUtility.getInstance()
        self.utility = self.guiUtility.utility 
        self.installdir = self.utility.getPath()
        self.frame = None
        self.first = True
      
    def set_frame(self,frame):
        self.frame = frame

    def custom_init(self):
        # animated gif for search results
        ag_fname = os.path.join(self.utility.getPath(),'Tribler','Main','vwxGUI','images','5.0','search.gif')
        #self.frame.ag = wx.animate.GIFAnimationCtrl(self.frame.top_bg, -1, ag_fname, pos=(358, 38))
        self.ag = wx.animate.GIFAnimationCtrl(self.go.GetParent(), -1, ag_fname)
        #self.frame.ag.SetUseWindowBackgroundColour(False)
        vsizer = wx.BoxSizer(wx.VERTICAL)
        vsizer.AddSpacer(wx.Size(0,5))
        vsizer.Add(self.ag,0,wx.FIXED_MINSIZE,0)
        hsizer = self.go.GetContainingSizer()
        hsizer.Add(vsizer,0,wx.FIXED_MINSIZE,0)
        hsizer.Layout()             

        hide_names = [self.ag,self.newFile]
        for name in hide_names:
            name.Hide()


        # family filter
        #print >> sys.stderr , "FF" , self.utility.config.Read('family_filter', "boolean")
        if self.utility.config.Read('family_filter', "boolean"):
            self.familyfilter.SetLabel('Family Filter:ON')
        else:
            self.familyfilter.SetLabel('Family Filter:OFF')



        # binding events  
        self.searchField.Bind(wx.EVT_KEY_DOWN, self.OnSearchKeyDown)
        self.go.Bind(wx.EVT_LEFT_UP, self.OnSearchKeyDown)
        self.search_results.Bind(wx.EVT_LEFT_UP, self.OnSearchResultsPressed)
        self.settings.Bind(wx.EVT_LEFT_UP, self.viewSettings)
        self.my_files.Bind(wx.EVT_LEFT_UP, self.viewLibrary)
        self.help.Bind(wx.EVT_LEFT_UP, self.helpClick)
        self.familyfilter.Bind(wx.EVT_LEFT_UP,self.toggleFamilyFilter)
        self.sr_msg.Bind(wx.EVT_LEFT_UP, self.sr_msgClick)


    def OnSearchKeyDown(self,event):
        if DEBUG:
            print >>sys.stderr,"TopSearchPanel: OnSearchKeyDown"
        
        if event.GetEventObject().GetName() == 'text':        
            keycode = event.GetKeyCode()
        else:
            keycode = None

        if self.searchField.GetValue().strip() != '' and (keycode == wx.WXK_RETURN or event.GetEventObject().GetName() == 'search'): 
            if self.first:
                self.first=False
                               
                self.frame.pageTitlePanel.Show()
                self.tribler_logo2.Show()
                self.sharing_reputation.Show()
                self.help.Show()
                self.frame.hsizer = self.sr_indicator.GetContainingSizer()               
                self.frame.Layout() 
                self.createBackgroundImage()
                self.srgradient.Show()
                self.sr_indicator.Show()
                self.frame.standardOverview.Show()
                self.seperator.Show()
                self.familyfilter.Show()
                
            self.ag.Show() 
            self.ag.Play()
                
            # Timer to stop animation after 10 seconds. No results will come 
            # in after that.
            self.agtimer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self.OnAGTimer)
            self.agtimer.Start(10000,True) 

            self.frame.videoframe.show_videoframe()   
            self.frame.videoparentpanel.Show()            
         
            wx.CallAfter(self.frame.pagerPanel.Show)

            self.settings.SetForegroundColour((255,51,0))
            self.my_files.SetForegroundColour((255,51,0))

            self.guiUtility.guiPage = 'search_results'
            self.guiUtility.standardFilesOverview()
            
            # Arno: delay actual search so the painting is faster.
            wx.CallAfter(self.guiUtility.dosearch)
        else:
            if not keycode == wx.WXK_BACK:
                try:
                    wx.CallAfter(self.autocomplete) # Nic: to demonstrate how autocomplete might work
                except:
                    pass # don't break the input field if something with autocomplete goes awkward
            event.Skip()     # Nic: not enough into wx to know if this should stay even though we're doing someething in here now
            
    def autocomplete(self):
        """appends the most frequent completion according to
           buddycast clicklog to the current input.
           sets the appended characters to "selected" such that they are
           automatically deleted as the user continues typing"""
        input = self.searchField.GetValue()
        if len(input)>1:
            completion = self.guiUtility.complete(input)
            if completion:
                l = len(input)
                self.searchField.SetValue(input + completion)
                self.searchField.SetSelection(l,l+len(completion))

    def OnSearchResultsPressed(self, event):
        self.guiUtility.OnResultsClicked()

    def OnAGTimer(self,event):
        self.ag.Stop()
        self.ag.Hide()


    def sr_msgClick(self,event=None):
        
        if self.sr_msg.GetLabel() == 'Poor':
            title = self.utility.lang.get('sharing_reputation_information_title')
            msg = self.utility.lang.get('sharing_reputation_poor')
            
            dlg = wx.MessageDialog(None, msg, title, wx.OK|wx.ICON_WARNING)
 

            result = dlg.ShowModal()
            dlg.Destroy()



    def helpClick(self,event=None):
        title = self.utility.lang.get('sharing_reputation_information_title')
        msg = self.utility.lang.get('sharing_reputation_information_message')
            
        dlg = wx.MessageDialog(None, msg, title, wx.OK|wx.ICON_INFORMATION)
        result = dlg.ShowModal()
        dlg.Destroy()



    def viewSettings(self,event):
        self.guiUtility.settingsOverview()

    def viewLibrary(self,event):
        self.guiUtility.standardLibraryOverview()

    def toggleFamilyFilter(self,event):
        self.guiUtility.toggleFamilyFilter()


    
      
    def Bitmap(self,path,type):
        namelist = path.split("/")
        path = os.path.join(self.installdir,LIBRARYNAME,"Main","vwxGUI",*namelist)
        return wx.Bitmap(path,type)
        
    def _PostInit(self):
        if DEBUG:
            print >>sys.stderr,"TopSearchPanel: OnCreate"
            
        bgPanel._PostInit(self)
   
# MAINLY GENERATED BELOW, replace wxStaticBitmap, etc. with wx.StaticBitmap 
# and replace wx.BitMap with self.Bitmap
#
# What makes this code (either as Python or as XRC fail is the last statement:
#       self.SetSizer(object_1)
# should be
#       self.SetSizerAndFit(object_1)
# ----------------------------------------------------------------------------------------          
        
        #self.files_friends = wx.StaticBitmap(self, -1, self.Bitmap("images/5.0/search_files.png", wx.BITMAP_TYPE_ANY))
        self.files_friends = wx.StaticText(self, -1, "Search Files") 
        self.searchField = wx.TextCtrl(self, -1, "", style=wx.TE_PROCESS_ENTER)
        self.go = tribler_topButton(self,-1,name = 'search')
        self.familyfilter = wx.StaticText(self, -1, "Family Filter:")
        self.search_results = wx.StaticText(self, -1, "")
        self.sharing_reputation = wx.StaticText(self, -1, "Sharing Reputation: ") 
        self.sr_msg = wx.StaticText(self, -1, "") 
        #self.sharing_reputation = wx.StaticBitmap(self, -1, self.Bitmap("images/5.0/sharing_reputation.png", wx.BITMAP_TYPE_ANY))
        self.srgradient = wx.StaticBitmap(self, -1, self.Bitmap("images/5.0/SRgradient_new.png", wx.BITMAP_TYPE_ANY))
        self.help = wx.StaticBitmap(self, -1, self.Bitmap("images/5.0/help.png", wx.BITMAP_TYPE_ANY))
        self.sr_indicator = wx.StaticBitmap(self, -1, self.Bitmap("images/5.0/SRind.png", wx.BITMAP_TYPE_ANY))
        self.settings = wx.StaticText(self, -1, "Settings")
        self.newFile = wx.StaticBitmap(self, -1, self.Bitmap("images/5.0/iconSaved.png", wx.BITMAP_TYPE_ANY))
        self.seperator = wx.StaticBitmap(self, -1, self.Bitmap("images/5.0/seperator.png", wx.BITMAP_TYPE_ANY))
        self.my_files = wx.StaticText(self, -1, "My Files")
        self.tribler_logo2 = wx.StaticBitmap(self, -1, self.Bitmap("images/logo4video2.png", wx.BITMAP_TYPE_ANY))
        ##self.left = wx.StaticBitmap(self,-1, self.Bitmap("images/5.0/left.png", wx.BITMAP_TYPE_ANY))
        ##self.right = wx.StaticBitmap(self,-1, self.Bitmap("images/5.0/right.png", wx.BITMAP_TYPE_ANY))
        self.total_down = wx.StaticText(self, -1, "0B Down")
        self.total_up = wx.StaticText(self, -1, "0B Up")
        

        self.__set_properties()
        self.__do_layout()
        # end wx.Glade

        # OUR CODE
        self.custom_init()

    def __set_properties(self):
        # begin wx.Glade: MyPanel.__set_properties
        self.SetSize((1000,90))
        self.SetBackgroundColour(wx.Colour(255, 255, 255))
        self.searchField.SetMinSize((320,23))
        self.searchField.SetForegroundColour(wx.Colour(0, 0, 0))
        self.searchField.SetFont(wx.Font(10, wx.MODERN, wx.NORMAL, wx.NORMAL, 0, "Verdana"))
        self.searchField.SetFocus()
        self.go.SetMinSize((50,24))
        self.go.SetBackgroundColour(wx.Colour(255, 255, 255))
        self.familyfilter.SetMinSize((100,15))
        self.familyfilter.SetFont(wx.Font(8, wx.SWISS, wx.NORMAL, wx.NORMAL, 0, "UTF-8"))
        self.search_results.SetMinSize((100,10))
        self.search_results.SetFont(wx.Font(10, wx.DEFAULT, wx.NORMAL, wx.NORMAL, 0, ""))
        self.settings.SetMinSize((50,15))
        self.settings.SetForegroundColour(wx.Colour(255, 51, 0))
        self.settings.SetFont(wx.Font(8, wx.SWISS, wx.NORMAL, wx.NORMAL, 0, "UTF-8"))
        self.my_files.SetMinSize((50,15))
        self.my_files.SetForegroundColour(wx.Colour(255, 51, 0))
        self.my_files.SetFont(wx.Font(8, wx.SWISS, wx.NORMAL, wx.NORMAL, 0, "UTF-8"))
        self.total_down.SetFont(wx.Font(7, wx.SWISS, wx.NORMAL, wx.NORMAL, 0, "UTF-8"))
        self.total_up.SetFont(wx.Font(7, wx.SWISS, wx.NORMAL, wx.NORMAL, 0, "UTF-8"))
        self.sharing_reputation.SetFont(wx.Font(8, wx.SWISS, wx.NORMAL, wx.BOLD, 0, "Nimbus Sans L"))
        self.sr_msg.SetFont(wx.Font(8, wx.SWISS, wx.NORMAL, wx.BOLD, 0, "Nimbus Sans L"))
        self.files_friends.SetFont(wx.Font(8, wx.SWISS, wx.NORMAL, wx.BOLD, 0, "Nimbus Sans L"))


        # end wx.Glade


    def __do_layout(self):
        # begin wx.Glade: MyPanel.__do_layout
        object_1 = wx.BoxSizer(wx.HORIZONTAL)
        object_12 = wx.BoxSizer(wx.VERTICAL)
        object_11 = wx.BoxSizer(wx.VERTICAL)
        object_10 = wx.BoxSizer(wx.VERTICAL)
        object_2 = wx.BoxSizer(wx.HORIZONTAL)
        object_7 = wx.BoxSizer(wx.VERTICAL)
        object_14 = wx.BoxSizer(wx.HORIZONTAL)
        object_9 = wx.BoxSizer(wx.HORIZONTAL)
        object_8 = wx.BoxSizer(wx.HORIZONTAL)
        object_3 = wx.BoxSizer(wx.VERTICAL)
        object_5 = wx.BoxSizer(wx.HORIZONTAL)
        object_6 = wx.BoxSizer(wx.VERTICAL)
        object_4 = wx.BoxSizer(wx.HORIZONTAL)
        object_13 = wx.BoxSizer(wx.HORIZONTAL)
        object_1.Add((10, 0), 0, 0, 0)
        object_3.Add((0, 20), 0, 0, 0)
        object_3.Add(self.files_friends, 0, 0, 0)
        object_3.Add((0, 5), 0, 0, 0)
        object_4.Add(self.searchField, 0, wx.LEFT, -2)
        object_4.Add((2, 0), 0, 0, 0)
        object_4.Add(self.go, 0, 0, 0)
        object_4.Add((2,0), 0, 0, 0)
        object_3.Add(object_4, 0, 0, 0)
        object_6.Add((0, 0), 0, 0, 0)
        object_6.Add(self.familyfilter, 0, 0, 0)
        object_5.Add(object_6, 0, 0, 0)
        object_5.Add((120, 0), 1, 0, 0)
        object_5.Add(self.search_results, 0, wx.ALIGN_RIGHT, 0)
        object_3.Add(object_5, 0, 0, 0)
        object_2.Add(object_3, 0, wx.EXPAND, 0)
        object_2.Add((40, 0), 0, 0, 0)
        object_7.Add((0, 20), 0, 0, 0)
        object_7.Add(object_14, 0, 0, 0)
        object_14.Add(self.sharing_reputation, 0, 0, 0)
        object_14.Add(self.sr_msg, 0, 0, 0)
        object_7.Add((0, 5), 0, 0, 0)
        object_8.Add(self.srgradient, 0, 0, 0)
        object_8.Add((5, 0), 0, 0, 0)
        object_8.Add(self.help, 0, 0, 0)
        object_7.Add(object_8, 0, 0, 0)
        object_7.Add((0, 5), 0, 0, 0)
        object_9.Add((50, 0), 0, 0, 0)
        object_9.Add(self.sr_indicator, 0, wx.TOP, -17)
        object_7.Add(object_9, 0, 0, 0)
        object_7.Add(object_13, 0, 0, 0)
        object_2.Add(object_7, 0, wx.EXPAND, 0)
        object_1.Add(object_2, 1, wx.EXPAND, 0)
        object_1.Add((7, 0), 0, 0, 0) # Arno: set to 100 to get right view on win32
        object_10.Add((0, 20), 0, 0, 0)
        object_10.Add(self.settings, 0, 0, 0)
        object_10.Add((0, 0), 0, 0, 0)
        object_1.Add(object_10, 0, 0, 0)
        object_1.Add((7, 0), 0, 0, 0)
        object_11.Add((0, 20), 0, 0, 0)
        object_11.Add(self.seperator, 0, 0, 0)
        object_1.Add(object_11, 0, 0, 0)
        object_1.Add((7, 0), 0, 0, 0)
        object_12.Add((0, 20), 0, 0, 0)
        object_12.Add(self.my_files, 0, 0, 0)
        object_12.Add((0, 0), 0, 0, 0)
        object_12.Add(self.newFile, 0, 0, 0)
        object_1.Add(object_12, 0, 0, 0)
        object_1.Add((7, 0), 0, 0, 0)
        object_1.Add(self.tribler_logo2, 0, 0, 0)
        object_1.Add((10, 0), 0, 0, 0)
        ##object_13.Add(self.left, 0, 0, 0)
        object_13.Add((0, 0), 0, 0, 0)
        object_13.Add(self.total_down, 0, 0, 0)
        object_13.Add((8, 0), 0, 0, 0)
        object_13.Add(self.total_up, 0, 0, 0)
        object_13.Add((0, 0), 0, 0, 0)
        ##object_13.Add(self.right, 0, 0, 0)
        
        # OUR CODE  ARNO50: Check diff in defs
        if sys.platform == 'win32':
            self.SetSizerAndFit(object_1)
        else:
            self.SetSizer(object_1)
        # end wx.Glade

# end of class MyPanel

