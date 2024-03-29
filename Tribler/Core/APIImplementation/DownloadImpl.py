# Written by Arno Bakker
# Updated by George Milescu
# see LICENSE.txt for license information

import sys
import os
import copy
from traceback import print_exc,print_stack
from threading import RLock,Condition,Event,Thread,currentThread

from Tribler.Core.DownloadState import DownloadState
from Tribler.Core.DownloadConfig import DownloadStartupConfig
from Tribler.Core.simpledefs import *
from Tribler.Core.exceptions import *
from Tribler.Core.osutils import *
from Tribler.Core.APIImplementation.SingleDownload import SingleDownload
import Tribler.Core.APIImplementation.maketorrent as maketorrent

DEBUG = False

class DownloadImpl:
    
    def __init__(self,session,tdef):
        self.dllock = RLock()
        # just enough so error saving and get_state() works
        self.error = None
        self.sd = None # hack
        # To be able to return the progress of a stopped torrent, how far it got.
        self.progressbeforestop = 0.0
        self.filepieceranges = []
        self.pstate_for_restart = None # h4x0r to remember resumedata

        # Copy tdef, so we get an infohash
        self.session = session
        self.tdef = tdef.copy()
        self.tdef.readonly = True
        
    #
    # Creating a Download
    #
    def setup(self,dcfg=None,pstate=None,initialdlstatus=None,lmcreatedcallback=None,lmvodeventcallback=None):
        """
        Create a Download object. Used internally by Session.
        @param dcfg DownloadStartupConfig or None (in which case 
        a new DownloadConfig() is created and the result 
        becomes the runtime config of this Download.
        """
        # Called by any thread
        try:
            self.dllock.acquire() # not really needed, no other threads know of this object

            torrentdef = self.get_def()
            metainfo = torrentdef.get_metainfo()
            # H4xor this so the 'name' field is safe
            self.correctedinfoname = fix_filebasename(torrentdef.get_name_as_unicode())

            if DEBUG:
                print >>sys.stderr,"Download: setup: piece size",metainfo['info']['piece length']
            
            # See if internal tracker used
            itrackerurl = self.session.get_internal_tracker_url()
            #infohash = self.tdef.get_infohash()
            metainfo = self.tdef.get_metainfo()
            usingitracker = False
            
            if DEBUG:
                print >>sys.stderr,"Download: setup: internal tracker?",metainfo['announce'],itrackerurl,"#"
            
            if itrackerurl.endswith('/'):
                slashless = itrackerurl[:-1]
            else:
                slashless = itrackerurl
            if 'announce' in metainfo and (metainfo['announce'] == itrackerurl or metainfo['announce'] == slashless):
                usingitracker = True
            elif 'announce-list' in metainfo:
                for tier in metainfo['announce-list']:
                    if itrackerurl in tier or slashless in tier:
                        usingitracker = True
                        break
                  
            if usingitracker:
                if DEBUG:
                    print >>sys.stderr,"Download: setup: Using internal tracker"
                # Copy .torrent to state_dir/itracker so the tracker thread 
                # finds it and accepts peer registrations for it.
                #
                self.session.add_to_internal_tracker(self.tdef) 
            elif DEBUG:
                print >>sys.stderr,"Download: setup: Not using internal tracker"
            
            # Copy dlconfig, from default if not specified
            if dcfg is None:
                cdcfg = DownloadStartupConfig()
            else:
                cdcfg = dcfg
                cdcfg.updateToCurrentVersion()
            self.dlconfig = copy.copy(cdcfg.dlconfig)
            

            # Copy sessconfig into dlconfig, such that BitTornado.BT1.Connecter, etc.
            # knows whether overlay is on, etc.
            #
            for (k,v) in self.session.get_current_startup_config_copy().sessconfig.iteritems():
                self.dlconfig.setdefault(k,v)
            self.set_filepieceranges(metainfo)
    
            # Things that only exist at runtime
            self.dlruntimeconfig= {}
            self.dlruntimeconfig['max_desired_upload_rate'] = 0
            self.dlruntimeconfig['max_desired_download_rate'] = 0
    
            if DEBUG:
                print >>sys.stderr,"DownloadImpl: setup: initialdlstatus",`self.tdef.get_name_as_unicode()`,initialdlstatus

            # Closed swarms config
            self.dlconfig['cs_keys'] = self.tdef.get_cs_keys_as_ders()
            self.dlconfig['permid'] = self.session.get_permid()
            if self.dlconfig['cs_keys']:
                print >> sys.stderr,"DownloadImpl: setup: This is a closed swarm"
                #if dcfg.get_poa():
                #    self.dlconfig['poa'] = dcfg.get_poa()
                #else:
                #    print >> sys.stderr,"POA not available - seeding?"

            # Set progress
            if pstate is not None and pstate.has_key('dlstate'):
                self.progressbeforestop = pstate['dlstate'].get('progress', 0.0)
            
            # Note: initialdlstatus now only works for STOPPED
            if initialdlstatus != DLSTATUS_STOPPED:
                if pstate is None or pstate['dlstate']['status'] != DLSTATUS_STOPPED: 
                    # Also restart on STOPPED_ON_ERROR, may have been transient
                    self.create_engine_wrapper(lmcreatedcallback,pstate,lmvodeventcallback,initialdlstatus) # RePEX: propagate initialdlstatus
                
            self.pstate_for_restart = pstate
                
            self.dllock.release()
        except Exception,e:
            print_exc()
            self.set_error(e)
            self.dllock.release()

    def create_engine_wrapper(self,lmcreatedcallback,pstate,lmvodeventcallback,initialdlstatus=None):
        """ Called by any thread, assume dllock already acquired """
        if DEBUG:
            print >>sys.stderr,"Download: create_engine_wrapper()"
        
        # all thread safe
        infohash = self.get_def().get_infohash()
        metainfo = copy.deepcopy(self.get_def().get_metainfo())
        
        # H4xor this so the 'name' field is safe
        metainfo['info']['name'] = self.correctedinfoname 
        if 'name.utf-8' in metainfo['info']:
            metainfo['info']['name.utf-8'] = self.correctedinfoname
        
        multihandler = self.session.lm.multihandler
        listenport = self.session.get_listen_port()
        vapath = self.session.get_video_analyser_path()

        # Note: BT1Download is started with copy of d.dlconfig, not direct access
        kvconfig = copy.copy(self.dlconfig)
        
        # RePEX: extend kvconfig with initialdlstatus
        kvconfig['initialdlstatus'] = initialdlstatus
        
        # Define which file to DL in VOD mode
        live = self.get_def().get_live()
        vodfileindex = {
            'index':-1,
            'inpath':None,
            'bitrate':0.0,
            'live':live,
            'usercallback':None,
            'userevents': [],
            'outpath':None}

        # --- streaming settings
        if self.dlconfig['mode'] == DLMODE_VOD or self.dlconfig['video_source']:
            # video file present which is played or produced
            multi = False
            if 'files' in metainfo['info']:
                multi = True
            
            # Determine bitrate
            if multi and len(self.dlconfig['selected_files']) == 0:
                # Multi-file torrent, but no file selected
                raise VODNoFileSelectedInMultifileTorrentException() 
            
            if not multi:
                # single-file torrent
                file = self.get_def().get_name()
                idx = -1
                bitrate = self.get_def().get_bitrate()
            else:
                # multi-file torrent
                file = self.dlconfig['selected_files'][0]
                idx = self.get_def().get_index_of_file_in_files(file)
                bitrate = self.get_def().get_bitrate(file)

            # Determine MIME type
            mimetype = self.get_mimetype(file)
            # Arno: don't encode mimetype in lambda, allow for dynamic 
            # determination by videoanalyser
            vod_usercallback_wrapper = lambda event,params:self.session.uch.perform_vod_usercallback(self,self.dlconfig['vod_usercallback'],event,params)

            vodfileindex['index'] = idx
            vodfileindex['inpath'] = file
            vodfileindex['bitrate'] = bitrate
            vodfileindex['mimetype'] = mimetype
            vodfileindex['usercallback'] = vod_usercallback_wrapper
            vodfileindex['userevents'] = self.dlconfig['vod_userevents'][:]
        elif live:
            # live torrents must be streamed or produced, but not just downloaded
            raise LiveTorrentRequiresUsercallbackException()
        # Ric: added svc case TODO
        elif self.dlconfig['mode'] == DLMODE_SVC:
            # video file present which is played or produced
            multi = False
            if 'files' in metainfo['info']:
                multi = True
            
            # Determine bitrate
            if multi and len(self.dlconfig['selected_files']) == 0:
                # Multi-file torrent, but no file selected
                raise VODNoFileSelectedInMultifileTorrentException() 
            
            # multi-file torrent
            # Ric: the selected files are already ordered
            files = self.dlconfig['selected_files']
            
            idx = []
            for file in files:
                idx.append( self.get_def().get_index_of_file_in_files(file) )
                
            bitrate = self.get_def().get_bitrate(files[0]) 
            
            # Determine MIME type
            mimetype = self.get_mimetype(file)
            # Arno: don't encode mimetype in lambda, allow for dynamic 
            # determination by videoanalyser
            vod_usercallback_wrapper = lambda event,params:self.session.uch.perform_vod_usercallback(self,self.dlconfig['vod_usercallback'],event,params)

            vodfileindex['index'] = idx
            vodfileindex['inpath'] = files
            vodfileindex['bitrate'] = bitrate
            vodfileindex['mimetype'] = mimetype
            vodfileindex['usercallback'] = vod_usercallback_wrapper
            vodfileindex['userevents'] = self.dlconfig['vod_userevents'][:]
            
        else:
            vodfileindex['mimetype'] = 'application/octet-stream'
            
        if DEBUG:
            print >>sys.stderr,"Download: create_engine_wrapper: vodfileindex",`vodfileindex` 

        # Delegate creation of engine wrapper to network thread
        network_create_engine_wrapper_lambda = lambda:self.network_create_engine_wrapper(infohash,metainfo,kvconfig,multihandler,listenport,vapath,vodfileindex,lmcreatedcallback,pstate,lmvodeventcallback)
        self.session.lm.rawserver.add_task(network_create_engine_wrapper_lambda,0) 
        

    def network_create_engine_wrapper(self,infohash,metainfo,kvconfig,multihandler,listenport,vapath,vodfileindex,lmcallback,pstate,lmvodeventcallback):
        """ Called by network thread """
        self.dllock.acquire()
        try:
            self.sd = SingleDownload(infohash,metainfo,kvconfig,multihandler,self.session.lm.get_ext_ip,listenport,vapath,vodfileindex,self.set_error,pstate,lmvodeventcallback,self.session.lm.hashcheck_done, self)
            sd = self.sd
            exc = self.error
            if lmcallback is not None:
                lmcallback(self,sd,exc,pstate)
        finally:
            self.dllock.release()

    #
    # Public method
    #
    def get_def(self):
        # No lock because attrib immutable and return value protected
        return self.tdef

    #
    # Retrieving DownloadState
    #
    def set_state_callback(self,usercallback,getpeerlist=False):
        """ Called by any thread """
        self.dllock.acquire()
        try:
            network_get_state_lambda = lambda:self.network_get_state(usercallback,getpeerlist)
            # First time on general rawserver
            self.session.lm.rawserver.add_task(network_get_state_lambda,0.0)
        finally:
            self.dllock.release()


    def network_get_state(self,usercallback,getpeerlist,sessioncalling=False):
        """ Called by network thread """
        self.dllock.acquire()
        try:
            # RePEX: get last stored SwarmCache, if any:
            swarmcache = None
            if self.pstate_for_restart is not None and self.pstate_for_restart.has_key('dlstate'):
                swarmcache = self.pstate_for_restart['dlstate'].get('swarmcache',None)
            
            if self.sd is None:
                if DEBUG:
                    print >>sys.stderr,"DownloadImpl: network_get_state: Download not running"
                ds = DownloadState(self,DLSTATUS_STOPPED,self.error,self.progressbeforestop,swarmcache=swarmcache)
            else:
                # RePEX: try getting the swarmcache from SingleDownload or use our last known swarmcache:
                swarmcache = self.sd.get_swarmcache() or swarmcache
                
                (status,stats,logmsgs,proxyservice_proxy_list,proxyservice_doe_list) = self.sd.get_stats(getpeerlist)
                ds = DownloadState(self,status,self.error,0.0,stats=stats,filepieceranges=self.filepieceranges,logmsgs=logmsgs,proxyservice_proxy_list=proxyservice_proxy_list,proxyservice_doe_list=proxyservice_doe_list,swarmcache=swarmcache)
                self.progressbeforestop = ds.get_progress()
            
            if sessioncalling:
                return ds

            # Invoke the usercallback function via a new thread.
            # After the callback is invoked, the return values will be passed to
            # the returncallback for post-callback processing.
            self.session.uch.perform_getstate_usercallback(usercallback,ds,self.sesscb_get_state_returncallback)
        finally:
            self.dllock.release()


    def sesscb_get_state_returncallback(self,usercallback,when,newgetpeerlist):
        """ Called by SessionCallbackThread """
        self.dllock.acquire()
        try:
            if when > 0.0:
                # Schedule next invocation, either on general or DL specific
                # TODO: ensure this continues when dl is stopped. Should be OK.
                network_get_state_lambda = lambda:self.network_get_state(usercallback,newgetpeerlist)
                if self.sd is None:
                    self.session.lm.rawserver.add_task(network_get_state_lambda,when)
                else:
                    self.sd.dlrawserver.add_task(network_get_state_lambda,when)
        finally:
            self.dllock.release()

    #
    # Download stop/resume
    #
    def stop(self):
        """ Called by any thread """
        self.stop_remove(removestate=False,removecontent=False)

    def stop_remove(self,removestate=False,removecontent=False):
        """ Called by any thread """
        if DEBUG:
            print >>sys.stderr,"DownloadImpl: stop_remove:",`self.tdef.get_name_as_unicode()`,"state",removestate,"content",removecontent
        self.dllock.acquire()
        try:
            network_stop_lambda = lambda:self.network_stop(removestate,removecontent)
            self.session.lm.rawserver.add_task(network_stop_lambda,0.0)
        finally:
            self.dllock.release()

    def network_stop(self,removestate,removecontent):
        """ Called by network thread """
        if DEBUG:
            print >>sys.stderr,"DownloadImpl: network_stop",`self.tdef.get_name_as_unicode()`
        self.dllock.acquire()
        try:
            infohash = self.tdef.get_infohash() 
            pstate = self.network_get_persistent_state()
            if self.sd is not None:
                pstate['engineresumedata'] = self.sd.shutdown()
                self.sd = None
                self.pstate_for_restart = pstate
            else:
                # This method is also called at Session shutdown, where one may
                # choose to checkpoint its Download. If the Download was 
                # stopped before, pstate_for_restart contains its resumedata.
                # and that should be written into the checkpoint.
                #
                if self.pstate_for_restart is not None:
                    if DEBUG:
                        print >>sys.stderr,"DownloadImpl: network_stop: Reusing previously saved engineresume data for checkpoint"
                    # Don't copy full pstate_for_restart, as the torrent
                    # may have gone from e.g. HASHCHECK at startup to STOPPED
                    # now, at shutdown. In other words, it was never active
                    # in this session and the pstate_for_restart still says 
                    # HASHCHECK.
                    pstate['engineresumedata'] = self.pstate_for_restart['engineresumedata'] 
            
            # Offload the removal of the content and other disk cleanup to another thread
            if removestate:
                contentdest = self.get_content_dest() 
                self.session.uch.perform_removestate_callback(infohash,contentdest,removecontent)
            
            return (infohash,pstate)
        finally:
            self.dllock.release()

        
    def restart(self, initialdlstatus=None):
        """ Restart the Download. Technically this action does not need to be
        delegated to the network thread, but does so removes some concurrency
        problems. By scheduling both stops and restarts via the network task 
        queue we ensure that they are executed in the order they were called.
        
        Note that when a Download is downloading or seeding, calling restart 
        is a no-op. If a Download is performing some other task, it is left 
        up to the internal running SingleDownload to determine what a restart 
        means. Often it means SingleDownload will abort its current task and 
        switch to downloading/seeding.
        
        Called by any thread """
        # RePEX: added initialdlstatus parameter
        # RePEX: TODO: Should we mention the initialdlstatus behaviour in the docstring?
        if DEBUG:
            print >>sys.stderr,"DownloadImpl: restart:",`self.tdef.get_name_as_unicode()`
        self.dllock.acquire()
        try:
            network_restart_lambda = lambda:self.network_restart(initialdlstatus)
            self.session.lm.rawserver.add_task(network_restart_lambda,0.0)
        finally:
            self.dllock.release()

    def network_restart(self,initialdlstatus=None):
        """ Called by network thread """
        # Must schedule the hash check via lm. In some cases we have batch stops
        # and restarts, e.g. we have stop all-but-one & restart-all for VOD)
        
        # RePEX: added initialdlstatus parameter
        if DEBUG:
            print >>sys.stderr,"DownloadImpl: network_restart",`self.tdef.get_name_as_unicode()`
        self.dllock.acquire()
        try:
            if self.sd is None:
                self.error = None # assume fatal error is reproducible
                # h4xor: restart using earlier loaded resumedata
                # RePEX: propagate initialdlstatus
                self.create_engine_wrapper(self.session.lm.network_engine_wrapper_created_callback,pstate=self.pstate_for_restart,lmvodeventcallback=self.session.lm.network_vod_event_callback,initialdlstatus=initialdlstatus)
            else:
                if DEBUG:
                    print >>sys.stderr,"DownloadImpl: network_restart: SingleDownload already running",`self`
                # RePEX: leave decision what to do to SingleDownload
                self.sd.restart(initialdlstatus)

            # No exception if already started, for convenience
        finally:
            self.dllock.release()
    
    
    #
    # Config parameters that only exists at runtime 
    #
    def set_max_desired_speed(self,direct,speed):
        if DEBUG:
            print >>sys.stderr,"Download: set_max_desired_speed",direct,speed
        #if speed < 10:
        #    print_stack()
        
        self.dllock.acquire()
        if direct == UPLOAD:
            self.dlruntimeconfig['max_desired_upload_rate'] = speed
        else:
            self.dlruntimeconfig['max_desired_download_rate'] = speed
        self.dllock.release()

    def get_max_desired_speed(self,direct):
        self.dllock.acquire()
        try:
            if direct == UPLOAD:
                return self.dlruntimeconfig['max_desired_upload_rate']
            else:
                return self.dlruntimeconfig['max_desired_download_rate']
        finally:
            self.dllock.release()

    def get_dest_files(self, exts=None):
        """ We could get this from BT1Download.files (see BT1Download.saveAs()),
        but that object is the domain of the network thread.
        You can give a list of extensions to return. If None: return all dest_files
        """

        def get_ext(filename):
            (prefix,ext) = os.path.splitext(filename)
            if ext != '' and ext[0] == '.':
                ext = ext[1:]
            return ext
        
        self.dllock.acquire()
        try:
            f2dlist = []
            metainfo = self.tdef.get_metainfo() 
            if 'files' not in metainfo['info']:
                # single-file torrent
                diskfn = self.get_content_dest()
                _, filename = os.path.split(diskfn)
                f2dtuple = (filename, diskfn)
                ext = get_ext(diskfn)
                if exts is None or ext in exts:
                    f2dlist.append(f2dtuple)
            else:
                # multi-file torrent
                if len(self.dlconfig['selected_files']) > 0:
                    fnlist = self.dlconfig['selected_files']
                else:
                    fnlist = self.tdef.get_files(exts=exts)
                    
                for filename in fnlist:
                    filerec = maketorrent.get_torrentfilerec_from_metainfo(filename,metainfo)
                    savepath = maketorrent.torrentfilerec2savefilename(filerec)
                    diskfn = maketorrent.savefilenames2finaldest(self.get_content_dest(),savepath)
                    ext = get_ext(diskfn)
                    if exts is None or ext in exts:
                        f2dtuple = (filename,diskfn)
                        f2dlist.append(f2dtuple)
                
            return f2dlist
        finally:
            self.dllock.release()

    



    #
    # Persistence
    #
    def network_checkpoint(self):
        """ Called by network thread """
        self.dllock.acquire()
        try:
            pstate = self.network_get_persistent_state() 
            if self.sd is None:
                resdata = None
            else:
                resdata = self.sd.checkpoint()
            pstate['engineresumedata'] = resdata
            return (self.tdef.get_infohash(),pstate)
        finally:
            self.dllock.release()
        

    def network_get_persistent_state(self):
        """ Assume dllock already held """
        pstate = {}
        pstate['version'] = PERSISTENTSTATE_CURRENTVERSION
        pstate['metainfo'] = self.tdef.get_metainfo() # assumed immutable
        dlconfig = copy.copy(self.dlconfig)
        # Reset unpicklable params
        dlconfig['vod_usercallback'] = None
        dlconfig['mode'] = DLMODE_NORMAL # no callback, no VOD
        pstate['dlconfig'] = dlconfig

        pstate['dlstate'] = {}
        #ds = self.network_get_state(None,False,sessioncalling=True)
        ds = self.network_get_state(None,True,sessioncalling=True) # RePEX: get peerlist in case of running Download
        pstate['dlstate']['status'] = ds.get_status()
        pstate['dlstate']['progress'] = ds.get_progress()
        pstate['dlstate']['swarmcache'] = ds.get_swarmcache() # RePEX: store SwarmCache
        
        if DEBUG:
            print >>sys.stderr,"Download: netw_get_pers_state: status",dlstatus_strings[ds.get_status()],"progress",ds.get_progress()
        
        pstate['engineresumedata'] = None
        return pstate

    #
    # ProxyService
    #
    def get_proxyservice_object(self, role):
        """ Called by network thread """
        role_object = None
        self.dllock.acquire()
        try:
            if self.sd is not None:
                role_object = self.sd.get_proxyservice_object(role)
        finally:
            self.dllock.release()
        return role_object



    #
    # Internal methods
    #
    def set_error(self,e):
        self.dllock.acquire()
        self.error = e
        self.dllock.release()


    def set_filepieceranges(self,metainfo):
        """ Determine which file maps to which piece ranges for progress info """
        
        if DEBUG:
            print >>sys.stderr,"Download: set_filepieceranges:",self.dlconfig['selected_files']
        (length,self.filepieceranges) = maketorrent.get_length_filepieceranges_from_metainfo(metainfo,self.dlconfig['selected_files'])

    def get_content_dest(self):
        """ Returns the file (single-file torrent) or dir (multi-file torrent)
        to which the downloaded content is saved. """
        return os.path.join(self.dlconfig['saveas'],self.correctedinfoname)
    
    # ARNOCOMMENT: better if we removed this from Core, user knows which
    # file he selected to play, let him figure out MIME type
    def get_mimetype(self,file):
        (prefix,ext) = os.path.splitext(file)
        ext = ext.lower()
        mimetype = None
        if sys.platform == 'win32':
            # TODO: Use Python's mailcap facility on Linux to find player
            try:
                from Tribler.Video.utils import win32_retrieve_video_play_command

                [mimetype,playcmd] = win32_retrieve_video_play_command(ext,file)
                if DEBUG:
                    print >>sys.stderr,"DownloadImpl: Win32 reg said MIME type is",mimetype
            except:
                if DEBUG:
                    print_exc()
                pass
        else:
            try:
                import mimetypes
                # homedir = os.path.expandvars('${HOME}')
                homedir = get_home_dir()
                homemapfile = os.path.join(homedir,'.mimetypes')
                mapfiles = [homemapfile] + mimetypes.knownfiles
                mimetypes.init(mapfiles)
                (mimetype,encoding) = mimetypes.guess_type(file)
                
                if DEBUG:
                    print >>sys.stderr,"DownloadImpl: /etc/mimetypes+ said MIME type is",mimetype,file
            except:
                print_exc()

        # if auto detect fails
        if mimetype is None:
            if ext == '.avi':
                # Arno, 2010-01-08: Hmmm... video/avi is not official registered at IANA
                mimetype = 'video/avi'
            elif ext == '.mpegts' or ext == '.ts':
                mimetype = 'video/mp2t'
            elif ext == '.mkv':
                mimetype = 'video/x-matroska'
            elif ext in ('.ogg', '.ogv'):
                mimetype = 'video/ogg'
            elif ext in ('.oga'):
                mimetype = 'audio/ogg'
            elif ext == '.webm':
                mimetype = 'video/webm'
            else:
                mimetype = 'video/mpeg'
        return mimetype
    
