# Written by Nitin Chiluka
# see LICENSE.txt for license information

import sys
import threading
from time import time, ctime, sleep
from zlib import compress, decompress
from binascii import hexlify
from traceback import print_exc, print_stack
from types import StringType, ListType, DictType
from random import randint, sample, seed, random, shuffle
from sha import sha
from sets import Set

from Tribler.Core.BitTornado.bencode import bencode, bdecode
from Tribler.Core.Statistics.Logger import OverlayLogger
from Tribler.Core.BitTornado.BT1.MessageID import CHANNELCAST, BUDDYCAST
from Tribler.Core.CacheDB.CacheDBHandler import ChannelCastDBHandler, VoteCastDBHandler
from Tribler.Core.Utilities.unicode import str2unicode
from Tribler.Core.Utilities.utilities import *
from Tribler.Core.Overlay.permid import permid_for_user,sign_data,verify_data
from Tribler.Core.CacheDB.sqlitecachedb import SQLiteCacheDB, bin2str, str2bin, NULL
from Tribler.Core.CacheDB.Notifier import Notifier
from Tribler.Core.SocialNetwork.RemoteTorrentHandler import RemoteTorrentHandler
from Tribler.Core.SocialNetwork.RemoteQueryMsgHandler import RemoteQueryMsgHandler
from Tribler.Core.BuddyCast.moderationcast_util import *
from Tribler.Core.Overlay.SecureOverlay import OLPROTO_VER_THIRTEENTH,\
    OLPROTO_VER_FOURTEENTH
from Tribler.Core.simpledefs import NTFY_CHANNELCAST, NTFY_UPDATE
from Tribler.Core.Subtitles.RichMetadataInterceptor import RichMetadataInterceptor
from Tribler.Core.CacheDB.MetadataDBHandler import MetadataDBHandler
from Tribler.Core.Subtitles.PeerHaveManager import PeersHaveManager
from Tribler.Core.Subtitles.SubtitlesSupport import SubtitlesSupport

DEBUG = False

NUM_OWN_RECENT_TORRENTS = 15
NUM_OWN_RANDOM_TORRENTS = 10
NUM_OTHERS_RECENT_TORRENTS = 15
NUM_OTHERS_RECENT_TORRENTS = 10

RELOAD_FREQUENCY = 2*60*60

