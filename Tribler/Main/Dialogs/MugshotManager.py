# Written by Arno Bakker
# see LICENSE.txt for license information

try:
    import wx
    got_wx = True
except:
    got_wx = False
    
import os
import sys
from cStringIO import StringIO
from sha import sha
from shutil import copy2
from traceback import print_exc

from Tribler.Core.Utilities.utilities import show_permid_short

ICON_MAX_SIZE = 10*1024
NETW_EXT = '.jpg'
NETW_MIME_TYPE = 'image/jpeg'

ICON_MAX_DIM = 80
SMALL_ICON_MAX_DIM = 32

DEBUG = False

class MugshotManager:

    __single = None
    
    def __init__(self):
        if MugshotManager.__single:
            raise RuntimeError, "MugshotManager is singleton"
        MugshotManager.__single = self
        self.usericonpath = '' # for test suite
        self.sysiconpath = ''
        #self.register()
     

    def getInstance(*args, **kw):
        if MugshotManager.__single is None:
            MugshotManager(*args, **kw)
        return MugshotManager.__single
    getInstance = staticmethod(getInstance)
        

    def register(self,userpath,syspath):
        self.usericonpath = os.path.join(userpath,'icons')
        self.sysiconpath = os.path.join(syspath,'icons')
        self.guiImagePath = os.path.join(syspath,'Tribler', 'Main', 'vwxGUI', 'images')
        self.defaults = {}
        self.categoryThumbs = {}
	if not got_wx:
	    return
        self.defaults['filesMode'] = {}        
        self.defaults['filesMode']['DEFAULT_THUMB'] = wx.Bitmap(os.path.join(self.guiImagePath, 'defaultThumb.png'))
        self.defaults['filesMode']['BIG_DEFAULT_THUMB'] = wx.Bitmap(os.path.join(self.guiImagePath, 'defaultThumbL.png'))
        self.defaults['filesMode']['MASK_BITMAP'] = wx.Bitmap(os.path.join(self.guiImagePath, 'fileItemMask_clean.png'))
        self.defaults['filesMode']['MASK_BITMAP_BOTTOM'] = wx.Bitmap(os.path.join(self.guiImagePath, 'itemMask.png'))
        #self.defaults['filesMode']['HEART_BITMAP'] = wx.Bitmap(os.path.join(self.guiImagePath, 'heart1.png'))
        self.defaults['libraryMode'] = {}
        self.defaults['libraryMode']['DEFAULT_THUMB'] = wx.Bitmap(os.path.join(self.guiImagePath, 'defaultThumbLibrary.png'))
        self.defaults['personsMode'] = {}
        self.defaults['personsMode']['DEFAULT_THUMB'] = wx.Bitmap(os.path.join(self.guiImagePath, 'defaultThumbPeer.png'))
        self.defaults['personsMode']['DEFAULT_THUMB_SMALL'] = wx.Bitmap(os.path.join(self.guiImagePath, 'defaultThumbPeerS.png'))
        self.defaults['personsMode']['MASK_BITMAP'] = wx.Bitmap(os.path.join(self.guiImagePath, 'itemMask.png'))
        self.defaults['personsMode']['MASK_BITMAP_CLEAN'] = wx.Bitmap(os.path.join(self.guiImagePath, 'itemMask_clean.png'))
        self.defaults['personsMode']['HEART_BITMAP'] = wx.Bitmap(os.path.join(self.guiImagePath, 'heart1.png'))
        self.defaults['personsMode']['FRIEND_ONLINE_BITMAP'] = wx.Bitmap(os.path.join(self.guiImagePath, 'friend.png'))
        self.defaults['personsMode']['FRIEND_OFFLINE_BITMAP'] = wx.Bitmap(os.path.join(self.guiImagePath, 'friend_offline.png'))
        self.defaults['personsMode']['ISFRIEND_BITMAP'] = wx.Bitmap(os.path.join(self.guiImagePath, 'isFriend.png'))
        self.defaults['personsMode']['ISFRIEND_CLICKED_BITMAP'] = wx.Bitmap(os.path.join(self.guiImagePath, 'isFriend_clicked.png'))
        self.defaults['personsMode']['SUPERPEER_BITMAP'] = wx.Bitmap(os.path.join(self.guiImagePath, 'superpeer.png'))
        self.defaults['subscriptionsMode'] = {}
        self.defaults['subscriptionsMode']['DEFAULT_THUMB'] = wx.Bitmap(os.path.join(self.guiImagePath, 'favicon.png'))
        self.defaults['subscriptionsMode']['BUDDYCAST_THUMB'] = wx.Bitmap(os.path.join(self.guiImagePath, 'bcicon.png'))
        self.defaults['friendsMode'] = {}
        self.defaults['friendsMode']['DEFAULT_THUMB'] = wx.Bitmap(os.path.join(self.guiImagePath, 'defaultThumbPeerS.png'))
        self.defaults['friendsMode']['MASK_BITMAP_OVERLAY'] = wx.Bitmap(os.path.join(self.guiImagePath, 'itemMask_clean.png'))
        
        
        self.H1EXPANDEDTRUE = wx.Bitmap(os.path.join(self.guiImagePath, 'ExpandedTrue.png'))
        self.H1EXPANDEDFALSE = wx.Bitmap(os.path.join(self.guiImagePath, 'ExpandedFalse.png'))
