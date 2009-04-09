# Written by Jie Yang
# see LICENSE.txt for license information
# Note for Developers: Please write a unittest in Tribler/Test/test_sqlitecachedbhandler.py 
# for any function you add to database. 
# Please reuse the functions in sqlitecachedb as much as possible

from Tribler.Core.CacheDB.sqlitecachedb import SQLiteCacheDB, bin2str, str2bin, NULL
from unicode import name2unicode,dunno2unicode
from copy import deepcopy,copy
from sets import Set
from traceback import print_exc, print_stack
from threading import currentThread
from time import time
from sha import sha
import sys
import os
import socket
import threading
import base64
from random import randint, sample
from sets import Set
import math


from maxflow import Network
from math import atan, pi


from Tribler.Core.BitTornado.bencode import bencode, bdecode
from Notifier import Notifier
from Tribler.Core.simpledefs import *
from Tribler.Core.BuddyCast.moderationcast_util import *
from Tribler.Core.Overlay.permid import sign_data, verify_data
from Tribler.Category.Category import Category

# maxflow constants
MAXFLOW_DISTANCE = 2
ALPHA = float(1)/30000

DEBUG = False
SHOW_ERROR = False

MAX_KEYWORDS_STORED = 5
MAX_KEYWORD_LENGTH = 50

def show_permid_shorter(permid):
    if not permid:
        return 'None'
    s = base64.encodestring(permid).replace("\n","")
    return s[-5:]

class BasicDBHandler:
    def __init__(self,db, table_name): ## self, table_name
        self._db = db ## SQLiteCacheDB.getInstance()
        self.table_name = table_name
        self.notifier = Notifier.getInstance()
        
    def __del__(self):
        try:
            self.sync()
        except:
            if SHOW_ERROR:
                print_exc()
        
    def close(self):
        try:
            self._db.close()
        except:
            if SHOW_ERROR:
                print_exc()
        
    def size(self):
        return self._db.size(self.table_name)

    def sync(self):
        self._db.commit()
        
    def commit(self):
        self._db.commit()
        
    def getOne(self, value_name, where=None, conj='and', **kw):
        return self._db.getOne(self.table_name, value_name, where=where, conj=conj, **kw)
    
    def getAll(self, value_name, where=None, group_by=None, having=None, order_by=None, limit=None, offset=None, conj='and', **kw):
        return self._db.getAll(self.table_name, value_name, where=where, group_by=group_by, having=having, order_by=order_by, limit=limit, offset=offset, conj=conj, **kw)
    
            
class MyDBHandler(BasicDBHandler):

    __single = None    # used for multithreaded singletons pattern
    lock = threading.Lock()
    
    def getInstance(*args, **kw):
        # Singleton pattern with double-checking
        if MyDBHandler.__single is None:
            MyDBHandler.lock.acquire()   
            try:
                if MyDBHandler.__single is None:
                    MyDBHandler(*args, **kw)
            finally:
                MyDBHandler.lock.release()
        return MyDBHandler.__single
    
    getInstance = staticmethod(getInstance)
    
    def __init__(self):
        if MyDBHandler.__single is not None:
            raise RuntimeError, "MyDBHandler is singleton"
        MyDBHandler.__single = self
        db = SQLiteCacheDB.getInstance()
        BasicDBHandler.__init__(self,db,'MyInfo') ## self,db,'MyInfo'
        # keys: version, torrent_dir
        
    def get(self, key, default_value=None):
        value = self.getOne('value', entry=key)
        if value is not NULL:
            return value
        else:
            if default_value is not None:
                return default_value
            else:
                raise KeyError, key

    def put(self, key, value, commit=True):
        if self.getOne('value', entry=key) is NULL:
            self._db.insert(self.table_name, commit=commit, entry=key, value=value)
        else:
            where = "entry=" + repr(key)
            self._db.update(self.table_name, where, commit=commit, value=value)

class FriendDBHandler(BasicDBHandler):
    
    __single = None    # used for multithreaded singletons pattern
    lock = threading.Lock()
    
    def getInstance(*args, **kw):
        # Singleton pattern with double-checking
        if FriendDBHandler.__single is None:
            FriendDBHandler.lock.acquire()   
            try:
                if FriendDBHandler.__single is None:
                    FriendDBHandler(*args, **kw)
            finally:
                FriendDBHandler.lock.release()
        return FriendDBHandler.__single
    
    getInstance = staticmethod(getInstance)
    
    def __init__(self):
        if FriendDBHandler.__single is not None:
            raise RuntimeError, "FriendDBHandler is singleton"
        FriendDBHandler.__single = self
        db = SQLiteCacheDB.getInstance()
        BasicDBHandler.__init__(self,db, 'Peer') ## self,db,'Peer'
        
    def setFriendState(self, permid, state=1, commit=True):
        self._db.update(self.table_name,  'permid='+repr(bin2str(permid)), commit=commit, friend=state)
        self.notifier.notify(NTFY_PEERS, NTFY_UPDATE, permid, 'friend', state)

    def getFriends(self,state=1):
        where = 'friend=%d ' % state
        res = self._db.getAll('Friend', 'permid',where=where)
        return [str2bin(p[0]) for p in res]
        #raise Exception('Use PeerDBHandler getGUIPeers(category = "friend")!')

    def getFriendState(self, permid):
        res = self.getOne('friend', permid=bin2str(permid))
        return res
        
    def deleteFriend(self,permid):
        self.setFriendState(permid,0)
        
    def searchNames(self,kws):
        return doPeerSearchNames(self,'Friend',kws)
        
    def getRanks(self):
        # TODO
        return []
    
    def size(self):
        return self._db.size('Friend')
    
    def addExternalFriend(self, peer):
        peerdb = PeerDBHandler.getInstance()
        peerdb.addPeer(peer['permid'], peer)
        self.setFriendState(peer['permid'])
        
NETW_MIME_TYPE = 'image/jpeg'

class PeerDBHandler(BasicDBHandler):
    
    __single = None    # used for multithreaded singletons pattern
    lock = threading.Lock()

    gui_value_name = ('permid', 'name', 'ip', 'port', 'similarity', 'friend',
                      'num_peers', 'num_torrents', 'num_prefs', 
                      'connected_times', 'buddycast_times', 'last_connected')
    
    def getInstance(*args, **kw):
        # Singleton pattern with double-checking
        if PeerDBHandler.__single is None:
            PeerDBHandler.lock.acquire()   
            try:
                if PeerDBHandler.__single is None:
                    PeerDBHandler(*args, **kw)
            finally:
                PeerDBHandler.lock.release()
        return PeerDBHandler.__single
    
    getInstance = staticmethod(getInstance)
    
    def __init__(self):
        if PeerDBHandler.__single is not None:
            raise RuntimeError, "PeerDBHandler is singleton"
        PeerDBHandler.__single = self
        db = SQLiteCacheDB.getInstance()
        BasicDBHandler.__init__(self, db,'Peer') ## self, db ,'Peer'
        self.pref_db = PreferenceDBHandler.getInstance()
        self.online_peers = set()


    def __len__(self):
        return self.size()

    def getPeerID(self, permid):
        return self._db.getPeerID(permid)

    def getPeer(self, permid, keys=None):
        if keys is not None:
            res = self.getOne(keys, permid=bin2str(permid))
            return res
        else:
            # return a dictionary
            # make it compatible for calls to old bsddb interface
            value_name = ('permid', 'name', 'ip', 'port', 'similarity', 'friend',
                      'num_peers', 'num_torrents', 'num_prefs', 'num_queries', 
                      'connected_times', 'buddycast_times', 'last_connected', 'last_seen', 'last_buddycast')

            item = self.getOne(value_name, permid=bin2str(permid))
            if not item:
                return None
            peer = dict(zip(value_name, item))
            peer['permid'] = str2bin(peer['permid'])
            return peer
        
    def getPeerSim(self, permid):
        permid_str = bin2str(permid)
        sim = self.getOne('similarity', permid=permid_str)
        if sim is None:
            sim = 0
        return sim
        
    def getPeerList(self, peerids=None):    # get the list of all peers' permid
        if peerids is None:
            permid_strs = self.getAll('permid')
            return [str2bin(permid_str[0]) for permid_str in permid_strs]
        else:
            if not peerids:
                return []
            s = str(peerids).replace('[','(').replace(']',')')
#            if len(peerids) == 1:
#                s = '(' + str(peerids[0]) + ')'    # tuple([1]) = (1,), syntax error for sql
#            else:
#                s = str(tuple(peerids))
            sql = 'select permid from Peer where peer_id in ' + s
            permid_strs = self._db.fetchall(sql)
            return [str2bin(permid_str[0]) for permid_str in permid_strs]
        

    def getPeers(self, peer_list, keys):    # get a list of dictionaries given peer list
        # BUG: keys must contain 2 entries, otherwise the records in all are single values??
        value_names = ",".join(keys)
        sql = 'select %s from Peer where permid=?;'%value_names
        all = []
        for permid in peer_list:
            permid_str = bin2str(permid)
            p = self._db.fetchone(sql, (permid_str,))
            all.append(p)
        
        peers = []
        for i in range(len(all)):
            p = all[i]
            peer = dict(zip(keys,p))
            peer['permid'] = peer_list[i]
            peers.append(peer)
        
        return peers
    
    def addPeer(self, permid, value, update_dns=True, update_connected=False, commit=True):
        # add or update a peer
        # ARNO: AAARGGH a method that silently changes the passed value param!!!
        # Jie: deepcopy(value)?
        
        _permid = _last_seen = _ip = _port = None
        if 'permid' in value:
            _permid = value.pop('permid')
            
        if not update_dns:
            if value.has_key('ip'):
                _ip = value.pop('ip')
            if value.has_key('port'):
                _port = value.pop('port')
                
        if update_connected:
            old_connected = self.getOne('connected_times', permid=bin2str(permid))
            if not old_connected:
                value['connected_times'] = 1
            else:
                value['connected_times'] = old_connected + 1
            
        peer_existed = self._db.insertPeer(permid, commit=commit, **value)
        
        if _permid is not None:
            value['permid'] = permid
        if _last_seen is not None:
            value['last_seen'] = _last_seen
        if _ip is not None:
            value['ip'] = _ip
        if _port is not None:
            value['port'] = _port
        
        if peer_existed:
            self.notifier.notify(NTFY_PEERS, NTFY_UPDATE, permid)
        # Jie: only notify the GUI when a peer was connected
        if 'connected_times' in value:
            self.notifier.notify(NTFY_PEERS, NTFY_INSERT, permid)

        #print >>sys.stderr,"sqldbhand: addPeer",`permid`,self._db.getPeerID(permid),`value`
        #print_stack()
            
            
    def hasPeer(self, permid):
        return self._db.hasPeer(permid)

    def findPeers(self, key, value):    
        # only used by Connecter
        if key == 'permid':
            value = bin2str(value)
        res = self.getAll('permid', **{key:value})
        if not res:
            return []
        ret = []
        for p in res:
            ret.append({'permid':str2bin(p[0])})
        return ret
    
    def updatePeer(self, permid, commit=True, **argv):
        self._db.update(self.table_name, 'permid='+repr(bin2str(permid)), commit=commit, **argv)
        self.notifier.notify(NTFY_PEERS, NTFY_UPDATE, permid)

        #print >>sys.stderr,"sqldbhand: updatePeer",`permid`,argv
        #print_stack()

    def deletePeer(self, permid=None, peer_id=None, force=False, commit=True):
        # don't delete friend of superpeers, except that force is True
        # to do: add transaction
        #self._db._begin()    # begin a transaction
        if peer_id is None:
            peer_id = self._db.getPeerID(permid)
        if peer_id is None:
            return
        deleted = self._db.deletePeer(permid=permid, peer_id=peer_id, force=force, commit=commit)
        if deleted:
            self.pref_db._deletePeer(peer_id=peer_id, commit=commit)
        self.notifier.notify(NTFY_PEERS, NTFY_DELETE, permid)
            
    def updateTimes(self, permid, key, change=1, commit=True):
        permid_str = bin2str(permid)
        sql = "SELECT peer_id,%s FROM Peer WHERE permid==?"%key
        find = self._db.fetchone(sql, (permid_str,))
        if find:
            peer_id,value = find
            if value is None:
                value = 1
            else:
                value += change
            sql_update_peer = "UPDATE Peer SET %s=? WHERE peer_id=?"%key
            self._db.execute_write(sql_update_peer, (value, peer_id), commit=commit)
        self.notifier.notify(NTFY_PEERS, NTFY_UPDATE, permid)

    def updatePeerSims(self, sim_list, commit=True):
        sql_update_sims = 'UPDATE Peer SET similarity=? WHERE peer_id=?'
        s = time()
        self._db.executemany(sql_update_sims, sim_list, commit=commit)

    def getPermIDByIP(self,ip):
        permid = self.getOne('permid', ip=ip)
        if permid is not None:
            return str2bin(permid)
        else:
            return None
        
    def getPermid(self, peer_id):
        permid = self.getOne('permid', peer_id=peer_id)
        if permid is not None:
            return str2bin(permid)
        else:
            return None
        
    def getNumberPeers(self, category_name = 'all'):
        # 28/07/08 boudewijn: counting the union from two seperate
        # select statements is faster than using a single select
        # statement with an OR in the WHERE clause. Note that UNION
        # returns a distinct list of peer_id's.
        if category_name == 'friend':
            sql = 'SELECT COUNT(peer_id) FROM Peer WHERE last_connected > 0 AND friend = 1'
        else:
            sql = 'SELECT COUNT(peer_id) FROM (SELECT peer_id FROM Peer WHERE last_connected > 0 UNION SELECT peer_id FROM Peer WHERE friend = 1)'
        res = self._db.fetchone(sql)
        if not res:
            res = 0
        return res
    
    def getGUIPeers(self, category_name = 'all', range = None, sort = None, reverse = False, get_online=False, get_ranks=True):
        #
        # ARNO: WHY DIFF WITH NORMAL getPeers??????
        # load peers for GUI
        #print >> sys.stderr, 'getGUIPeers(%s, %s, %s, %s)' % (category_name, range, sort, reverse)
        """
        db keys: peer_id, permid, name, ip, port, thumbnail, oversion, 
                 similarity, friend, superpeer, last_seen, last_connected, 
                 last_buddycast, connected_times, buddycast_times, num_peers, 
                 num_torrents, num_prefs, num_queries, 
                 
        @in: get_online: boolean: if true, give peers a key 'online' if there is a connection now
        """
        value_name = PeerDBHandler.gui_value_name
        
        where = '(last_connected>0 or friend=1 or friend=2 or friend=3) '
        if category_name in ('friend', 'friends'):
            # Show mutual, I invited and he invited 
            where += 'and (friend=1 or friend=2 or friend=3) '
        if range:
            offset= range[0]
            limit = range[1] - range[0]
        else:
            limit = offset = None
        if sort:
            # Arno, 2008-10-6: buggy: not reverse???
            desc = (reverse) and 'desc' or ''
            if sort in ('name'):
                order_by = ' lower(%s) %s' % (sort, desc)
            else:
                order_by = ' %s %s' % (sort, desc)
        else:
            order_by = None

        # Must come before query
        if get_ranks:
            ranks = self.getRanks()
        # Arno, 2008-10-23: Someone disabled ranking of people, why?
            
        res_list = self.getAll(value_name, where, offset= offset, limit=limit, order_by=order_by)
        
        #print >>sys.stderr,"getGUIPeers: where",where,"offset",offset,"limit",limit,"order",order_by
        #print >>sys.stderr,"getGUIPeers: returned len",len(res_list)
        
        peer_list = []
        for item in res_list:
            peer = dict(zip(value_name, item))
            peer['name'] = dunno2unicode(peer['name'])
            peer['simRank'] = ranksfind(ranks,peer['permid'])
            peer['permid'] = str2bin(peer['permid'])
            peer_list.append(peer)
            
        if get_online:
           self.checkOnline(peer_list)
            
        # peer_list consumes about 1.5M for 1400 peers, and this function costs about 0.015 second
        
        return  peer_list

            
    def getRanks(self):
        value_name = 'permid'
        order_by = 'similarity desc'
        rankList_size = 20
        where = '(last_connected>0 or friend=1) '
        res_list = self._db.getAll('Peer', value_name, where=where, limit=rankList_size, order_by=order_by)
        return [a[0] for a in res_list]
        
    def checkOnline(self, peerlist):
        # Add 'online' key in peers when their permid
        # Called by any thread, accesses single online_peers-dict
        # Peers will never be sorted by 'online' because it is not in the db.
        # Do not sort here, because then it would be sorted with a partial select (1 page in the grid)
        self.lock.acquire()
        for peer in peerlist:
            peer['online'] = (peer['permid'] in self.online_peers)
        self.lock.release()
        
        

    def setOnline(self,subject,changeType,permid,*args):
        """Called by callback threads
        with NTFY_CONNECTION, args[0] is boolean: connection opened/closed
        """
        self.lock.acquire()
        if args[0]: # connection made
            self.online_peers.add(permid)
        else: # connection closed
            self.online_peers.remove(permid)
        self.lock.release()
        #print >> sys.stderr, (('#'*50)+'\n')*5+'%d peers online' % len(self.online_peers)

    def registerConnectionUpdater(self, session):
        session.add_observer(self.setOnline, NTFY_PEERS, [NTFY_CONNECTION], None)
    
    def updatePeerIcon(self, permid, icontype, icondata, updateFlag = True):
         # save thumb in db
         self.updatePeer(permid, thumbnail=bin2str(icondata))
         #if self.mm is not None:
         #    self.mm.save_data(permid, icontype, icondata)
    

    def getPeerIcon(self, permid):
        item = self.getOne('thumbnail', permid=bin2str(permid))
        if item:
            return NETW_MIME_TYPE, str2bin(item)
        else:
            return None, None
        #if self.mm is not None:
        #    return self.mm.load_data(permid)
        #3else:
        #    return None


    def searchNames(self,kws):
        return doPeerSearchNames(self,'Peer',kws)