class ChannelCastCore:
    __single = None
    TESTASSERVER = False # for unit testing

    def __init__(self, data_handler, overlay_bridge, session, buddycast_interval_function, log = '', dnsindb = None):
        """ Returns an instance of this class """
        if ChannelCastCore.__single:
            raise RuntimeError, "ChannelCastCore is singleton"
        ChannelCastCore.__single = self
        
        #Keep reference to interval-function of BuddycastFactory
        self.interval = buddycast_interval_function
        self.data_handler = data_handler
        self.dnsindb = dnsindb
        self.log = log
        self.overlay_bridge = overlay_bridge
        self.channelcastdb = ChannelCastDBHandler.getInstance()
        self.votecastdb = VoteCastDBHandler.getInstance()
        self.rtorrent_handler = RemoteTorrentHandler.getInstance()
        
        self.session = session
        self.my_permid = session.get_permid()
        
        self.network_delay = 30
        #Reference to buddycast-core, set by the buddycast-core (as it is created by the
        #buddycast-factory after calling this constructor).
        self.buddycast_core = None
        
        #Extend logging with ChannelCast-messages and status
        if self.log:
            self.overlay_log = OverlayLogger.getInstance(self.log)
            self.dnsindb = self.data_handler.get_dns_from_peerdb

        self.notifier = Notifier.getInstance()

        self.metadataDbHandler = MetadataDBHandler.getInstance()
        
        #subtitlesHandler = SubtitlesHandler.getInstance()
        subtitleSupport = SubtitlesSupport.getInstance()
        # better if an instance of RMDInterceptor was provided from the
        # outside
        self.peersHaveManger = PeersHaveManager.getInstance()
        if not self.peersHaveManger.isRegistered():
                self.peersHaveManger.register(self.metadataDbHandler, self.overlay_bridge)
        #self.richMetadataInterceptor = RichMetadataInterceptor(self.metadataDbHandler,self.votecastdb,
        #                                                       self.my_permid, subtitleSupport, self.peersHaveManger,
        #                                                       self.notifier)
    
    def initialized(self):
        return self.buddycast_core is not None

    def getInstance(*args, **kw):
        if ChannelCastCore.__single is None:
            ChannelCastCore(*args, **kw)
        return ChannelCastCore.__single
    getInstance = staticmethod(getInstance)
    def gotChannelCastMessage(self, recv_msg, sender_permid, selversion):
        """ Receive and handle a ChannelCast message """
        # ChannelCast feature starts from eleventh version; hence, do not receive from lower version peers
        # Arno, 2010-02-05: v12 uses a different on-the-wire format, ignore those.
        # Andrea: 2010-04-08: v14 can still receive v13 channelcast messages
        # Niels: 2011-02-02: Channelcast is now using dispersy, but we can still receive old messages
        
        if selversion < OLPROTO_VER_THIRTEENTH:
            if DEBUG:
                print >> sys.stderr, "channelcast: Do not receive from lower version peer:", selversion
            return True
                
        if DEBUG:
            print >> sys.stderr,'channelcast: Received a msg from ', show_permid_short(sender_permid)
            print >> sys.stderr,"channelcast: my_permid=", show_permid_short(self.my_permid)
        
        if not sender_permid or sender_permid == self.my_permid:
            if DEBUG:
                print >> sys.stderr, "channelcast: warning - got channelcastMsg from a None/Self peer", \
                        show_permid_short(sender_permid), recv_msg
            return False
       
        channelcast_data = {}
        try:
            channelcast_data = bdecode(recv_msg)
        except:
            print >> sys.stderr, "channelcast: warning, invalid bencoded data"
            return False

        # check message-structure
        if not validChannelCastMsg(channelcast_data):
            print >> sys.stderr, "channelcast: invalid channelcast_message"
            return False

        # 19/02/10 Boudewijn: validChannelCastMsg passes when
        # PUBLISHER_NAME and TORRENTNAME are either string or
        # unicode-string.  However, all further code requires that
        # these are unicode!
        for ch in channelcast_data.values():
            if isinstance(ch["publisher_name"], str):
                ch["publisher_name"] = str2unicode(ch["publisher_name"])
            if isinstance(ch["torrentname"], str):
                ch["torrentname"] = str2unicode(ch["torrentname"])

        self.handleChannelCastMsg(sender_permid, channelcast_data)
        
        #Log RECV_MSG of uncompressed message
        if self.log:
            dns = self.dnsindb(sender_permid)
            if dns:
                ip,port = dns
                MSG_ID = "CHANNELCAST"
                # 08/04/10 Andrea: representing the whole channelcast  + metadata message
                msg = repr(channelcast_data)
                self.overlay_log('RECV_MSG', ip, port, show_permid(sender_permid), selversion, MSG_ID, msg)
 
        if self.TESTASSERVER:
            self.createAndSendChannelCastMessage(sender_permid, selversion)
        return True       

    def handleChannelCastMsg(self, sender_permid, data):
        self._updateChannelInternal(sender_permid, None, data)

    def updateChannel(self,query_permid, query, hits):
        """
        This function is called when there is a reply from remote peer regarding updating of a channel
        @param query_permid: the peer who returned the results
        @param query: the query string (None if this is not the results of a query) 
        @param hits: details of all matching results related to the query
        """
        if DEBUG:
            print >> sys.stderr, "channelcast: sending message to", bin2str(query_permid), query, len(hits)
        return self._updateChannelInternal(query_permid, query, hits)
        
    def _updateChannelInternal(self, query_permid, query, hits):
        listOfAdditions = list()

        if len(hits) > 0:
            # a single read from the db is more efficient
            all_spam_channels = self.votecastdb.getPublishersWithNegVote(bin2str(self.session.get_permid()))
            permid_channel_id = self.channelcastdb.getPermChannelIdDict()

            for k,v in hits.items():
                #create new channel if not found
                if v['publisher_id'] not in permid_channel_id:
                    permid_channel_id[v['publisher_id']] = self.channelcastdb.on_channel_from_channelcast(v['publisher_id'], v['publisher_name'])

                #add local channel_id to all messages
                v['channel_id'] = permid_channel_id[v['publisher_id']]

                #check if the record belongs to a channel who we have "reported spam" (negative vote)
                if bin2str(v['publisher_id']) in all_spam_channels:
                    # if so, ignore the incoming record
                    continue

                # make everything into "string" format, if "binary"
                hit = (bin2str(v['publisher_id']),v['publisher_name'],bin2str(v['infohash']),bin2str(v['torrenthash']),v['torrentname'],v['time_stamp'],bin2str(k))
                listOfAdditions.append(hit)

            # Arno, 2010-06-11: We're on the OverlayThread
            self._updateChannelcastDB(query_permid, query, hits, listOfAdditions)
        return listOfAdditions
    
    def _updateChannelcastDB(self, query_permid, query, hits, listOfAdditions):
        if DEBUG:
            print >> sys.stderr, "channelcast: updating channelcastdb", query, len(hits)

        channel_ids = Set()
        infohashes = Set()
        for hit in listOfAdditions:
            channel_ids.add(hit[0])
            infohashes.add(hit[2])
            
        my_favorites = self.votecastdb.getChannelsWithPosVote(bin2str(self.my_permid))