#        self.LEFTBUTTONMENU = wx.Bitmap(os.path.join(self.guiImagePath, 'leftButtonMenu.png'))
        self.PROGRESSDUMMYICON = wx.Bitmap(os.path.join(self.guiImagePath, 'progressBar.png'))

        self.MENUICONHOME = wx.Bitmap(os.path.join(self.guiImagePath, 'MenuiconHome.png'))
        self.MENUICONSTATS= wx.Bitmap(os.path.join(self.guiImagePath, 'MenuiconStats.png'))
        self.MENUICONPROFILE= wx.Bitmap(os.path.join(self.guiImagePath, 'MenuiconProfile.png'))
        self.MENUICONALLDOWNLOADS= wx.Bitmap(os.path.join(self.guiImagePath, 'MenuiconAlldownloads.png'))
        self.MENUICONPLAYLIST= wx.Bitmap(os.path.join(self.guiImagePath, 'MenuiconPlaylist.png'))
        self.MENUICONALLFRIENDS = wx.Bitmap(os.path.join(self.guiImagePath, 'MenuiconAllfriends.png'))
        self.MENUICONALLSUBSCRIPTIONS = wx.Bitmap(os.path.join(self.guiImagePath, 'MenuiconAllsubscriptions.png'))
        self.MENUICONGROUPS = wx.Bitmap(os.path.join(self.guiImagePath, 'MenuiconGroups.png'))

        self.DOWNLOAD_BUTTON_LIBRARY = wx.Bitmap(os.path.join(self.guiImagePath, 'inLibrary.png'))
        self.DOWNLOAD_BUTTON_LIBRARY_S = wx.Bitmap(os.path.join(self.guiImagePath, 'inLibrary_clicked.png'))
        self.DOWNLOAD_BUTTON_DOWNLOAD = wx.Bitmap(os.path.join(self.guiImagePath, 'download.png'))
        self.DOWNLOAD_BUTTON_DOWNLOAD_S = wx.Bitmap(os.path.join(self.guiImagePath, 'download_clicked.png'))
        self.DOWNLOAD_BUTTON_PLAY = wx.Bitmap(os.path.join(self.guiImagePath, 'play.png'))
        self.DOWNLOAD_BUTTON_PLAY_S = wx.Bitmap(os.path.join(self.guiImagePath, 'play_clicked.png'))
        
        self.SOURCE_ICON_TRIBLER = wx.Bitmap(os.path.join(self.guiImagePath, 'icon_tribler.png'))
        self.SOURCE_ICON_YOUTUBE = wx.Bitmap(os.path.join(self.guiImagePath, 'icon_youtube.png'))
        self.SOURCE_ICON_LIVELEAK = wx.Bitmap(os.path.join(self.guiImagePath, 'icon_liveleak.png'))
        self.SOURCE_ICON_REMOTE = wx.Bitmap(os.path.join(self.guiImagePath, 'icon_remote.png'))
        
    def create_wxImageList(self,peerswpermid,setindex=False):
        """ peerswpermid is a list of dictionaries that contain the
            name and permid of a peer
        """
        if len(peerswpermid) == 0:
            return None

        # scale default to proper size
        defaultThumb = self.get_default('personsMode','DEFAULT_THUMB')
        defaultThumb = wx.BitmapFromImage(defaultThumb.ConvertToImage().Scale(SMALL_ICON_MAX_DIM,SMALL_ICON_MAX_DIM))

        list = []
        for peer in peerswpermid:
            filename = self.find_filename(peer['permid'],peer['name'])
            bm = None
            if filename is None:
                bm = defaultThumb
            else:
                try:
                    im = wx.Image(filename)
                    bm = wx.BitmapFromImage(im.Scale(SMALL_ICON_MAX_DIM,SMALL_ICON_MAX_DIM),-1)
                except:
                    try:
                        bm = defaultThumb
                    except:
                        return None
            list.append(bm)
        imgList = wx.ImageList(SMALL_ICON_MAX_DIM,SMALL_ICON_MAX_DIM)
        if imgList is None:
            return None
        for peer in peerswpermid:
            bm = list.pop(0)
            index = imgList.Add(bm)
            if setindex:
                peer['tempiconindex'] = index
        return imgList

    def find_filename(self,permid,name):
        # See if we can find it using PermID or name (old style):
        filename = self._permid2iconfilename(permid)
        if not os.access(filename,os.R_OK):
            if name is not None:
                # Old style, < 3.5.0
                try:
                    filename = os.path.join(self.usericonpath,name+NETW_EXT)
                    if not os.access(filename,os.R_OK):
                        return None
                except:
                    return None
            else:
                return None
        return filename

    def load_data(self,permid,name=None):

        if DEBUG:
            print >>sys.stderr,"mugmgr: load_data permid",show_permid_short(permid),"name",`name`

        filename = self.find_filename(permid,name)
        if filename is None:
            
            if DEBUG:
                print >>sys.stderr,"mugmgr: load_data: filename is None"
            
            return [None,None]
        try:
            f = open(filename,"rb")
            data = f.read(-1)
            f.close()
        except:
            if DEBUG:
                print >>sys.stderr,"mugmgr: load_data: Error reading"

            
            return [None,None]
        if data == '' or len(data) > ICON_MAX_SIZE:
            
            if DEBUG:
                print >>sys.stderr,"mugmgr: load_data: data 0 or too big",len(data)
 
            return [None,None]
        else:
            return [NETW_MIME_TYPE,data]


    def save_data(self,permid,type,data):
        filename = self._permid2iconfilename(permid)
        
        if DEBUG:
            print >>sys.stderr,"mugmgr: save_data: filename is",filename,type
        
        try:
            
            #f = open("maarten.bmp","wb")
            #f.write(data)
            #f.close()
            
            mi = StringIO(data)
            # St*pid wx says "No handler for image/bmp defined" while this
            # is the image handler that is guaranteed to always be there,
            # according to the docs :-(
            if type == 'image/bmp':
                im = wx.ImageFromStream(mi,wx.BITMAP_TYPE_BMP)
            else:
                im = wx.ImageFromStreamMime(mi,type)
            im.SaveMimeFile(filename,NETW_MIME_TYPE)
            f = open(filename,"wb")
            f.write(data)
            f.close()
            return True
        except:
            if DEBUG:
                print_exc()
            return False

    def copy_file(self,permid,srcfilename):
        """ srcfilename must point to a .JPG file """
        dstfilename = self._permid2iconfilename(permid)
        if DEBUG:
            print >>sys.stderr,"mugmgr: copying icon",srcfilename,"to",dstfilename
        try:
            copy2(os.path.normpath(srcfilename),dstfilename)
        except:
            if DEBUG:
                print_exc()
            pass

    def create_from_file(self,permid,srcfilename):
        """ srcfilename must point to an image file processable by wx.Image """
        dstfilename = self._permid2iconfilename(permid)
        try:
            sim = wx.Image(srcfilename).Scale(ICON_MAX_DIM,ICON_MAX_DIM)
            sim.SaveFile(dstfilename,wx.BITMAP_TYPE_JPEG)
            return True
        except:
            if DEBUG:
                print_exc()
            return False

    def load_wxBitmap(self,permid,name=None):
        filename = self.find_filename(permid,name)
        if filename is None:
            return None
        return self.load_wxBitmap_from_file(filename)

    def load_wxBitmap_from_file(self,filename):
        try:
            im = wx.Image(filename)
            bm = wx.BitmapFromImage(im.Scale(ICON_MAX_DIM,ICON_MAX_DIM),-1)
            return bm
        except:
            if DEBUG:
                print_exc()
            pass
        return None

    def _permid2iconfilename(self,permid):
        safename = sha(permid).hexdigest()
        return os.path.join(self.usericonpath, safename+NETW_EXT)


    def data2wxBitmap(self,type,data,dim=ICON_MAX_DIM):
        try:
            mi = StringIO(data)
            # St*pid wx says "No handler for image/bmp defined" while this
            # is the image handler that is guaranteed to always be there,
            # according to the docs :-(
            if type == 'image/bmp':
                im = wx.ImageFromStream(mi,wx.BITMAP_TYPE_BMP)
            else:
                im = wx.ImageFromStreamMime(mi,type)
            
            bm = wx.BitmapFromImage(im.Scale(dim,dim),-1)
            return bm
        except:
            if DEBUG:
                print_exc()
            return None


    def get_default(self,mode,name):
        return self.defaults[mode][name]
    
    def getCategoryIcon(self, mode, cat, thumbtype = 'normal', web2 = False):
        #print "**** getCategoryIcon", mode, cat, thumbtype, web2
        
        categoryConverter = {'picture':'other', 
                             'videoclips':'video',
                             'document':'other'}
        thumbType = {'normal':'defaultThumb_%s.png',
                     'large':'defaultThumbL_%s.png',
                     'small':'defaultThumbS_%s.png',
                     'icon':'icon_%s.png'
                     }
        if type(cat) == list:
            cat = cat[0]
        if web2:
            cat = 'video'
        elif cat == None:
            return None
        
        cat = cat.lower()
        
        if cat in categoryConverter:
            cat = categoryConverter[cat]
        
                
        if self.categoryThumbs.get((cat, thumbtype)):
            return self.categoryThumbs[(cat, thumbtype)]
        else:
            filename = thumbType[thumbtype] % cat
            pathname = os.path.join(self.guiImagePath, filename)
            
            #print >> sys.stderr, 'mm: Looking for category image:',pathname
            if os.path.isfile(pathname):
                bm = wx.Bitmap(pathname)
            else:
                bm = None
                print >> sys.stderr, 'mm: No thumb found for category: %s' % cat
            self.categoryThumbs[(cat, thumbtype)] = bm
            return bm
    
            
    def getDownloadButton(self, mode):
        if mode == 'play':
            return self.DOWNLOAD_BUTTON_PLAY, self.DOWNLOAD_BUTTON_PLAY_S
        elif mode == 'download':
            return self.DOWNLOAD_BUTTON_DOWNLOAD, self.DOWNLOAD_BUTTON_DOWNLOAD_S
        elif mode == 'library':
            return self.DOWNLOAD_BUTTON_LIBRARY, self.DOWNLOAD_BUTTON_LIBRARY_S
        else:
            raise Exception('No such mode')
        
    def getSourceIcon(self, source):
        if source == 'tribler':
            return self.SOURCE_ICON_TRIBLER
        elif source == 'youtube':
            return self.SOURCE_ICON_YOUTUBE
        elif source == 'liveleak':
            return self.SOURCE_ICON_LIVELEAK
        elif source == 'remote':
            return self.SOURCE_ICON_REMOTE
        elif not source:
            return None
        else:
            raise Exception('No such source')
        