class SuperPeerDBHandler(BasicDBHandler):
    
    __single = None    # used for multithreaded singletons pattern
    lock = threading.Lock()
    
    def getInstance(*args, **kw):
        # Singleton pattern with double-checking
        if SuperPeerDBHandler.__single is None:
            SuperPeerDBHandler.lock.acquire()   
            try:
                if SuperPeerDBHandler.__single is None:
                    SuperPeerDBHandler(*args, **kw)
            finally:
                SuperPeerDBHandler.lock.release()
        return SuperPeerDBHandler.__single
    
    getInstance = staticmethod(getInstance)
    
    def __init__(self):
        if SuperPeerDBHandler.__single is not None:
            raise RuntimeError, "SuperPeerDBHandler is singleton"
        SuperPeerDBHandler.__single = self
        db = SQLiteCacheDB.getInstance()
        BasicDBHandler.__init__(self, db, 'SuperPeer')
        self.peer_db_handler = PeerDBHandler.getInstance()
        
    def loadSuperPeers(self, config, refresh=False):
        filename = os.path.join(config['install_dir'], config['superpeer_file'])
        superpeer_list = self.readSuperPeerList(filename)
        self.insertSuperPeers(superpeer_list, refresh)

    def readSuperPeerList(self, filename=''):
        """ read (superpeer_ip, superpeer_port, permid [, name]) lines from a text file """
        
        try:
            filepath = os.path.abspath(filename)
            file = open(filepath, "r")
        except IOError:
            print >> sys.stderr, "superpeer: cannot open superpeer file", filepath
            return []
            
        superpeers = file.readlines()
        file.close()
        superpeers_info = []
        for superpeer in superpeers:
            if superpeer.strip().startswith("#"):    # skip commended lines
                continue
            superpeer_line = superpeer.split(',')
            superpeer_info = [a.strip() for a in superpeer_line]
            try:
                superpeer_info[2] = base64.decodestring(superpeer_info[2]+'\n' )
            except:
                print_exc()
                continue
            try:
                ip = socket.gethostbyname(superpeer_info[0])
                superpeer = {'ip':ip, 'port':superpeer_info[1], 
                          'permid':superpeer_info[2], 'superpeer':1}
                if len(superpeer_info) > 3:
                    superpeer['name'] = superpeer_info[3]
                superpeers_info.append(superpeer)
            except:
                print_exc()
                    
        return superpeers_info

    def insertSuperPeers(self, superpeer_list, refresh=False):
        for superpeer in superpeer_list:
            superpeer = deepcopy(superpeer)
            if not isinstance(superpeer, dict) or 'permid' not in superpeer:
                continue
            permid = superpeer.pop('permid')
            self.peer_db_handler.addPeer(permid, superpeer, commit=False)
        self.peer_db_handler.commit()
    
    def getSuperPeers(self):
        # return list with permids of superpeers
        res_list = self._db.getAll(self.table_name, 'permid')
        return [str2bin(a[0]) for a in res_list]
        
    def addExternalSuperPeer(self, peer):
        _peer = deepcopy(peer)
        permid = _peer.pop('permid')
        _peer['superpeer'] = 1
        self._db.insertPeer(permid, **_peer)


class CrawlerDBHandler:
    """
    The CrawlerDBHandler is not an actual handle to a
    database. Instead it uses a local file (usually crawler.txt) to
    identify crawler processes.
    """
    
    __single = None    # used for multithreaded singletons pattern
    lock = threading.Lock()
    
    def getInstance(*args, **kw):
        # Singleton pattern with double-checking
        if CrawlerDBHandler.__single is None:
            CrawlerDBHandler.lock.acquire()   
            try:
                if CrawlerDBHandler.__single is None:
                    CrawlerDBHandler(*args, **kw)
            finally:
                CrawlerDBHandler.lock.release()
        return CrawlerDBHandler.__single
    
    getInstance = staticmethod(getInstance)
    
    def __init__(self):
        if CrawlerDBHandler.__single is not None:
            raise RuntimeError, "CrawlerDBHandler is singleton"
        CrawlerDBHandler.__single = self
        self._crawler_list = []
        
    def loadCrawlers(self, config, refresh=False):
        filename = os.path.join(config['crawler_file'])
        self._crawler_list = self.readCrawlerList(filename)

    def readCrawlerList(self, filename=''):
        """
        read (permid [, name]) lines from a text file
        returns a list containing permids
        """
        
        try:
            filepath = os.path.abspath(filename)
            file = open(filepath, "r")
        except IOError:
            print >> sys.stderr, "crawler: cannot open crawler file", filepath
            return []
            
        crawlers = file.readlines()
        file.close()
        crawlers_info = []
        for crawler in crawlers:
            if crawler.strip().startswith("#"):    # skip commended lines
                continue
            crawler_info = [a.strip() for a in crawler.split(",")]
            try:
                crawler_info[0] = base64.decodestring(crawler_info[0]+'\n')
            except:
                print_exc()
                continue
            crawlers_info.append(str2bin(crawler))
                    
        return crawlers_info

    def temporarilyAddCrawler(self, permid):
        """
        Because of security reasons we will not allow crawlers to be
        added to the crawler.txt list. This temporarilyAddCrawler
        method can be used to add one for the running session. Usefull
        for debugging and testing.
        """
        if not permid in self._crawler_list:
            self._crawler_list.append(permid)

    def getCrawlers(self):
        """
        returns a list with permids of crawlers
        """
        return self._crawler_list


        
class PreferenceDBHandler(BasicDBHandler):
    
    __single = None    # used for multithreaded singletons pattern
    lock = threading.Lock()
    
    def getInstance(*args, **kw):
        # Singleton pattern with double-checking
        if PreferenceDBHandler.__single is None:
            PreferenceDBHandler.lock.acquire()   
            try:
                if PreferenceDBHandler.__single is None:
                    PreferenceDBHandler(*args, **kw)
            finally:
                PreferenceDBHandler.lock.release()
        return PreferenceDBHandler.__single
    
    getInstance = staticmethod(getInstance)
    
    def __init__(self):
        if PreferenceDBHandler.__single is not None:
            raise RuntimeError, "PreferenceDBHandler is singleton"
        PreferenceDBHandler.__single = self
        db = SQLiteCacheDB.getInstance()
        BasicDBHandler.__init__(self,db, 'Preference') ## self,db,'Preference'
            
    def _getTorrentOwnersID(self, torrent_id):
        sql_get_torrent_owners_id = u"SELECT peer_id FROM Preference WHERE torrent_id==?"
        res = self._db.fetchall(sql_get_torrent_owners_id, (torrent_id,))
        return [t[0] for t in res]
    
    def getPrefList(self, permid, return_infohash=False):
        # get a peer's preference list of infohash or torrent_id according to return_infohash
        peer_id = self._db.getPeerID(permid)
        if peer_id is None:
            return []
        
        if not return_infohash:
            sql_get_peer_prefs_id = u"SELECT torrent_id FROM Preference WHERE peer_id==?"
            res = self._db.fetchall(sql_get_peer_prefs_id, (peer_id,))
            return [t[0] for t in res]
        else:
            sql_get_infohash = u"SELECT infohash FROM Torrent WHERE torrent_id IN (SELECT torrent_id FROM Preference WHERE peer_id==?)"
            res = self._db.fetchall(sql_get_infohash, (peer_id,))
            return [str2bin(t[0]) for t in res]
    
    def _deletePeer(self, permid=None, peer_id=None, commit=True):   # delete a peer from pref_db
        # should only be called by PeerDBHandler
        if peer_id is None:
            peer_id = self._db.getPeerID(permid)
            if peer_id is None:
                return
        
        self._db.delete(self.table_name, commit=commit, peer_id=peer_id)

    def addPreference(self, permid, infohash, data={}, commit=True):           
        # This function should be replaced by addPeerPreferences 
        # peer_permid and prefs are binaries, the peer must have been inserted in Peer table
        # Nicolas: did not change this function as it seems addPreference*s* is getting called
        peer_id = self._db.getPeerID(permid)
        if peer_id is None:
            print >> sys.stderr, 'PreferenceDBHandler: add preference of a peer which is not existed in Peer table', `permid`
            return
        
        sql_insert_peer_torrent = u"INSERT INTO Preference (peer_id, torrent_id) VALUES (?,?)"        
        torrent_id = self._db.getTorrentID(infohash)
        if not torrent_id:
            self._db.insertInfohash(infohash)
            torrent_id = self._db.getTorrentID(infohash)
        try:
            self._db.execute_write(sql_insert_peer_torrent, (peer_id, torrent_id), commit=commit)
        except Exception, msg:    # duplicated
            print_exc()
            
            

    def addPreferences(self, peer_permid, prefs, is_torrent_id=False, commit=True):
        # peer_permid and prefs are binaries, the peer must have been inserted in Peer table
        #
        # boudewijn: for buddycast version >= OLPROTO_VER_EIGTH the
        # prefs list may contain both strings (indicating an infohash)
        # or dictionaries (indicating an infohash with metadata)
        
        peer_id = self._db.getPeerID(peer_permid)
        if peer_id is None:
            print >> sys.stderr, 'PreferenceDBHandler: add preference of a peer which is not existed in Peer table', `peer_permid`
            return

        prefs = [type(pref) is str and {"infohash":pref} or pref
                 for pref
                 in prefs]
        
        if is_torrent_id:
            torrent_id_prefs = [(peer_id, 
                                 pref['torrent_id'], 
                                 pref.get('position', -1), 
                                 pref.get('reranking_strategy', -1)) 
                                for pref in prefs]
        else:
            # Nicolas: do not know why this would be called, but let's handle it smoothly
            torrent_id_prefs = []
            for pref in prefs:
                if type(pref)==dict:
                    infohash = pref["infohash"]
                else:
                    infohash = pref # Nicolas: from wherever this might come, we even handle old list of infohashes style
                torrent_id = self._db.getTorrentID(infohash)
                if not torrent_id:
                    self._db.insertInfohash(infohash)
                    torrent_id = self._db.getTorrentID(infohash)
                torrent_id_prefs.append((peer_id, torrent_id, -1, -1))
            
        sql_insert_peer_torrent = u"INSERT INTO Preference (peer_id, torrent_id, click_position, reranking_strategy) VALUES (?,?,?,?)"        
        if len(prefs) > 0:
            try:
                self._db.executemany(sql_insert_peer_torrent, torrent_id_prefs, commit=commit)
            except Exception, msg:    # duplicated
                print_exc()
                print >> sys.stderr, 'dbhandler: addPreferences:', Exception, msg
                
        # now, store search terms
        
        # Nicolas: if maximum number of search terms is exceeded, abort storing them.
        # Although this may seem a bit strict, this means that something different than a genuine Tribler client
        # is on the other side, so we might rather err on the side of caution here and simply let clicklog go.
        nums_of_search_terms = [len(pref.get('search_terms',[])) for pref in prefs]
        if max(nums_of_search_terms)>MAX_KEYWORDS_STORED:
            if DEBUG:
                print >>sys.stderr, "peer %d exceeds max number %d of keywords per torrent, aborting storing keywords"  % \
                                    (peer_id, MAX_KEYWORDS_STORED)
            return  
        
        all_terms_unclean = Set([])
        for pref in prefs:
            newterms = Set(pref.get('search_terms',[]))
            all_terms_unclean = all_terms_unclean.union(newterms)        
            
        all_terms = [] 
        for term in all_terms_unclean:
            cleanterm = ''
            for i in range(0,len(term)):
                c = term[i]
                if c.isalnum():
                    cleanterm += c
            if len(cleanterm)>0:
                all_terms.append(cleanterm)

        
        # maybe we haven't received a single key word, no need to loop again over prefs then
        if len(all_terms)==0:
            return
           
        termdb = TermDBHandler.getInstance()
        searchdb = SearchDBHandler.getInstance()
                
        # insert all unknown terms NOW so we can rebuild the index at once
        termdb.bulkInsertTerms(all_terms)         
        
        # get local term ids for terms.
        foreign2local = dict([(str(foreign_term), termdb.getTermID(foreign_term))
                              for foreign_term
                              in all_terms])        
        
        # process torrent data
        for pref in prefs:
            torrent_id = pref.get('torrent_id', None)
            search_terms = pref.get('search_terms', [])
            
            if search_terms==[]:
                continue
            if not torrent_id:
                if DEBUG:
                    print >> sys.stderr, "torrent_id not set, retrieving manually!"
                torrent_id = TorrentDBHandler.getInstance().getTorrentID(infohash)
                
            term_ids = [foreign2local[str(foreign)] for foreign in search_terms]
            searchdb.storeKeywordsByID(peer_id, torrent_id, term_ids, commit=False)
        if commit:
            searchdb.commit()
        
    def getAllEntries(self):
        """use with caution,- for testing purposes"""
        return self.getAll("rowid, peer_id, torrent_id, click_position,reranking_strategy", order_by="peer_id, torrent_id")


    def getRecentPeersPrefs(self, key, num=None):
        # get the recently seen peers' preference. used by buddycast
        sql = "select peer_id,torrent_id from Preference where peer_id in (select peer_id from Peer order by %s desc)"%key
        if num is not None:
             sql = sql[:-1] + " limit %d)"%num
        res = self._db.fetchall(sql)
        return res
    
    def getPositionScore(self, torrent_id, keywords):
        """returns a tuple (num, positionScore) stating how many times the torrent id was found in preferences,
           and the average position score, where each click at position i receives 1-(1/i) points"""
           
        if not keywords:
            return (0,0)
           
        term_db = TermDBHandler.getInstance()
        term_ids = [term_db.getTermID(keyword) for keyword in keywords]
        s_term_ids = str(term_ids).replace("[","(").replace("]",")").replace("L","")
        
        # we're not really interested in the peer_id here,
        # just make sure we don't count twice if we hit more than one keyword in a search
        # ... one might treat keywords a bit more strictly here anyway (AND instead of OR)
        sql = """
SELECT DISTINCT Preference.peer_id, Preference.click_position 
FROM Preference 
INNER JOIN ClicklogSearch 
ON 
    Preference.torrent_id = ClicklogSearch.torrent_id 
  AND 
    Preference.peer_id = ClicklogSearch.peer_id 
WHERE 
    ClicklogSearch.term_id IN %s 
  AND
    ClicklogSearch.torrent_id = %s""" % (s_term_ids, torrent_id)
        res = self._db.fetchall(sql)
        scores = [1.0-1.0/float(click_position+1) 
                  for (peer_id, click_position) 
                  in res 
                  if click_position>-1]
        if len(scores)==0:
            return (0,0)
        score = float(sum(scores))/len(scores)
        return (len(scores), score)

        