#         if query and query.startswith('CHANNEL p') and len(publisher_ids) == 1:
#             publisher_id = publisher_ids.pop()
#             publisher_ids.add(publisher_id)
            
#             nr_torrents = self.channelcastdb.getNrTorrentsInChannel(publisher_id)
#             if len(infohashes) > nr_torrents:
#                 if len(infohashes) > 50 and len(infohashes) > nr_torrents +1: #peer not behaving according to spec, ignoring
#                     if DEBUG:
#                         print >> sys.stderr, "channelcast: peer not behaving according to spec, ignoring",len(infohashes), show_permid(query_permid)
#                     return
                
#                 #if my channel, never remove all currently received
#                 if bin2str(self.session.get_permid()) != publisher_id:
#                     self.channelcastdb.deleteTorrentsFromPublisherId(str2bin(publisher_id))
#             if DEBUG:
#                 print >> sys.stderr, 'Received channelcast message with %d hashes'%len(infohashes), show_permid(query_permid)
#         else:
#             #ignore all my favorites, randomness will cause problems with timeframe
#             my_favorites = self.votecastdb.getPublishersWithPosVote(bin2str(self.session.get_permid()))
            
#             #filter listOfAdditions
#             listOfAdditions = [hit for hit in listOfAdditions if hit[0] not in my_favorites]
            
#             #request channeltimeframes for subscribed channels
#             for publisher_id in my_favorites:
#                 if publisher_id in publisher_ids:
#                     self.updateAChannel(publisher_id, [query_permid])
#                     publisher_ids.remove(publisher_id) #filter publisher_ids
            
#         #08/04/10: Andrea: processing rich metadata part.
#         self.richMetadataInterceptor.handleRMetadata(query_permid, hits, fromQuery = query is not None)
        
        #request updates for subscribed channels
        for channel_id in my_favorites:
            if channel_id in channel_ids:
                self.updateAChannel(channel_id, [query_permid])
            
        self.channelcastdb.on_torrents_from_channelcast(listOfAdditions)
        missing_infohashes = {}
        for channel_id in channel_ids:
            for infohash in self.channelcastdb.selectTorrentsToCollect(channel_id):
                missing_infohashes[infohash] = channel_id
                
        def notify(channel_id):
            self.notifier.notify(NTFY_CHANNELCAST, NTFY_UPDATE, channel_id)

        for infohash, channel_id in missing_infohashes.iteritems():
            if infohash in infohashes:
                self.rtorrent_handler.download_torrent(query_permid, infohash, lambda infohash, metadata, filename: notify(channel_id) ,2)
            else:
                self.rtorrent_handler.download_torrent(query_permid, infohash, lambda infohash, metadata, filename: notify(channel_id) ,3)
    
    def updateMySubscribedChannels(self):
        def update(permids):
            permid = permids.pop()

        #TODO: DETECT DISPERSY CHANNELS
        subscribed_channels = self.channelcastdb.getMySubscribedChannels()
        for channel in subscribed_channels:
            permid = self.channelcastdb.getPermidForChannel(channel[0])

            self.updateAChannel(permid)
            
            if len(permids) > 0:
                self.overlay_bridge.add_task(lambda: update(permids), 20)
        
        subscribed_channels = self.channelcastdb.getMySubscribedChannels()
        permids = [values[0] for values in subscribed_channels]
        if len(permids) > 0:
            update(permids)
        
        self.overlay_bridge.add_task(self.updateMySubscribedChannels, RELOAD_FREQUENCY)    
    
    def updateAChannel(self, publisher_id, peers = None, timeframe = None):
        if peers == None:
            peers = RemoteQueryMsgHandler.getInstance().get_connected_peers(OLPROTO_VER_THIRTEENTH)
        shuffle(peers)
        # Create separate task which does all the requesting
        self.overlay_bridge.add_task(lambda: self._sequentialQueryPeers(publisher_id, peers, timeframe))
    
    def _sequentialQueryPeers(self, publisher_id, peers, timeframe = None):
        def seqtimeout(permid):
            if peers and permid == peers[0][0]:
                peers.pop(0)
                dorequest()
                
        def seqcallback(query_permid, query, hits):
            self.updateChannel(query_permid, query, hits)
            
            if peers and query_permid == peers[0][0]:
                peers.pop(0)
                dorequest()
            
        def dorequest():
            if peers:
                permid, selversion = peers[0]
                
                q = "CHANNEL p "+publisher_id
                
                if timeframe:
                    record = timeframe
                else:
                    record = self.channelcastdb.getTimeframeForChannel(publisher_id)
                
                if record:
                    q+= " "+" ".join(map(str,record))
                self.session.query_peers(q,[permid],usercallback = seqcallback)

                self.overlay_bridge.add_task(lambda: seqtimeout(permid), 30)
        peers = peers[:]
        dorequest()