class TorrentDBHandler(BasicDBHandler):
    
    __single = None    # used for multithreaded singletons pattern
    lock = threading.Lock()
    
    def getInstance(*args, **kw):
        # Singleton pattern with double-checking
        if TorrentDBHandler.__single is None:
            TorrentDBHandler.lock.acquire()   
            try:
                if TorrentDBHandler.__single is None:
                    TorrentDBHandler(*args, **kw)
            finally:
                TorrentDBHandler.lock.release()
        return TorrentDBHandler.__single
    
    getInstance = staticmethod(getInstance)

    def __init__(self):
        if TorrentDBHandler.__single is not None:
            raise RuntimeError, "TorrentDBHandler is singleton"
        TorrentDBHandler.__single = self
        db = SQLiteCacheDB.getInstance()
        BasicDBHandler.__init__(self,db, 'Torrent') ## self,db,torrent
        
        self.mypref_db = MyPreferenceDBHandler.getInstance()
        
        self.status_table = {'good':1, 'unknown':0, 'dead':2}
        self.status_table.update(self._db.getTorrentStatusTable())
        self.id2status = dict([(x,y) for (y,x) in self.status_table.items()]) 
        self.torrent_dir = None
        # 0 - unknown
        # 1 - good
        # 2 - dead
        
        self.category_table  = {'Video':1,
                                'VideoClips':2,
                                'Audio':3,
                                'Compressed':4,
                                'Document':5,
                                'Picture':6,
                                'xxx':7,
                                'other':8,}
        self.category_table.update(self._db.getTorrentCategoryTable())
        self.category_table['unknown'] = 0 
        self.id2category = dict([(x,y) for (y,x) in self.category_table.items()])
        # 1 - Video
        # 2 - VideoClips
        # 3 - Audio
        # 4 - Compressed
        # 5 - Document
        # 6 - Picture
        # 7 - xxx
        # 8 - other
        
        self.src_table = self._db.getTorrentSourceTable()
        self.id2src = dict([(x,y) for (y,x) in self.src_table.items()])
        # 0 - ''    # local added
        # 1 - BC
        # 2,3,4... - URL of RSS feed
        self.keys = ['torrent_id', 'name', 'torrent_file_name',
                'length', 'creation_date', 'num_files', 'thumbnail',
                'insert_time', 'secret', 'relevance',
                'source_id', 'category_id', 'status_id',
                'num_seeders', 'num_leechers', 'comment']
        self.existed_torrents = Set()


        self.value_name = ['C.torrent_id', 'category_id', 'status_id', 'name', 'creation_date', 'num_files',
                      'num_leechers', 'num_seeders', 'length', 
                      'secret', 'insert_time', 'source_id', 'torrent_file_name',
                      'relevance', 'infohash', 'tracker', 'last_check']

    def register(self, category, torrent_dir):
        self.category = category
        self.torrent_dir = torrent_dir

    def getTorrentID(self, infohash):
        return self._db.getTorrentID(infohash)
    
    def getInfohash(self, torrent_id):
        return self._db.getInfohash(torrent_id)

    def hasTorrent(self, infohash):
        if infohash in self.existed_torrents:    #to do: not thread safe
            return True
        infohash_str = bin2str(infohash)
        existed = self._db.getOne('CollectedTorrent', 'torrent_id', infohash=infohash_str)
        if existed is None:
            return False
        else:
            self.existed_torrents.add(infohash)
            return True
    
    def addExternalTorrent(self, filename, source='BC', extra_info={}, metadata=None):
        infohash, torrent = self._readTorrentData(filename, source, extra_info, metadata)
        if infohash is None:
            return torrent
        if not self.hasTorrent(infohash):
            self._addTorrentToDB(infohash, torrent, commit=True)
            self.notifier.notify(NTFY_TORRENTS, NTFY_INSERT, infohash)

        return torrent

    def _readTorrentData(self, filename, source='BC', extra_info={}, metadata=None):
        # prepare data to insert into database
        try:
            if metadata is None:
                f = open(filename, 'rb')
                metadata = f.read()
                f.close()
            
            metainfo = bdecode(metadata)
        except Exception,msg:
            print >> sys.stderr, Exception,msg,`metadata`
            return None,None
        
        namekey = name2unicode(metainfo)  # convert info['name'] to type(unicode)
        info = metainfo['info']
        infohash = sha(bencode(info)).digest()

        torrent = {'infohash': infohash}
        torrent['torrent_file_name'] = os.path.split(filename)[1]
        torrent['name'] = info.get(namekey, '')
        
        length = 0
        nf = 0
        if info.has_key('length'):
            length = info.get('length', 0)
            nf = 1
        elif info.has_key('files'):
            for li in info['files']:
                nf += 1
                if li.has_key('length'):
                    length += li['length']
        torrent['length'] = length
        torrent['num_files'] = nf
        torrent['announce'] = metainfo.get('announce', '')
        torrent['announce-list'] = metainfo.get('announce-list', '')
        torrent['creation_date'] = metainfo.get('creation date', 0)
        
        torrent['comment'] = metainfo.get('comment', None)
        
        torrent["ignore_number"] = 0
        torrent["retry_number"] = 0
        torrent["num_seeders"] = extra_info.get('seeder', -1)
        torrent["num_leechers"] = extra_info.get('leecher', -1)
        other_last_check = extra_info.get('last_check_time', -1)
        if other_last_check >= 0:
            torrent["last_check_time"] = int(time()) - other_last_check
        else:
            torrent["last_check_time"] = 0
        torrent["status"] = self._getStatusID(extra_info.get('status', "unknown"))
        
        torrent["source"] = self._getSourceID(source)
        torrent["insert_time"] = long(time())

        torrent['category'] = self._getCategoryID(self.category.calculateCategory(metainfo, torrent['name']))
        torrent['secret'] = 0 # to do: check if torrent is secret
        torrent['relevance'] = 0.0
        thumbnail = 0
        if 'azureus_properties' in metainfo and 'Content' in metainfo['azureus_properties']:
            if metainfo['azureus_properties']['Content'].get('Thumbnail',''):
                thumbnail = 1
        torrent['thumbnail'] = thumbnail
        
        #if (torrent['category'] != []):
        #    print '### one torrent added from MetadataHandler: ' + str(torrent['category']) + ' ' + torrent['torrent_name'] + '###'
        return infohash, torrent
        
    def addInfohash(self, infohash, commit=True):
        if self._db.getTorrentID(infohash) is None:
            self._db.insert('Torrent', commit=commit, infohash=bin2str(infohash))

    def _getStatusID(self, status):
        return self.status_table.get(status.lower(), 0)

    def _getCategoryID(self, category_list):
        if len(category_list) > 0:
            category = category_list[0].lower()
            cat_int = self.category_table[category]
        else:
            cat_int = 0
        return cat_int

    def _getSourceID(self, src):
        if src in self.src_table:
            src_int = self.src_table[src]
        else:
            src_int = self._insertNewSrc(src)    # add a new src, e.g., a RSS feed
            self.src_table[src] = src_int
            self.id2src[src_int] = src
        return src_int

    def _addTorrentToDB(self, infohash, data, commit=True):
        torrent_id = self._db.getTorrentID(infohash)
        if torrent_id is None:    # not in db
            infohash_str = bin2str(infohash)
            self._db.insert('Torrent', 
                        commit=True,    # must commit to get the torrent id
                        infohash = infohash_str,
                        name = dunno2unicode(data['name']),
                        torrent_file_name = data['torrent_file_name'],
                        length = data['length'], 
                        creation_date = data['creation_date'], 
                        num_files = data['num_files'], 
                        thumbnail = data['thumbnail'],
                        insert_time = data['insert_time'], 
                        secret = data['secret'], 
                        relevance = data['relevance'],
                        source_id = data['source'], 
                        category_id = data['category'], 
                        status_id = data['status'],
                        num_seeders = data['num_seeders'], 
                        num_leechers = data['num_leechers'], 
                        comment = dunno2unicode(data['comment']))
            torrent_id = self._db.getTorrentID(infohash)
        else:    # infohash in db
            where = 'torrent_id = %d'%torrent_id
            self._db.update('Torrent', where = where,
                            commit=False,
                            name = dunno2unicode(data['name']),
                            torrent_file_name = data['torrent_file_name'],
                            length = data['length'], 
                            creation_date = data['creation_date'], 
                            num_files = data['num_files'], 
                            thumbnail = data['thumbnail'],
                            insert_time = data['insert_time'], 
                            secret = data['secret'], 
                            relevance = data['relevance'],
                            source_id = data['source'], 
                            category_id = data['category'], 
                            status_id = data['status'],
                            num_seeders = data['num_seeders'], 
                            num_leechers = data['num_leechers'], 
                            comment = dunno2unicode(data['comment']))
        
        self._addTorrentTracker(torrent_id, data, commit=False)
        if commit:
            self.commit()    
        self._db.show_execute = False
        return torrent_id
    
    def _insertNewSrc(self, src, commit=True):
        desc = ''
        if src.startswith('http') and src.endswith('xml'):
            desc = 'RSS'
        self._db.insert('TorrentSource', commit=commit, name=src, description=desc)
        src_id = self._db.getOne('TorrentSource', 'source_id', name=src)
        return src_id

    def _addTorrentTracker(self, torrent_id, data, add_all=False, commit=True):
        # Set add_all to True if you want to put all multi-trackers into db.
        # In the current version (4.2) only the main tracker is used.
        exist = self._db.getOne('TorrentTracker', 'tracker', torrent_id=torrent_id)
        if exist:
            return
        
        announce = data['announce']
        ignore_number = data['ignore_number']
        retry_number = data['retry_number']
        last_check_time = data['last_check_time']
        
        announce_list = data['announce-list']
        
        sql_insert_torrent_tracker = """
        INSERT INTO TorrentTracker
        (torrent_id, tracker, announce_tier, 
        ignored_times, retried_times, last_check)
        VALUES (?,?,?, ?,?,?)
        """
        
        values = [(torrent_id, announce, 1, ignore_number, retry_number, last_check_time)]
        # each torrent only has one announce with tier number 1
        tier_num = 2
        trackers = {announce:None}
        if add_all:
            for tier in announce_list:
                for tracker in tier:
                    if tracker in trackers:
                        continue
                    value = (torrent_id, tracker, tier_num, 0, 0, 0)
                    values.append(value)
                    trackers[tracker] = None
                tier_num += 1
            
        self._db.executemany(sql_insert_torrent_tracker, values, commit=commit)
        
    def updateTorrent(self, infohash, commit=True, **kw):    # watch the schema of database
        if 'category' in kw:
            cat_id = self._getCategoryID(kw.pop('category'))
            kw['category_id'] = cat_id
        if 'status' in kw:
            status_id = self._getStatusID(kw.pop('status'))
            kw['status_id'] = status_id
        if 'progress' in kw:
            self.mypref_db.updateProgress(infohash, kw.pop('progress'), commit=False)# commit at end of function
        if 'seeder' in kw:
            kw['num_seeders'] = kw.pop('seeder')
        if 'leecher' in kw:
            kw['num_leechers'] = kw.pop('leecher')
        if 'last_check_time' in kw or 'ignore_number' in kw or 'retry_number' in kw \
          or 'retried_times' in kw or 'ignored_times' in kw:
            self.updateTracker(infohash, kw, commit=False)
        
        for key in kw.keys():
            if key not in self.keys:
                kw.pop(key)
                
        if len(kw) > 0:
            infohash_str = bin2str(infohash)
            where = "infohash='%s'"%infohash_str
            self._db.update(self.table_name, where, commit=False, **kw)
            
        if commit:
            self.commit()
            # to.do: update the torrent panel's number of seeders/leechers 
        self.notifier.notify(NTFY_TORRENTS, NTFY_UPDATE, infohash)
        
    def updateTracker(self, infohash, kw, tier=1, tracker=None, commit=True):
        torrent_id = self._db.getTorrentID(infohash)
        if torrent_id is None:
            return
        update = {}
        assert type(kw) == dict and kw, 'updateTracker error: kw should be filled dict, but is: %s' % kw
        if 'last_check_time' in kw:
            update['last_check'] = kw.pop('last_check_time')
        if 'ignore_number' in kw:
            update['ignored_times'] = kw.pop('ignore_number')
        if 'ignored_times' in kw:
            update['ignored_times'] = kw.pop('ignored_times')
        if 'retry_number' in kw:
            update['retried_times'] = kw.pop('retry_number')
        if 'retried_times' in kw:
            update['retried_times'] = kw.pop('retried_times')
            
        if tracker is None:
            where = 'torrent_id=%d AND announce_tier=%d'%(torrent_id, tier)
        else:
            where = 'torrent_id=%d AND tracker=%s'%(torrent_id, repr(tracker))
        self._db.update('TorrentTracker', where, commit=commit, **update)

    def deleteTorrent(self, infohash, delete_file=False, commit = True):
        if not self.hasTorrent(infohash):
            return False
        
        if self.mypref_db.hasMyPreference(infohash):  # don't remove torrents in my pref
            return False

        if delete_file:
            deleted = self.eraseTorrentFile(infohash)
        else:
            deleted = True
        
        if deleted:
            self._deleteTorrent(infohash, commit=commit)
            
        self.notifier.notify(NTFY_TORRENTS, NTFY_DELETE, infohash)
        return deleted

    def _deleteTorrent(self, infohash, keep_infohash=True, commit=True):
        torrent_id = self._db.getTorrentID(infohash)
        if torrent_id is not None:
            if keep_infohash:
                self._db.update(self.table_name, where="torrent_id=%d"%torrent_id, commit=commit, torrent_file_name=None)
            else:
                self._db.delete(self.table_name, commit=commit, torrent_id=torrent_id)
            if infohash in self.existed_torrents:
                self.existed_torrents.remove(infohash)
            self._db.delete('TorrentTracker', commit=commit, torrent_id=torrent_id)
            #print '******* delete torrent', torrent_id, `infohash`, self.hasTorrent(infohash)
            
    def eraseTorrentFile(self, infohash):
        torrent_id = self._db.getTorrentID(infohash)
        if torrent_id is not None:
            torrent_dir = self.getTorrentDir()
            torrent_name = self.getOne('torrent_file_name', torrent_id=torrent_id)
            src = os.path.join(torrent_dir, torrent_name)
            if not os.path.exists(src):    # already removed
                return True
            
            try:
                os.remove(src)
            except Exception, msg:
                print >> sys.stderr, "cachedbhandler: failed to erase torrent", src, Exception, msg
                return False
        
        return True
            
    def getTracker(self, infohash, tier=0):
        torrent_id = self._db.getTorrentID(infohash)
        if torrent_id is not None:
            sql = "SELECT tracker, announce_tier FROM TorrentTracker WHERE torrent_id==%d"%torrent_id
            if tier > 0:
                sql += " AND announce_tier<=%d"%tier
            return self._db.fetchall(sql)
    
    def getTorrentDir(self):
        return self.torrent_dir
    
    
    def getTorrent(self, infohash, keys=None, include_mypref=True):
        # to do: replace keys like source -> source_id and status-> status_id ??
        
        if keys is None:
            keys = deepcopy(self.value_name)
            #('torrent_id', 'category_id', 'status_id', 'name', 'creation_date', 'num_files',
            # 'num_leechers', 'num_seeders',   'length', 
            # 'secret', 'insert_time', 'source_id', 'torrent_file_name',
            # 'relevance', 'infohash', 'torrent_id')
        else:
            keys = list(keys)
        where = 'C.torrent_id = T.torrent_id and announce_tier=1 '
        
        res = self._db.getOne('CollectedTorrent C, TorrentTracker T', keys, where=where, infohash=bin2str(infohash))
        if not res:
            return None
        torrent = dict(zip(keys, res))
        if 'source_id' in torrent:
            torrent['source'] = self.id2src[torrent['source_id']]
            del torrent['source_id']
        if 'category_id' in torrent:
            torrent['category'] = [self.id2category[torrent['category_id']]]
            del torrent['category_id']
        if 'status_id' in torrent:
            torrent['status'] = self.id2status[torrent['status_id']]
            del torrent['status_id']
        torrent['infohash'] = infohash
        if 'last_check' in torrent:
            torrent['last_check_time'] = torrent['last_check']
            del torrent['last_check']
        
        if include_mypref:
            tid = torrent['C.torrent_id']
            stats = self.mypref_db.getMyPrefStats(tid)
            del torrent['C.torrent_id']
            if stats:
                torrent['myDownloadHistory'] = True
                torrent['creation_time'] = stats[tid][0]
                torrent['progress'] = stats[tid][1]
                torrent['destination_path'] = stats[tid][2]
                
                
        return torrent

    def getNumberTorrents(self, category_name = 'all', library = False):
        table = 'CollectedTorrent'
        value = 'count(torrent_id)'
        where = '1 '

        if category_name != 'all':
            where += ' and category_id= %d' % self.category_table.get(category_name.lower(), -1) # unkown category_name returns no torrents
        if library:
            where += ' and torrent_id in (select torrent_id from MyPreference)'
        else:
            where += ' and status_id=%d ' % self.status_table['good']
            # add familyfilter
            where += self.category.get_family_filter_sql(self._getCategoryID)
        
        number = self._db.getOne(table, value, where)
        if not number:
            number = 0
        return number
    
    def getTorrents(self, category_name = 'all', range = None, library = False, sort = None, reverse = False):
        """
        get Torrents of some category and with alive status (opt. not in family filter)
        
        @return Returns a list of dicts with keys: 
            torrent_id, infohash, name, category, status, creation_date, num_files, num_leechers, num_seeders,
            length, secret, insert_time, source, torrent_filename, relevance, simRank, tracker, last_check
            (if in library: myDownloadHistory, download_started, progress, dest_dir)
            
        """
        
        #print >> sys.stderr, 'TorrentDBHandler: getTorrents(%s, %s, %s, %s, %s)' % (category_name, range, library, sort, reverse)
        s = time()
        
        value_name = deepcopy(self.value_name)
            
        where = 'T.torrent_id = C.torrent_id and announce_tier=1 '
        
        if category_name != 'all':
            where += ' and category_id= %d' % self.category_table.get(category_name.lower(), -1) # unkown category_name returns no torrents
        if library:
            if sort in value_name:
                where += ' and C.torrent_id in (select torrent_id from MyPreference)'
            else:
                value_name[0] = 'C.torrent_id'
                where += ' and C.torrent_id = M.torrent_id and announce_tier=1'
        else:
            where += ' and status_id=%d ' % self.status_table['good'] # if not library, show only good files
            # add familyfilter
            where += self.category.get_family_filter_sql(self._getCategoryID)
        if range:
            offset= range[0]
            limit = range[1] - range[0]
        else:
            limit = offset = None
        if sort:
            # Arno, 2008-10-6: buggy: not reverse???
            desc = (reverse) and 'desc' or ''
            if sort in ('name'):
                order_by = ' lower(%s) %s' % (sort, desc)
            else:
                order_by = ' %s %s' % (sort, desc)
        else:
            order_by = None
            
        #print >>sys.stderr,"TorrentDBHandler: GET TORRENTS val",value_name,"where",where,"limit",limit,"offset",offset,"order",order_by
        #print_stack
        
        # Must come before query
        ranks = self.getRanks()

        #self._db.show_execute = True
        if library and sort not in value_name:
            res_list = self._db.getAll('CollectedTorrent C, MyPreference M, TorrentTracker T', value_name, where, limit=limit, offset=offset, order_by=order_by)
        else:
            res_list = self._db.getAll('CollectedTorrent C, TorrentTracker T', value_name, where, limit=limit, offset=offset, order_by=order_by)
        #self._db.show_execute = False
        
        mypref_stats = self.mypref_db.getMyPrefStats()
        
        #print >>sys.stderr,"TorrentDBHandler: getTorrents: getAll returned ###################",len(res_list)
        
        torrent_list = self.valuelist2torrentlist(value_name,res_list,ranks,mypref_stats)
        del res_list
        del mypref_stats
        return torrent_list

    def valuelist2torrentlist(self,value_name,res_list,ranks,mypref_stats):
        
        torrent_list = []
        for item in res_list:
            value_name[0] = 'torrent_id'
            torrent = dict(zip(value_name, item))
            
            try:
                torrent['source'] = self.id2src[torrent['source_id']]
            except:
                print_exc()
                # Arno: RSS subscription and id2src issue
                torrent['source'] = 'http://some/RSS/feed'
            
            torrent['category'] = [self.id2category[torrent['category_id']]]
            torrent['status'] = self.id2status[torrent['status_id']]
            torrent['simRank'] = ranksfind(ranks,torrent['infohash'])
            torrent['infohash'] = str2bin(torrent['infohash'])
            #torrent['num_swarm'] = torrent['num_seeders'] + torrent['num_leechers']
            torrent['last_check_time'] = torrent['last_check']
            del torrent['last_check']
            del torrent['source_id']
            del torrent['category_id']
            del torrent['status_id']
            torrent_id = torrent['torrent_id']
            if mypref_stats is not None and torrent_id in mypref_stats:
                # add extra info for torrent in mypref
                torrent['myDownloadHistory'] = True
                data = mypref_stats[torrent_id]  #(create_time,progress,destdir)
                torrent['download_started'] = data[0]
                torrent['progress'] = data[1]
                torrent['destdir'] = data[2]
            
            #print >>sys.stderr,"TorrentDBHandler: GET TORRENTS",`torrent`
                
            torrent_list.append(torrent)
        return  torrent_list
        
    def getRanks(self,):
        value_name = 'infohash'
        order_by = 'relevance desc'
        rankList_size = 20
        where = 'status_id=%d ' % self.status_table['good']
        res_list = self._db.getAll('Torrent', value_name, where = where, limit=rankList_size, order_by=order_by)
        return [a[0] for a in res_list]

    def getNumberCollectedTorrents(self): 
        #return self._db.size('CollectedTorrent')
        return self._db.getOne('CollectedTorrent', 'count(torrent_id)')

    def freeSpace(self, torrents2del):
#        if torrents2del > 100:  # only delete so many torrents each time
#            torrents2del = 100
        sql = """
            select torrent_file_name, torrent_id, infohash, relevance,
                min(relevance,2500) +  min(500,num_leechers) + 4*min(500,num_seeders) - (max(0,min(500,(%d-creation_date)/86400)) ) as weight
            from CollectedTorrent
            where  torrent_id not in (select torrent_id from MyPreference)
            order by weight  
            limit %d  
        """ % (int(time()), torrents2del)
        res_list = self._db.fetchall(sql)
        if len(res_list) == 0: 
            return False
        
        # delete torrents from db
        sql_del_torrent = "delete from Torrent where torrent_id=?"
        sql_del_tracker = "delete from TorrentTracker where torrent_id=?"
        sql_del_pref = "delete from Preference where torrent_id=?"
        tids = [(torrent_id,) for torrent_file_name, torrent_id, infohash, relevance, weight in res_list]

        self._db.executemany(sql_del_torrent, tids, commit=False)
        self._db.executemany(sql_del_tracker, tids, commit=False)
        self._db.executemany(sql_del_pref, tids, commit=False)
        
        self._db.commit()
        
        # but keep the infohash in db to maintain consistence with preference db
        #torrent_id_infohashes = [(torrent_id,infohash_str,relevance) for torrent_file_name, torrent_id, infohash_str, relevance, weight in res_list]
        #sql_insert =  "insert into Torrent (torrent_id, infohash, relevance) values (?,?,?)"
        #self._db.executemany(sql_insert, torrent_id_infohashes, commit=True)
        
        torrent_dir = self.getTorrentDir()
        deleted = 0 # deleted any file?
        for torrent_file_name, torrent_id, infohash, relevance, weight in res_list:
            torrent_path = os.path.join(torrent_dir, torrent_file_name)
            try:
                os.remove(torrent_path)
                print >> sys.stderr, "Erase torrent:", os.path.basename(torrent_path)
                deleted += 1
            except Exception, msg:
                #print >> sys.stderr, "Error in erase torrent", Exception, msg
                pass
        
        self.notifier.notify(NTFY_TORRENTS, NTFY_DELETE, str2bin(infohash)) # refresh gui
        
        return deleted

    def hasMetaData(self, infohash):
        return self.hasTorrent(infohash)
    
    def getTorrentRelevances(self, tids):
        sql = 'SELECT torrent_id, relevance from Torrent WHERE torrent_id in ' + str(tuple(tids))
        return self._db.fetchall(sql)
    
    def updateTorrentRelevance(self, infohash, relevance):
        self.updateTorrent(infohash, relevance=relevance)

    def updateTorrentRelevances(self, tid_rel_pairs, commit=True):
        if len(tid_rel_pairs) > 0:
            sql_update_sims = 'UPDATE Torrent SET relevance=? WHERE torrent_id=?'
            self._db.executemany(sql_update_sims, tid_rel_pairs, commit=commit)
        
    def searchNames(self,kws):
        """ Get all torrents (good and bad) that have the specified keywords in 
        their name.  Return a list of dictionaries. Each dict is in the 
        NEWDBSTANDARD format.
        @param kws A list of keyword strings
        @return A list of dictionaries.
        """ 
        
        mypref_stats = self.mypref_db.getMyPrefStats()

        where = 'C.torrent_id = T.torrent_id and announce_tier=1'        
        for i in range(len(kws)):
            kw = kws[i]
            # Strip special chars. Note that s.translate() does special stuff for Unicode, which we don't want
            cleankw = ''
            for i in range(0,len(kw)):
                c = kw[i]
                if c.isalnum():
                    cleankw += c
            
            where += ' and name like "%'+cleankw+'%"'

        value_name = copy(self.value_name)
        if 'torrent_id' in value_name:
            index = value_name.index('torrent_id')
            value_name.remove('torrent_id')
            value_name.insert(index, 'C.torrent_id')
            
        #print >>sys.stderr,"torrent_db: searchNames: where",where
        res_list = self._db.getAll('CollectedTorrent C, TorrentTracker T', value_name, where)
        #print >>sys.stderr,"torrent_db: searchNames: res",`res_list`
        
        torrent_list = self.valuelist2torrentlist(value_name,res_list,None,mypref_stats)
        del res_list
        del mypref_stats
        
        return torrent_list
            

    def selectTorrentToCollect(self, permid, candidate_list=None):
        """ select a torrent to collect from a given candidate list
        If candidate_list is not present or None, all torrents of 
        this peer will be used for sampling.
        Return: the infohashed of selected torrent
        """
        
        if candidate_list is None:
            sql = """
                select infohash 
                from Torrent,Peer,Preference 
                where Peer.permid==?
                      and Peer.peer_id==Preference.peer_id 
                      and Torrent.torrent_id==Preference.torrent_id 
                      and torrent_file_name is NULL 
                order by relevance desc 
            """
            permid_str = bin2str(permid)
            res = self._db.fetchone(sql, (permid_str,))
        else:
            cand_str = [bin2str(infohash) for infohash in candidate_list]
            s = repr(cand_str).replace('[','(').replace(']',')')
            sql = 'select infohash from Torrent where torrent_file_name is NULL and infohash in ' + s
            sql += ' order by relevance desc'
            res = self._db.fetchone(sql)
        if res is None:
            return None
        return str2bin(res)
        
    def selectTorrentToCheck(self, policy='random', infohash=None, return_value=None):    # for tracker checking
        """ select a torrent to update tracker info (number of seeders and leechers)
        based on the torrent checking policy.
        RETURN: a dictionary containing all useful info.

        Policy 1: Random [policy='random']
           Randomly select a torrent to collect (last_check < 5 min ago)
        
        Policy 2: Oldest (unknown) first [policy='oldest']
           Select the non-dead torrent which was not been checked for the longest time (last_check < 5 min ago)
        
        Policy 3: Popular first [policy='popular']
           Select the non-dead most popular (3*num_seeders+num_leechers) one which has not been checked in last N seconds 
           (The default N = 4 hours, so at most 4h/torrentchecking_interval popular peers)
        """
        
        #import threading
        #print >> sys.stderr, "****** selectTorrentToCheck", threading.currentThread().getName()
        
        if infohash is None:
            # create a view?
            sql = """select T.torrent_id, ignored_times, retried_times, torrent_file_name, infohash, status_id, num_seeders, num_leechers, last_check 
                     from CollectedTorrent T, TorrentTracker TT
                     where TT.torrent_id=T.torrent_id and announce_tier=1 """
            if policy.lower() == 'random':
                ntorrents = self.getNumberCollectedTorrents()
                if ntorrents == 0:
                    rand_pos = 0
                else:                    
                    rand_pos = randint(0, ntorrents-1)
                last_check_threshold = int(time()) - 300
                sql += """and last_check < %d 
                        limit 1 offset %d """%(last_check_threshold, rand_pos)
            elif policy.lower() == 'oldest':
                last_check_threshold = int(time()) - 300
                sql += """ and last_check < %d and status_id <> 2
                         order by last_check
                         limit 1 """%last_check_threshold
            elif policy.lower() == 'popular':
                last_check_threshold = int(time()) - 4*60*60
                sql += """ and last_check < %d and status_id <> 2 
                         order by 3*num_seeders+num_leechers desc
                         limit 1 """%last_check_threshold
            res = self._db.fetchone(sql)
        else:
            sql = """select T.torrent_id, ignored_times, retried_times, torrent_file_name, infohash, status_id, num_seeders, num_leechers, last_check 
                     from CollectedTorrent T, TorrentTracker TT
                     where TT.torrent_id=T.torrent_id and announce_tier=1
                     and infohash=? 
                  """
            infohash_str = bin2str(infohash)
            res = self._db.fetchone(sql, (infohash_str,))
        
        if res:
            torrent_file_name = res[3]
            torrent_dir = self.getTorrentDir()
            torrent_path = os.path.join(torrent_dir, torrent_file_name)
            if res is not None:
                res = {'torrent_id':res[0], 
                       'ignored_times':res[1], 
                       'retried_times':res[2], 
                       'torrent_path':torrent_path,
                       'infohash':str2bin(res[4])
                      }
            return_value['torrent'] = res
        return_value['event'].set()


    def getTorrentsFromSource(self,source):
        """ Get all torrents from the specified Subscription source. 
        Return a list of dictionaries. Each dict is in the NEWDBSTANDARD format.
        """
        id = self._getSourceID(source)

        where = 'C.source_id = %d and C.torrent_id = T.torrent_id and announce_tier=1' % (id)
        # add familyfilter
        where += self.category.get_family_filter_sql(self._getCategoryID)
        
        value_name = deepcopy(self.value_name)

        res_list = self._db.getAll('Torrent C, TorrentTracker T', value_name, where)
        
        torrent_list = self.valuelist2torrentlist(value_name,res_list,None,None)
        del res_list
        
        return torrent_list

        
    def setSecret(self,infohash,secret):
        kw = {'secret': secret}
        self.updateTorrent(infohash, updateFlag=True, **kw)
        

class MyPreferenceDBHandler(BasicDBHandler):
    
    __single = None    # used for multithreaded singletons pattern
    lock = threading.Lock()
    
    def getInstance(*args, **kw):
        # Singleton pattern with double-checking
        if MyPreferenceDBHandler.__single is None:
            MyPreferenceDBHandler.lock.acquire()   
            try:
                if MyPreferenceDBHandler.__single is None:
                    MyPreferenceDBHandler(*args, **kw)
            finally:
                MyPreferenceDBHandler.lock.release()
        return MyPreferenceDBHandler.__single
    
    getInstance = staticmethod(getInstance)
    
    def __init__(self):
        if MyPreferenceDBHandler.__single is not None:
            raise RuntimeError, "MyPreferenceDBHandler is singleton"
        MyPreferenceDBHandler.__single = self
        db = SQLiteCacheDB.getInstance()
        BasicDBHandler.__init__(self,db, 'MyPreference') ## self,db,'MyPreference'

        self.status_table = {'good':1, 'unknown':0, 'dead':2}
        self.status_table.update(self._db.getTorrentStatusTable())
        self.status_good = self.status_table['good']
        self.recent_preflist = None
        self.recent_preflist_with_clicklog = None
        self.rlock = threading.RLock()
        
        
    def loadData(self):
        self.rlock.acquire()
        try:
            self.recent_preflist = self._getRecentLivePrefList()
            self.recent_preflist_with_clicklog = self._getRecentLivePrefListWithClicklog()
        finally:
            self.rlock.release()
                
    def getMyPrefList(self, order_by=None):
        res = self.getAll('torrent_id', order_by=order_by)
        return [p[0] for p in res]

    def getMyPrefListInfohash(self):
        sql = 'select infohash from Torrent where torrent_id in (select torrent_id from MyPreference)'
        res = self._db.fetchall(sql)
        return [str2bin(p[0]) for p in res]
    
    def getMyPrefStats(self, torrent_id=None):
        # get the full {torrent_id:(create_time,progress,destdir)}
        value_name = ('torrent_id','creation_time','progress','destination_path')
        if torrent_id is not None:
            where = 'torrent_id=%s' % torrent_id
        else:
            where = None
        res = self.getAll(value_name, where)
        mypref_stats = {}
        for pref in res:
            torrent_id,creation_time,progress,destination_path = pref
            mypref_stats[torrent_id] = (creation_time,progress,destination_path)
        return mypref_stats
        
    def getCreationTime(self, infohash):
        torrent_id = self._db.getTorrentID(infohash)
        if torrent_id is not None:
            ct = self.getOne('creation_time', torrent_id=torrent_id)
            return ct
        else:
            return None

    def getRecentLivePrefListWithClicklog(self, num=0):
        """returns OL 8 style preference list: a list of lists, with each of the inner lists
           containing infohash, search terms, click position, and reranking strategy"""
           
        if self.recent_preflist_with_clicklog is None:
            self.rlock.acquire()
            try:
                if self.recent_preflist_with_clicklog is None:
                    self.recent_preflist_with_clicklog = self._getRecentLivePrefListWithClicklog()
            finally:
                self.rlock.release()
        if num > 0:
            return self.recent_preflist_with_clicklog[:num]
        else:
            return self.recent_preflist_with_clicklog  

        
    def getRecentLivePrefList(self, num=0):
        if self.recent_preflist is None:
            self.rlock.acquire()
            try:
                if self.recent_preflist is None:
                    self.recent_preflist = self._getRecentLivePrefList()
            finally:
                self.rlock.release()
        if num > 0:
            return self.recent_preflist[:num]
        else:
            return self.recent_preflist


        
    def addClicklogToMyPreference(self, infohash, clicklog_data, commit=True):
        torrent_id = self._db.getTorrentID(infohash)
        clicklog_already_stored = False # equivalent to hasMyPreference TODO
        if torrent_id is None or clicklog_already_stored:
            return False

        d = {}
        # copy those elements of the clicklog data which are used in the update command
        for clicklog_key in ["click_position", "reranking_strategy"]: 
            if clicklog_key in clicklog_data: 
                d[clicklog_key] = clicklog_data[clicklog_key]
                                
        if d=={}:
            if DEBUG:
                print >> sys.stderr, "no updatable information given to addClicklogToMyPreference"
        else:
            if DEBUG:
                print >> sys.stderr, "addClicklogToMyPreference: updatable clicklog data: %s" % d
            self._db.update(self.table_name, 'torrent_id=%d' % torrent_id, commit=commit, **d)
                
        # have keywords stored by SearchDBHandler
        if 'keywords' in clicklog_data:
            if not clicklog_data['keywords']==[]:
                searchdb = SearchDBHandler.getInstance() 
                searchdb.storeKeywords(peer_id=0, 
                                       torrent_id=torrent_id, 
                                       terms=clicklog_data['keywords'], 
                                       commit=commit)   
 



            

                    
        
    def _getRecentLivePrefListWithClicklog(self, num=0):
        """returns a list containing a list for each torrent: [infohash, [seach terms], click position, reranking strategy]"""
        
        sql = """
        select infohash, click_position, reranking_strategy, m.torrent_id from MyPreference m, Torrent t 
        where m.torrent_id == t.torrent_id 
        and status_id == %d
        order by creation_time desc
        """ % self.status_good
        
        recent_preflist_with_clicklog = self._db.fetchall(sql)
        if recent_preflist_with_clicklog is None:
            recent_preflist_with_clicklog = []
        else:
            recent_preflist_with_clicklog = [[str2bin(t[0]),
                                              t[3],   # insert search terms in next step, only for those actually required, store torrent id for now
                                              t[1], # click position
                                              t[2]]  # reranking strategy
                                             for t in recent_preflist_with_clicklog]

        if num != 0:
            recent_preflist_with_clicklog = recent_preflist_with_clicklog[:num]

        # now that we only have those torrents left in which we are actually interested, 
        # replace torrent id by user's search terms for torrent id
        termdb = TermDBHandler.getInstance()
        searchdb = SearchDBHandler.getInstance()
        for pref in recent_preflist_with_clicklog:
            torrent_id = pref[1]
            search_terms = searchdb.getMyTorrentSearchTerms(torrent_id)
            pref[1] = [termdb.getTerm(search_term) for search_term in search_terms]            

        return recent_preflist_with_clicklog
    
    
    def _getRecentLivePrefList(self, num=0):    # num = 0: all files
        # get recent and live torrents
        sql = """
        select infohash from MyPreference m, Torrent t 
        where m.torrent_id == t.torrent_id 
        and status_id == %d
        order by creation_time desc
        """ % self.status_good

        recent_preflist = self._db.fetchall(sql)
        if recent_preflist is None:
            recent_preflist = []
        else:
            recent_preflist = [str2bin(t[0]) for t in recent_preflist]

        if num != 0:
            return recent_preflist[:num]
        else:
            return recent_preflist

    def hasMyPreference(self, infohash):
        torrent_id = self._db.getTorrentID(infohash)
        if torrent_id is None:
            return False
        res = self.getOne('torrent_id', torrent_id=torrent_id)
        if res is not None:
            return True
        else:
            return False
            
    def addMyPreference(self, infohash, data, commit=True):
        # keys in data: destination_path, progress, creation_time, torrent_id
        torrent_id = self._db.getTorrentID(infohash)
        if torrent_id is None or self.hasMyPreference(infohash):
            # Arno, 2009-03-09: Torrent already exists in myrefs.
            # Hack for hiding from lib while keeping in myprefs.
            # see standardOverview.removeTorrentFromLibrary()
            #
            self.updateDestDir(infohash,data.get('destination_path'),commit=commit)
            return False
        d = {}
        d['destination_path'] = data.get('destination_path')
        d['progress'] = data.get('progress', 0)
        d['creation_time'] = data.get('creation_time', int(time()))
        d['torrent_id'] = torrent_id
        self._db.insert(self.table_name, commit=commit, **d)
        self.notifier.notify(NTFY_MYPREFERENCES, NTFY_INSERT, infohash)
        self.rlock.acquire()
        try:
            if self.recent_preflist is None:
                self.recent_preflist = self._getRecentLivePrefList()
            else:
                self.recent_preflist.insert(0, infohash)
        finally:
            self.rlock.release()
        return True

    def deletePreference(self, infohash, commit=True):
        # Arno: when deleting a preference, you may also need to do
        # some stuff in BuddyCast: see delMyPref()
        torrent_id = self._db.getTorrentID(infohash)
        if torrent_id is None:
            return
        self._db.delete(self.table_name, commit=commit, **{'torrent_id':torrent_id})
        self.notifier.notify(NTFY_MYPREFERENCES, NTFY_DELETE, infohash)
        self.rlock.acquire()
        try:
            if self.recent_preflist is not None and infohash in self.recent_preflist:
                self.recent_preflist.remove(infohash)
        finally:
            self.rlock.release()
            
            
    def updateProgress(self, infohash, progress, commit=True):
        torrent_id = self._db.getTorrentID(infohash)
        if torrent_id is None:
            return
        self._db.update(self.table_name, 'torrent_id=%d'%torrent_id, commit=commit, progress=progress)
        #print >> sys.stderr, '********* update progress', `infohash`, progress, commit

    def getAllEntries(self):
        """use with caution,- for testing purposes"""
        return self.getAll("torrent_id, click_position, reranking_strategy", order_by="torrent_id")

    def updateDestDir(self, infohash, destdir, commit=True):
        torrent_id = self._db.getTorrentID(infohash)
        if torrent_id is None:
            return
        self._db.update(self.table_name, 'torrent_id=%d'%torrent_id, commit=commit, destination_path=destdir)
    

#    def getAllTorrentCoccurrence(self):
#        # should be placed in PreferenceDBHandler, but put here to be convenient for TorrentCollecting
#        sql = """select torrent_id, count(torrent_id) as coocurrency from Preference where peer_id in
#            (select peer_id from Preference where torrent_id in 
#            (select torrent_id from MyPreference)) and torrent_id not in 
#            (select torrent_id from MyPreference)
#            group by torrent_id
#            """
#        coccurrence = dict(self._db.fetchall(sql))
#        return coccurrence

        
class BarterCastDBHandler(BasicDBHandler):

    __single = None    # used for multithreaded singletons pattern
    lock = threading.Lock()
    
    def getInstance(*args, **kw):
        
        if BarterCastDBHandler.__single is None:
            BarterCastDBHandler.lock.acquire()   
            try:
                if BarterCastDBHandler.__single is None:
                    BarterCastDBHandler(*args, **kw)
            finally:
                BarterCastDBHandler.lock.release()
        return BarterCastDBHandler.__single
    
    getInstance = staticmethod(getInstance)

    def __init__(self):
        BarterCastDBHandler.__single = self
        db = SQLiteCacheDB.getInstance()
        BasicDBHandler.__init__(self, db,'BarterCast') ## self,db,'BarterCast'
        self.peer_db = PeerDBHandler.getInstance()
        
        # create the maxflow network
        self.network = Network({})
        self.update_network()
                   
        if DEBUG:
            print >> sys.stderr, "bartercastdb: MyPermid is ", self.my_permid

        
    ##def registerSession(self, session):
    ##    self.session = session

        # Retrieve MyPermid
    ##    self.my_permid = session.get_permid()


    def registerSession(self, session):
        self.session = session

        # Retrieve MyPermid
        self.my_permid = session.get_permid()

        if self.my_permid is None:
            raise ValueError('Cannot get permid from Session')

        # Keep administration of total upload and download
        # (to include in BarterCast message)
        self.my_peerid = self.getPeerID(self.my_permid)
        
        if self.my_peerid != None:
            where = "peer_id_from=%s" % (self.my_peerid)
            item = self.getOne(('sum(uploaded)', 'sum(downloaded)'), where=where)
        else:
            item = None
        
        if item != None and len(item) == 2 and item[0] != None and item[1] != None:
            self.total_up = int(item[0])
            self.total_down = int(item[1])
        else:
            self.total_up = 0
            self.total_down = 0
            
#         if DEBUG:
#             print >> sys.stderr, "My reputation: ", self.getMyReputation()
            
    
    def getTotals(self):
        return (self.total_up, self.total_down)
                        
    def getName(self, permid):

        if permid == 'non-tribler':
            return "non-tribler"
        elif permid == self.my_permid:
            return "local_tribler"

        name = self.peer_db.getPeer(permid, 'name')
        
        if name == None or name == '':
            return 'peer %s' % show_permid_shorter(permid) 
        else:
            return name

    def getNameByID(self, peer_id):
        permid = self.getPermid(peer_id)
        return self.getName(permid)


    def getPermid(self, peer_id):

        # by convention '-1' is the id of non-tribler peers
        if peer_id == -1:
            return 'non-tribler'
        else:
            return self.peer_db.getPermid(peer_id)


    def getPeerID(self, permid):
        
        # by convention '-1' is the id of non-tribler peers
        if permid == "non-tribler":
            return -1
        else:
            return self.peer_db.getPeerID(permid)

    def getItem(self, (permid_from, permid_to), default=False):

        # ARNODB: now converting back to dbid! just did reverse in getItemList
        peer_id1 = self.getPeerID(permid_from)
        peer_id2 = self.getPeerID(permid_to)
        
        if peer_id1 is None:
            self._db.insertPeer(permid_from) # ARNODB: database write
            peer_id1 = self.getPeerID(permid_from) # ARNODB: database write
        
        if peer_id2 is None:
            self._db.insertPeer(permid_to)
            peer_id2 = self.getPeerID(permid_to)
            
        return self.getItemByIDs((peer_id1,peer_id2),default=default)


    def getItemByIDs(self, (peer_id_from, peer_id_to), default=False):
        if peer_id_from is not None and peer_id_to is not None:
            
            where = "peer_id_from=%s and peer_id_to=%s" % (peer_id_from, peer_id_to)
            item = self.getOne(('downloaded', 'uploaded', 'last_seen'), where=where)
        
            if item is None:
                return None
        
            if len(item) != 3:
                return None
            
            itemdict = {}
            itemdict['downloaded'] = item[0]
            itemdict['uploaded'] = item[1]
            itemdict['last_seen'] = item[2]
            itemdict['peer_id_from'] = peer_id_from
            itemdict['peer_id_to'] = peer_id_to

            return itemdict

        else:
            return None


    def getItemList(self):    # get the list of all peers' permid
        
        keys = self.getAll(('peer_id_from','peer_id_to'))
        # ARNODB: this dbid -> permid translation is more efficiently done
        # on the final top-N list.
        keys = map(lambda (id_from, id_to): (self.getPermid(id_from), self.getPermid(id_to)), keys)
        return keys


    def addItem(self, (permid_from, permid_to), item, commit=True):

#        if value.has_key('last_seen'):    # get the latest last_seen
#            old_last_seen = 0
#            old_data = self.getPeer(permid)
#            if old_data:
#                old_last_seen = old_data.get('last_seen', 0)
#            last_seen = value['last_seen']
#            value['last_seen'] = max(last_seen, old_last_seen)

        # get peer ids
        peer_id1 = self.getPeerID(permid_from)
        peer_id2 = self.getPeerID(permid_to)
                
        # check if they already exist in database; if not: add
        if peer_id1 is None:
            self._db.insertPeer(permid_from)
            peer_id1 = self.getPeerID(permid_from)
        if peer_id2 is None:
            self._db.insertPeer(permid_to)
            peer_id2 = self.getPeerID(permid_to)
            
        item['peer_id_from'] = peer_id1
        item['peer_id_to'] = peer_id2    
            
        self._db.insert(self.table_name, commit=commit, **item)

    def updateItem(self, (permid_from, permid_to), key, value, commit=True):
        
        if DEBUG:
            print >> sys.stderr, "bartercastdb: update (%s, %s) [%s] += %s" % (self.getName(permid_from), self.getName(permid_to), key, str(value))

        itemdict = self.getItem((permid_from, permid_to))

        # if item doesn't exist: add it
        if itemdict == None:
            self.addItem((permid_from, permid_to), {'uploaded':0, 'downloaded': 0, 'last_seen': int(time())}, commit=True)
            itemdict = self.getItem((permid_from, permid_to))

        # get peer ids
        peer_id1 = itemdict['peer_id_from']
        peer_id2 = itemdict['peer_id_to']

        if key in itemdict.keys():
            
            where = "peer_id_from=%s and peer_id_to=%s" % (peer_id1, peer_id2)
            item = {key: value}
            self._db.update(self.table_name, where = where, commit=commit, **item)            

    def incrementItem(self, (permid_from, permid_to), key, value, commit=True):
        if DEBUG:
            print >> sys.stderr, "bartercastdb: increment (%s, %s) [%s] += %s" % (self.getName(permid_from), self.getName(permid_to), key, str(value))

        # adjust total_up and total_down
        if permid_from == self.my_permid:
            if key == 'uploaded':
                self.total_up += int(value)
            if key == 'downloaded':
                self.total_down += int(value)
    
        itemdict = self.getItem((permid_from, permid_to))

        # if item doesn't exist: add it
        if itemdict == None:
            self.addItem((permid_from, permid_to), {'uploaded':0, 'downloaded': 0, 'last_seen': int(time())}, commit=True)
            itemdict = self.getItem((permid_from, permid_to))
            
        # get peer ids
        peer_id1 = itemdict['peer_id_from']
        peer_id2 = itemdict['peer_id_to']

        if key in itemdict.keys():
            old_value = itemdict[key]
            new_value = old_value + value
            
            where = "peer_id_from=%s and peer_id_to=%s" % (peer_id1, peer_id2)

            item = {key: new_value}
            self._db.update(self.table_name, where = where, commit=commit, **item)            
            return new_value

        return None

    def addPeersBatch(self,permids):
        """ Add unknown permids as batch -> single transaction """
        if DEBUG:
            print >> sys.stderr, "bartercastdb: addPeersBatch: n=",len(permids)
        
        for permid in permids:
            peer_id = self.getPeerID(permid)
            # check if they already exist in database; if not: add
            if peer_id is None:
                self._db.insertPeer(permid,commit=False)
        self._db.commit()

    def updateULDL(self, (permid_from, permid_to), ul, dl, commit=True):
        """ Add ul/dl record to database as a single write """
        
        if DEBUG:
            print >> sys.stderr, "bartercastdb: updateULDL (%s, %s) ['ul'] += %s ['dl'] += %s" % (self.getName(permid_from), self.getName(permid_to), str(ul), str(dl))

        itemdict = self.getItem((permid_from, permid_to))

        # if item doesn't exist: add it
        if itemdict == None:
            itemdict =  {'uploaded':ul, 'downloaded': dl, 'last_seen': int(time())}
            self.addItem((permid_from, permid_to), itemdict, commit=commit)
            return

        # get peer ids
        peer_id1 = itemdict['peer_id_from']
        peer_id2 = itemdict['peer_id_to']

        if 'uploaded' in itemdict.keys() and 'downloaded' in itemdict.keys():
            where = "peer_id_from=%s and peer_id_to=%s" % (peer_id1, peer_id2)
            item = {'uploaded': ul, 'downloaded':dl}
            self._db.update(self.table_name, where = where, commit=commit, **item)            

    def getPeerIDPairs(self):
        keys = self.getAll(('peer_id_from','peer_id_to'))
        return keys
        
    def getTopNPeers(self, n, local_only = False):
        """
        Return (sorted) list of the top N peers with the highest (combined) 
        values for the given keys. This version uses batched reads and peer_ids
        in calculation
        @return a dict containing a 'top' key with a list of (permid,up,down) 
        tuples, a 'total_up', 'total_down', 'tribler_up', 'tribler_down' field. 
        Sizes are in kilobytes.
        """
        
        # TODO: this won't scale to many interactions, as the size of the DB
        # is NxN
        
        if DEBUG:
            print >> sys.stderr, "bartercastdb: getTopNPeers: local = ", local_only
            #print_stack()
        
        n = max(1, n)
        my_peer_id = self.getPeerID(self.my_permid)
        total_up = {}
        total_down = {}
        # Arno, 2008-10-30: I speculate this is to count transfers only once,
        # i.e. the DB stored (a,b) and (b,a) and we want to count just one.
        
        processed =  Set()
        

        value_name = '*'
        increment = 500
        
        nrecs = self.size()
        #print >>sys.stderr,"NEXTtopN: size is",nrecs
        
        for offset in range(0,nrecs,increment):
            if offset+increment > nrecs:
                limit = nrecs-offset
            else:
                limit = increment
            #print >>sys.stderr,"NEXTtopN: get",offset,limit
        
            reslist = self.getAll(value_name, offset=offset, limit=limit)
            #print >>sys.stderr,"NEXTtopN: res len is",len(reslist),`reslist`
            for res in reslist:
                (peer_id_from,peer_id_to,downloaded,uploaded,last_seen,value) = res
            
                if local_only:
                    if not (peer_id_to == my_peer_id or peer_id_from == my_peer_id):
                        # get only items of my local dealings
                        continue
                        
                if (not (peer_id_to, peer_id_from) in processed) and (not peer_id_to == peer_id_from):
                #if (not peer_id_to == peer_id_from):
        
                    up = uploaded *1024 # make into bytes
                    down = downloaded *1024
    
                    if DEBUG:
                        print >> sys.stderr, "bartercastdb: getTopNPeers: DB entry: (%s, %s) up = %d down = %d" % (self.getNameByID(peer_id_from), self.getNameByID(peer_id_to), up, down)
    
                    processed.add((peer_id_from, peer_id_to))
    
                    # fix for multiple my_permids
                    if peer_id_from == -1: # 'non-tribler':
                        peer_id_to = my_peer_id
                    if peer_id_to == -1: # 'non-tribler':
                        peer_id_from = my_peer_id
    
                    # process peer_id_from
                    total_up[peer_id_from] = total_up.get(peer_id_from, 0) + up
                    total_down[peer_id_from] = total_down.get(peer_id_from, 0) + down
    
                    # process peer_id_to
                    total_up[peer_id_to] = total_up.get(peer_id_to, 0) + down
                    total_down[peer_id_to] = total_down.get(peer_id_to, 0) +  up

                    
        # create top N peers
        top = []
        min = 0

        for peer_id in total_up.keys():

            up = total_up[peer_id]
            down = total_down[peer_id]

            if DEBUG:
                print >> sys.stderr, "bartercastdb: getTopNPeers: total of %s: up = %d down = %d" % (self.getName(peer_id), up, down)

            # we know rank on total upload?
            value = up

            # check if peer belongs to current top N
            if peer_id != -1 and peer_id != my_peer_id and (len(top) < n or value > min):

                top.append((peer_id, up, down))

                # sort based on value
                top.sort(cmp = lambda (p1, u1, d1), (p2, u2, d2): cmp(u2, u1))

                # if list contains more than N elements: remove the last (=lowest value)
                if len(top) > n:
                    del top[-1]

                # determine new minimum of values    
                min = top[-1][1]

        # Now convert to permid
        permidtop = []
        for peer_id,up,down in top:
            permid = self.getPermid(peer_id)
            permidtop.append((permid,up,down))

        result = {}

        result['top'] = permidtop

        # My total up and download, including interaction with non-tribler peers
        result['total_up'] = total_up.get(my_peer_id, 0)
        result['total_down'] = total_down.get(my_peer_id, 0)

        # My up and download with tribler peers only
        result['tribler_up'] = result['total_up'] - total_down.get(-1, 0) # -1 = 'non-tribler'
        result['tribler_down'] = result['total_down'] - total_up.get(-1, 0) # -1 = 'non-tribler'

        if DEBUG:
            print >> sys.stderr, result

        return result
        
        
    ################################
    def update_network(self):


        keys = self.getPeerIDPairs() #getItemList()


    ################################
    def getMyReputation(self, alpha = ALPHA):

        rep = atan((self.total_up - self.total_down) * alpha)/(0.5 * pi)
        return rep   







class ModerationCastDBHandler(BasicDBHandler):
    
    __single = None    # used for multithreaded singletons pattern
    lock = threading.Lock()
    
    def getInstance(*args, **kw):
        
        if ModerationCastDBHandler.__single is None:
            ModerationCastDBHandler.lock.acquire()   
            try:
                if ModerationCastDBHandler.__single is None:
                    ModerationCastDBHandler(*args, **kw)
            finally:
                ModerationCastDBHandler.lock.release()
        return ModerationCastDBHandler.__single
    
    getInstance = staticmethod(getInstance)

    def __init__(self):
        ModerationCastDBHandler.__single = self
        try:
            db = SQLiteCacheDB.getInstance()
            BasicDBHandler.__init__(self,db,'ModerationCast')
            print >> sys.stderr, "modcast: DB made" 
        except: 
            print >> sys.stderr, "modcast: couldn't create DB table"
        self.peer_db = PeerDBHandler.getInstance()
 
        if DEBUG:
            print >> sys.stderr, "MODERATIONCAST: MyPermid is ", self.my_permid
    
    def registerSession(self, session):
        self.session = session
        self.my_permid = session.get_permid()
    
    def __len__(self):
        return sum([db._size() for db in self.dbs])
    
    def getAll(self):
        sql = 'select * from ModerationCast'
        records = self._db.fetchall(sql)
        return records        

    def getAllModerations(self, permid):
        sql = 'select * from ModerationCast where mod_id==?'
        records = self._db.fetchall(sql, (permid,))
        return records
    
    def getModeration(self, infohash):
        #assert validInfohash(infohash)
        sql = 'select * from ModerationCast where infohash==?' #and time_stamp in (select max(time_stamp) latest FROM ModerationCast where infohash==? group by infohash)'
        item = self._db.fetchone(sql,(infohash,))
        return item


    def hasModeration(self, infohash):
        """ Returns True iff there is a moderation for infohash infohash """
        sql = 'select mod_id from ModerationCast where infohash==?'
        item = self._db.fetchone(sql,(infohash,))
        if DEBUG:
            print >> sys.stderr,"MCDB: hasModeration: infohash:",infohash," ; item:",item
        if item is None:
            return False
        else:
            return True

    def hasModerator(self, permid):
        """ Returns True iff there is a moderator for PermID permid in the moderatorDB """
        sql = "Select mod_id from Moderators where mod_id==?"
        args = permid
        
        item = self._db.fetchone(sql,(permid,))
        if item is None:
            return False
        else:
            return True
    
    def getModerator(self, permid):
        sql = 'select * from Moderators where mod_id==?'# + str(permid)
        item = self._db.fetchone(sql,(permid,))
        return item
    
    def getModeratorPermids(self):
        sql = 'select mod_id from Moderators'
        item = self._db.fetchall(sql)
        return item
    
    def getAllModerators(self):
        sql = 'select * from Moderators'
        item = self._db.fetchall(sql)
        return item
        

    def getVotedModerators(self):
        sql = 'select * from Moderators where status != 0'
        item = self._db.fetchall(sql)
        return item
    
    
    def getForwardModeratorPermids(self):
        sql = 'select mod_id from Moderators where status==1'
        permid_strs = self._db.fetchall(sql)
        return permid_strs
    
    def getBlockedModeratorPermids(self):
        sql = 'select mod_id from Moderators where status==-1'
        item = self._db.fetchall(sql)
        return item
        #CALL VOTECAST TABLES and return the value
        #return [permid for permid in self.moderator_db.getKeys() if permid['blocked']]        

    def getTopModeratorPermids(self, top=10):
        withmod = [permid for permid in self.moderator_db.getKeys() if permid.has_key('moderations') and permid['moderations'] != []]
        
        def topSort(moda, modb):
            return len(moda['moderations'])-len(modb['moderations'])
        
        return withmod.sort(topSort)[0:top]
    
    def updateModeration(self, moderation):
        assert type(moderation) == dict
        assert moderation.has_key('time_stamp') and validTimestamp(moderation['time_stamp'])
        assert moderation.has_key('mod_id') and validPermid(moderation['mod_id'])
        self.validSignature(moderation)
        infohash = moderation['infohash']
        moderator = moderation['mod_id']
        if self.hasModerator(moderator) and moderator in self.getBlockedModeratorPermids():
            print >> sys.stderr, "Got moderation from blocked moderator", show_permid_short(moderator)+", hence we drop this moderation!"
            return
        
        if not self.hasModeration(infohash) or self.getModeration(infohash)[3] < moderation['time_stamp']:            
            self.addModeration(moderation)
        
    def addOwnModeration(self, mod, clone=False):
        assert type(mod) == dict
        assert mod.has_key('infohash')
        assert validInfohash(mod['infohash'])
        
        moderation = mod
        moderation['mod_name'] = self.session.get_nickname()
        #Add current time as a timestamp
        moderation['time_stamp'] = now()
        moderation['mod_id'] = bin2str(self.my_permid)
        #Add permid and signature:
        self._sign(moderation)
        
        self.addModeration(moderation, clone=False)
    
    def addModeration(self, moderation, clone=True):
        if self.hasModeration(moderation['infohash']):
            if self.getModeration(moderation['infohash'])[3] < moderation['time_stamp']:
                self.deleteModeration(moderation['infohash'])
            else:
                return
        
        self._db.insert(self.table_name, **moderation)
        print >>sys.stderr, "Moderation inserted:", repr(moderation)
        
        if self.getModeratorPermids() is None or not self.hasModerator(moderation['mod_id']):
            new = {}
            new['mod_id'] = moderation['mod_id']
            #change it later RAMEEZ
            new['status'] = 0
            new['time_stamp'] = now()
            self._db.insert('Moderators', **new)
            print >>sys.stderr, "New Moderator inserted:", repr(new)
        
    def deleteModeration(self, infohash):
        sql = 'Delete From ModerationCast where infohash==?'
        self._db.execute_write(sql,(infohash,))
    
    def deleteModerations(self, permid):
        sql = 'Delete From ModerationCast where mod_id==?'
        self._db.execute_write(sql,(permid,))

    def deleteModerator(self, permid):
        """ Deletes moderator with permid permid from database """
        sql = 'Delete From Moderators where mod_id==?'
        self._db.execute_write(sql,(permid,))
        
        self.deleteModerations(permid)

    def blockModerator(self, permid, blocked=True):
        """ Blocks/unblocks moderator with permid permid """
        if blocked:
            
            self.deleteModerations(permid)
            sql = 'Update Moderators set status = -1, time_stamp=' + str(now())  + ' where mod_id==?'            
            self._db.execute_write(sql,(permid,))
        else:
            self.forwardModerator(permid)

    ################################
    def maxflow(self, peerid, max_distance = MAXFLOW_DISTANCE):

        self.update_network()
        upflow = self.network.maxflow(peerid, self.my_peerid, max_distance)
        downflow = self.network.maxflow(self.my_peerid, peerid, max_distance)

        return (upflow, downflow) 

    ################################
    def getReputationByID(self, peerid, max_distance = MAXFLOW_DISTANCE, alpha = ALPHA):

        (upflow, downflow) = self.maxflow(peerid, max_distance)
        rep = atan((upflow - downflow) * alpha)/(0.5 * pi)
        return rep   


    ################################
    def getReputation(self, permid, max_distance = MAXFLOW_DISTANCE, alpha = ALPHA):

        peerid = self.getPeerID(permid)
        return self.reputationByID(peerid, max_distance, alpha)  

         
    ################################
    def getMyReputation(self, alpha = ALPHA):

        rep = atan((self.total_up - self.total_down) * alpha)/(0.5 * pi)
        return rep   

    def forwardModerator(self, permid, forward=True):
        if DEBUG:
            print >>sys.stderr, "Before updating Moderator's status..", repr(self.getModerator(permid))
        sql = 'Update Moderators set status = 1, time_stamp=' + str(now())  + ' where mod_id==?'
        self._db.execute_write(sql,(permid,))
        if DEBUG:
            print >>sys.stderr, "Updated Moderator's status..", repr(self.getModerator(permid))

    def getName(self, permid):
        
        name = self.peer_db.getPeer(permid, 'name')
        
        if name == None or name == '':
            return 'peer %s' % show_permid_shorter(permid) 
        else:
            return name
    
    def getPermid(self, peer_id):

        # by convention '-1' is the id of non-tribler peers
        if peer_id == -1:
            return 'non-tribler'
        else:
            return self.peer_db.getPermid(peer_id)


    def getPeerID(self, permid):
        # by convention '-1' is the id of non-tribler peers
        if permid == "non-tribler":
            return -1
        else:
            return self.peer_db.getPeerID(permid)

    
    def hasPeer(self, permid):
        return self.peer_db.hasPeer(permid)
                
    
    def recentOwnModerations(self, nr=13):
        """ Returns the most recent nr moderations (if existing) that you have created """
        
        
        #List of our moderations
        if not self.hasModerator(bin2str(self.my_permid)):
            return []
        
        forwardable = self.getAllModerations(bin2str(self.my_permid))

        #Sort the infohashes in this list based on timestamp
        forwardable.sort(self._compareFunction)
        
        #Return most recent, forwardable, moderations (max nr)
        return forwardable[0:nr]
    
    def randomOwnModerations(self, nr=12):
        """ Returns nr random moderations (if existing) that you have created """
        
        #List of our moderations
        if not self.hasModerator(bin2str(self.my_permid)):
            return []
        
        forwardable = self.getAllModerations(bin2str(self.my_permid))
        
        if len(forwardable) > nr:
            #Return random subset of size nr
            return sample(forwardable, nr)
        else:
            #Return complete set
            return forwardable
    
    def recentModerations(self, nr=13):
        """ Returns the most recent nr moderations (if existing), for moderators that you selected to forward for """
        forwardable = []
        
        #Create a list of infohashes that we are willing to forward
        keys = self.getModeratorPermids()
        for key in keys:
            moderator = self.getModerator(key[0])
            if moderator[1] == 1:
                forwardable.extend(self.getAllModerations(key[0]))
                

        #Sort the infohashes in this list based on timestamp
        forwardable.sort(self._compareFunction)
        
        #Return most recent, forwardable, moderations (max nr)
        return forwardable[0:nr]

    
    

    def randomModerations(self, nr=12):
        """ Returns nr random moderations (if existing), for moderators that you selected to forward for """
        forwardable = []
        
        #Create a list of infohashes that we are willing to forward
        keys = self.getModeratorPermids()
        for key in keys:
            #print >> sys.stderr, "what is the average now baby?????????", key[0]
            moderator = self.getModerator(key[0])
            #print >> sys.stderr, "what is the average now my sooooonnnn", moderator[1]
            if moderator[1] == 1:
                forwardable.extend(self.getAllModerations(key[0]))

        if len(forwardable) > nr:
            #Return random subset of size nr
            return sample(forwardable, nr)
        else:
            #Return complete set
            return forwardable
    
    
    def getModerationInfohashes(self):
        return self.moderation_db.getKeys()

    
    def _compareFunction(self,moderationx,moderationy):
        if moderationx[3] > moderationy[3]:
            return 1
        if moderationx[3] == moderationy[3]:
            return 0
        return -1
    
    '''def _compareFunction(self,infohashx,infohashy):
        """ Compare function to sort an infohash-list based on the moderation-timestamps """
        #print >> sys.stderr, "what's it all about ?????????????", infohashx[0], infohashy[0]
        print >> sys.stderr, "i am a great great man ;-)", infohashx,"?????????????",infohashy
        tx = self.getModeration(infohashx[3])
        ty = self.getModeration(infohashy[3])
        
        #print >> sys.stderr, "i am a great great man ;-)", tx,"?????????????",ty
        
        if tx > ty:
            return 1
        if tx == ty:
            return 0
        return -1'''


    def _sign(self, moderation):
        assert moderation is not None
        assert type(moderation) == dict
        assert not moderation.has_key('signature')    #This would corrupt the signature
        moderation['mod_id'] = bin2str(self.my_permid)
        bencoding = bencode(moderation)
        moderation['signature'] = bin2str(sign_data(bencoding, self.session.keypair))
    
    def validSignature(self,moderation):
        blob = str2bin(moderation['signature'])
        permid = str2bin(moderation['mod_id'])
        #Plaintext excludes signature:
        del moderation['signature']
        plaintext = bencode(moderation)
        moderation['signature'] = bin2str(blob)

        r = verify_data(plaintext, permid, blob)
        if not r:
            if DEBUG:
                print >>sys.stderr,"modcastdb: Invalid signature >>>>>>"
        return r
    
    
#end moderation
class VoteCastDBHandler(BasicDBHandler):
    
    __single = None    # used for multithreaded singletons pattern
    lock = threading.Lock()
    
    def getInstance(*args, **kw):
        
        if VoteCastDBHandler.__single is None:
            VoteCastDBHandler.lock.acquire()   
            try:
                if VoteCastDBHandler.__single is None:
                    VoteCastDBHandler(*args, **kw)
            finally:
                VoteCastDBHandler.lock.release()
        return VoteCastDBHandler.__single
    
    getInstance = staticmethod(getInstance)

    def __init__(self):
        VoteCastDBHandler.__single = self
        try:
            db = SQLiteCacheDB.getInstance()
            BasicDBHandler.__init__(self,db,'VoteCast')
            print >> sys.stderr, "votecast: DB made" 
        except: 
            print >> sys.stderr, "votecast: couldn't make the table"
        
        self.peer_db = PeerDBHandler.getInstance()
        self.moderationcast_db = ModerationCastDBHandler.getInstance()
        if DEBUG:
            print >> sys.stderr, "votecast: My permid is",`self.my_permid`
    
    def registerSession(self, session):
        self.session = session
        self.my_permid = session.get_permid()
    
    def __len__(self):
        return sum([db._size() for db in self.dbs])
    
    def getAllVotes(self, permid):
        sql = 'select * from VoteCast where mod_id==?'
        
        records = self._db.fetchall(sql, (permid,))
        return records
    
    def getAll(self):
        sql = 'select * from VoteCast'
        
        records = self._db.fetchall(sql)
        return records
        
    
    def getAverageVotes(self):
        moderators = self.moderationcast_db.getModeratorPermids()
        if len(moderators) == 0:
            return 0
        
        total_votes = 0.0
        
        for mod in moderators:
            votes = self.getAllVotes(mod[0])
            total_votes += len(votes)
        
        
        avg = total_votes/len(moderators)
        return avg
    
    
    def getAverageRank(self):
        moderators = self.moderationcast_db.getModeratorPermids()
        if len(moderators) == 0:
            return 0
        avg = 0.0
        #print >> sys.stderr, "number of moderatosr has increased ", len(moderators)
        for mod in moderators:
            #print >> sys.stderr, "moderators ####: ", mod
            votes = self.getPosNegVotes(mod)
            pos = votes[0]
            neg = votes[1]
            if pos + neg == 0:
                rank = 0
            else:
                rank = pos/(pos+neg)
            avg +=rank
        
        value = avg/len(moderators)
        return value
    
    def getPosNegVotes(self, permid):
        sql = 'select * from VoteCast where mod_id==?'
        
        records = self._db.fetchall(sql, (permid[0],))
        pos_votes = 0
        neg_votes = 0
        
        if records is None:
            return(pos_votes,neg_votes)
        
        for vote in records:
            
            if vote[2] == "1":
                pos_votes +=1
            else:
                neg_votes +=1
        return (pos_votes, neg_votes)
    
    
    def getAllVotesByVoter(self, permid):
        #assert validInfohash(infohash)
        sql = 'select * from VoteCast where voter_id==?' #and time_stamp in (select max(time_stamp) latest FROM ModerationCast where infohash==? group by infohash)'
        item = self._db.fetchone(sql,(self.getPeerID(permid),))
        return item


    def hasVote(self, permid, voter_peerid):
        """ Returns True iff there is a moderation for infohash infohash """
        sql = 'select mod_id, voter_id from VoteCast where mod_id==? and voter_id==?'
        item = self._db.fetchone(sql,(permid,voter_peerid,))
        #print >> sys.stderr,"well well well",infohash," sdd",item
        if item is None:
            return False
        else:
            return True
    
    def getBallotBox(self):
        sql = 'select * from VoteCast'
        items = self._db.fetchall(sql)
        return items   
    
    
    def getVote(self,permid,peerid):
        sql = 'select * from VoteCast where mod_id==? and voter_id==?'
        item = self._db.fetchone(sql,(permid,peerid,))
        return item
    
    def addVote(self, vote, clone=True):
        vote['time_stamp'] = now()
        if self.hasVote(vote['mod_id'],vote['voter_id']):
            self.deleteVote(vote['mod_id'],vote['voter_id'])        
        self._db.insert(self.table_name, **vote)        
        print >> sys.stderr, "Vote added:",repr(vote)        
    
    def deleteVotes(self, permid):
        sql = 'Delete From VoteCast where mod_id==?'
        self._db.execute_write(sql,(permid,))
    
    def deleteVote(self, permid, voter_id):
        sql = 'Delete From VoteCast where mod_id==? and voter_id==?'
        self._db.execute_write(sql,(permid,voter_id,))
    
    def getPermid(self, peer_id):

        # by convention '-1' is the id of non-tribler peers
        if peer_id == -1:
            return 'non-tribler'
        else:
            return self.peer_db.getPermid(peer_id)


    def getPeerID(self, permid):
        # by convention '-1' is the id of non-tribler peers
        if permid == "non-tribler":
            return -1
        else:
            return self.peer_db.getPeerID(permid)

    
    def hasPeer(self, permid):
        return self.peer_db.hasPeer(permid)
    
    def recentVotes(self, nr=25):
        """ Returns the most recent nr moderations (if existing), for moderators that you selected to forward for """
        forwardable = []
        
        #Create a list of infohashes that we are willing to forward
        keys = self.moderationcast_db.getVotedModerators() 

        for key in keys:            
            forwardable.append(key)
        
        forwardable.sort(self._compareFunction)
        return forwardable[0:nr]
    
    def randomVotes(self, nr=25):
        """ Returns nr random moderations (if existing), for moderators that you selected to forward for """
        forwardable = []
        
        #Create a list of infohashes that we are willing to forward
        keys = self.moderationcast_db.getVotedModerators()
        
        for key in keys:
            #print >> sys.stderr, "votes i don't know ", key
            forwardable.append(key)
            
        if len(forwardable) > nr:
            #Return random subset of size nr
            return sample(forwardable, nr)
        else:
            #Return complete set
            return forwardable
        
    def _compareFunction(self,moderatorx, moderatory):
        """ Compare function to sort an infohash-list based on the moderation-timestamps """
        print >> sys.stderr, "what are you comparing", moderatorx,"sdfafdsfds", moderatory
        
        if moderatorx[2] > moderatory[2]:
            return 1
        
        if moderatorx[2] == moderatory[2]:
            return 0
        return -1

#end votes

           


class GUIDBHandler:
    """ All the functions of this class are only (or mostly) used by GUI.
        It is not associated with any db table, but will use any of them
    """
    
    __single = None    # used for multithreaded singletons pattern
    lock = threading.Lock()
    
    def getInstance(*args, **kw):
        # Singleton pattern with double-checking
        if GUIDBHandler.__single is None:
            GUIDBHandler.lock.acquire()   
            try:
                if GUIDBHandler.__single is None:
                    GUIDBHandler(*args, **kw)
            finally:
                GUIDBHandler.lock.release()
        return GUIDBHandler.__single
    
    getInstance = staticmethod(getInstance)
    
    def __init__(self):
        if GUIDBHandler.__single is not None:
            raise RuntimeError, "GUIDBHandler is singleton"
        self._db = SQLiteCacheDB.getInstance()
        self.notifier = Notifier.getInstance()
        GUIDBHandler.__single = self
        
    def getCommonFiles(self, permid):
        peer_id = self._db.getPeerID(permid)
        if peer_id is None:
            return []
        
        sql_get_common_files = """select name from CollectedTorrent where torrent_id in (
                                    select torrent_id from Preference where peer_id=?
                                      and torrent_id in (select torrent_id from MyPreference)
                                    ) and status_id <> 2
                               """ + self.get_family_filter_sql()
        res = self._db.fetchall(sql_get_common_files, (peer_id,))
        return [t[0] for t in res]
        
    def getOtherFiles(self, permid):
        peer_id = self._db.getPeerID(permid)
        if peer_id is None:
            return []
        
        sql_get_other_files = """select infohash,name from CollectedTorrent where torrent_id in (
                                    select torrent_id from Preference where peer_id=?
                                      and torrent_id not in (select torrent_id from MyPreference)
                                    ) and status_id <> 2
                              """ + self.get_family_filter_sql()
        res = self._db.fetchall(sql_get_other_files, (peer_id,))
        return [(str2bin(t[0]),t[1]) for t in res]
    
    def getSimItems(self, infohash, limit):
        # recommendation based on collaborative filtering
        torrent_id = self._db.getTorrentID(infohash)
        if torrent_id is None:
            return []
        
        sql_get_sim_files = """
            select infohash, name, status_id, count(P2.torrent_id) c 
             from Preference as P1, Preference as P2, CollectedTorrent as T
             where P1.peer_id=P2.peer_id and T.torrent_id=P2.torrent_id 
             and P2.torrent_id <> P1.torrent_id
             and P1.torrent_id=?
             and P2.torrent_id not in (select torrent_id from MyPreference)
             %s
             group by P2.torrent_id
             order by c desc
             limit ?    
        """ % self.get_family_filter_sql('T')
         
        res = self._db.fetchall(sql_get_sim_files, (torrent_id,limit))
        return [(str2bin(t[0]),t[1], t[2], t[3]) for t in res]
        
    def getSimilarTitles(self, name, limit, infohash, prefix_len=5):
        # recommendation based on similar titles
        name = name.replace("'","`")
        sql_get_sim_files = """
            select infohash, name, status_id from Torrent 
            where name like '%s%%'
             and infohash <> '%s'
             and torrent_id not in (select torrent_id from MyPreference)
             %s
            order by name
             limit ?    
        """ % (name[:prefix_len], bin2str(infohash), self.get_family_filter_sql())
        
        res = self._db.fetchall(sql_get_sim_files, (limit,))
        return [(str2bin(t[0]),t[1], t[2]) for t in res]

    def _how_many_prefix(self):
        """ test how long the prefix is enough to find similar titles """
        # Jie: I found 5 is the best value.
        
        sql = "select name from Torrent where name is not NULL order by name"
        names = self._db.fetchall(sql)
        
        for top in range(3, 10):
            sta = {}
            for line in names:
                prefix = line[0][:top]
                if prefix not in sta:
                    sta[prefix] = 1
                else:
                    sta[prefix] += 1
            
            res = [(v,k) for k,v in sta.items()]
            res.sort()
            res.reverse()
        
            print >> sys.stderr, '------------', top, '-------------'
            for k in res[:10]:
                print >> sys.stderr, k
         
    def get_family_filter_sql(self, table_name=''):
        torrent_db_handler = TorrentDBHandler.getInstance()
        return torrent_db_handler.category.get_family_filter_sql(torrent_db_handler._getCategoryID, table_name=table_name)



class TermDBHandler(BasicDBHandler):
    
    __single = None    # used for multithreaded singletons pattern
    lock = threading.Lock()
    
    def getInstance(*args, **kw):
        # Singleton pattern with double-checking
        if TermDBHandler.__single is None:
            TermDBHandler.lock.acquire()   
            try:
                if TermDBHandler.__single is None:
                    TermDBHandler(*args, **kw)
            finally:
                TermDBHandler.lock.release()
        return TermDBHandler.__single
    getInstance = staticmethod(getInstance)
    
    def __init__(self):
        if TermDBHandler.__single is not None:
            raise RuntimeError, "TermDBHandler is singleton"
        TermDBHandler.__single = self
        db = SQLiteCacheDB.getInstance()        
        BasicDBHandler.__init__(self,db, 'ClicklogTerm') 
        
        
    def getNumTerms(self):
        """returns number of terms stored"""
        return self.getOne("count(*)")
    
 
    
    def bulkInsertTerms(self, terms, commit=True):
        for term in terms:
            term_id = self.getTermIDNoInsert(term)
            if not term_id:
                self.insertTerm(term, commit=False) # this HAS to commit, otherwise last_insert_row_id() won't work. 
            # if you want to avoid committing too often, use bulkInsertTerm
        if commit:         
            self.commit()
            
    def getTermIDNoInsert(self, term):
        return self.getOne('term_id', term=term[:MAX_KEYWORD_LENGTH].lower())
            
    def getTermID(self, term):
        """returns the ID of term in table ClicklogTerm; creates a new entry if necessary"""
        term_id = self.getTermIDNoInsert(term)
        if term_id:
            return term_id
        else:
            self.insertTerm(term, commit=True) # this HAS to commit, otherwise last_insert_row_id() won't work. 
            return self.getOne("last_insert_rowid()")
    
    def insertTerm(self, term, commit=True):
        """creates a new entry for term in table Term"""
        self._db.insert(self.table_name, commit=commit, term=term[:MAX_KEYWORD_LENGTH])
    
    def getTerm(self, term_id):
        """returns the term for a given term_id"""
        return self.getOne("term", term_id=term_id)
        # if term_id==-1:
        #     return ""
        # term = self.getOne('term', term_id=term_id)
        # try:
        #     return str2bin(term)
        # except:
        #     return term
    
    def getTermsStartingWith(self, beginning, num=10):
        """returns num most frequently encountered terms starting with beginning"""
        
        # request twice the amount of hits because we need to apply
        # the familiy filter...
        terms = self.getAll('term', 
                            term=("like", u"%s%%" % beginning),
                            order_by="times_seen DESC",
                            limit=num * 2)

        if terms:
            # terms is a list containing lists. We only want the first
            # item of the inner lists.
            terms = [term for (term,) in terms]

            catobj = Category.getInstance()
            if catobj.family_filter_enabled():
                return filter(lambda term: not catobj.xxx_filter.foundXXXTerm(term), terms)[:num]
            else:
                return terms[:num]

        else:
            return []
    
    def getAllEntries(self):
        """use with caution,- for testing purposes"""
        return self.getAll("term_id, term", order_by="term_id")
    
    
class SearchDBHandler(BasicDBHandler):
    
    __single = None    # used for multithreaded singletons pattern
    lock = threading.Lock()
    
    def getInstance(*args, **kw):
        # Singleton pattern with double-checking
        if SearchDBHandler.__single is None:
            SearchDBHandler.lock.acquire()   
            try:
                if SearchDBHandler.__single is None:
                    SearchDBHandler(*args, **kw)
            finally:
                SearchDBHandler.lock.release()
        return SearchDBHandler.__single
    getInstance = staticmethod(getInstance)
    
    def __init__(self):
        if SearchDBHandler.__single is not None:
            raise RuntimeError, "SearchDBHandler is singleton"
        SearchDBHandler.__single = self
        db = SQLiteCacheDB.getInstance()
        BasicDBHandler.__init__(self,db, 'ClicklogSearch') ## self,db,'Search'
        
        
    ### write methods
    
    def storeKeywordsByID(self, peer_id, torrent_id, term_ids, commit=True):
        sql_insert_search = u"INSERT INTO ClicklogSearch (peer_id, torrent_id, term_id, term_order) values (?, ?, ?, ?)"
        
        if len(term_ids)>MAX_KEYWORDS_STORED:
            term_ids= term_ids[0:MAX_KEYWORDS_STORED]

        # TODO before we insert, we should delete all potentially existing entries
        # with these exact values
        # otherwise, some strange attacks might become possible
        # and again we cannot assume that user/torrent/term only occurs once

        # create insert data
        values = [(peer_id, torrent_id, term_id, term_order) 
                  for (term_id, term_order) 
                  in zip(term_ids, range(len(term_ids)))]
        self._db.executemany(sql_insert_search, values, commit=commit)        
        
        # update term popularity
        sql_update_term_popularity= u"UPDATE ClicklogTerm SET times_seen = times_seen+1 WHERE term_id=?"        
        self._db.executemany(sql_update_term_popularity, [[term_id] for term_id in term_ids], commit=commit)        
        
    def storeKeywords(self, peer_id, torrent_id, terms, commit=True):
        """creates a single entry in Search with peer_id and torrent_id for every term in terms"""
        terms = [term.strip() for term in terms if len(term.strip())>0]
        term_db = TermDBHandler.getInstance()
        term_ids = [term_db.getTermID(term) for term in terms]
        self.storeKeywordsByID(peer_id, torrent_id, term_ids, commit)

    def getAllEntries(self):
        """use with caution,- for testing purposes"""
        return self.getAll("rowid, peer_id, torrent_id, term_id, term_order ", order_by="rowid")
    
    def getAllOwnEntries(self):
        """use with caution,- for testing purposes"""
        return self.getAll("rowid, peer_id, torrent_id, term_id, term_order ", where="peer_id=0", order_by="rowid")
    

    
    ### read methods
    
    def getNumTermsPerTorrent(self, torrent_id):
        """returns the number of terms associated with a given torrent"""
        return self.getOne("COUNT (DISTINCT term_id)", torrent_id=torrent_id)
        
    def getNumTorrentsPerTerm(self, term_id):
        """returns the number of torrents stored with a given term."""
        return self.getOne("COUNT (DISTINCT torrent_id)", term_id=term_id)
    
    def getNumTorrentTermCooccurrences(self, term_id, torrent_id):
        """returns the number of times a torrent has been associated with a term"""
        return self.getOne("COUNT (*)", term_id=term_id, torrent_id=torrent_id)    
    
    def getRelativeTermFrequency(self, term_id, torrent_id):
        """returns the relative importance of a term for a torrent
        This is basically tf/idf 
        term frequency tf = # keyword used per torrent/# keywords used with torrent at all
        inverse document frequency = # of torrents associated with term at all
        
        normalization in tf ensures that a torrent cannot get most important for all keywords just 
        by, e.g., poisoning the db with a lot of keywords for this torrent
        idf normalization ensures that returned values are meaningful across several keywords 
        """
        
        terms_per_torrent = self.getNumTermsPerTorrent(torrent_id)
        if terms_per_torrent==0:
            return 0
        
        torrents_per_term = self.getNumTorrentsPerTerm(term_id)
        if torrents_per_term == 0:
            return 0
        
        coocc = self.getNumTorrentTermCooccurrences(term_id, torrent_id)
        
        tf = coocc/float(terms_per_torrent)
        idf = 1.0/math.log(torrents_per_term+1)
        
        return tf*idf
    
    
    def getTorrentSearchTerms(self, torrent_id, peer_id):
        return self.getAll("term_id", "torrent_id=%d AND peer_id=%s" % (torrent_id, peer_id), order_by="term_order")
    
    def getMyTorrentSearchTerms(self, torrent_id):
        return [x[0] for x in self.getTorrentSearchTerms(torrent_id, peer_id=0)]
        
                
    ### currently unused
                  
    def numSearchesWithTerm(self, term_id):
        """returns the number of searches stored with a given term. 
        I feel like I might miss something, but this should simply be the number of rows containing
        the term"""
        return self.getOne("COUNT (*)", term_id=term_id)
    
    def getNumTorrentPeers(self, torrent_id):
        """returns the number of users for a given torrent. if this should be used 
        extensively, an index on torrent_id might be in order"""
        return self.getOne("COUNT (DISTINCT peer_id)", torrent_id=torrent_id)
    
    def removeKeywords(self, peer_id, torrent_id, commit=True):
        """removes records of keywords used by peer_id to find torrent_id"""
        # TODO
        # would need to be called by deletePreference
        pass
    
    
    
    
def doPeerSearchNames(self,dbname,kws):
    """ Get all peers that have the specified keywords in their name. 
    Return a list of dictionaries. Each dict is in the NEWDBSTANDARD format.
    """
    if dbname == 'Peer':
        where = '(Peer.last_connected>0 or Peer.friend=1) and '
    elif dbname == 'Friend':
        where  = ''
    else:
        raise Exception('unknown dbname: %s' % dbname)
    
    # Must come before query
    ranks = self.getRanks()

    for i in range(len(kws)):
        kw = kws[i]
        where += ' name like "%'+kw+'%"'
        if (i+1) != len(kws):
            where += ' and'
            
    # See getGUIPeers()
    value_name = PeerDBHandler.gui_value_name
    
    #print >>sys.stderr,"peer_db: searchNames: sql",where
    res_list = self._db.getAll(dbname, value_name, where)
    #print >>sys.stderr,"peer_db: searchNames: res",res_list
    
    peer_list = []
    for item in res_list:
        #print >>sys.stderr,"peer_db: searchNames: Got Record",`item`
        peer = dict(zip(value_name, item))
        peer['name'] = dunno2unicode(peer['name'])
        peer['simRank'] = ranksfind(ranks,peer['permid'])
        peer['permid'] = str2bin(peer['permid'])
        peer_list.append(peer)
    return peer_list

def ranksfind(ranks,key):
    if ranks is None:
        return -1
    try:
        return ranks.index(key)+1
    except:
        return -1
    



