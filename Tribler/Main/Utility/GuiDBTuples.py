#Niels: getValidArgs nased on http://stackoverflow.com/questions/196960/can-you-list-the-keyword-arguments-a-python-function-receives
import sys
from inspect import getargspec
import functools
from Tribler.Video.utils import videoextdefaults
import os.path
from Tribler.Main.vwxGUI import VLC_SUPPORTED_SUBTITLES, COMMENT_REQ_COLUMNS
from collections import namedtuple
from Tribler.Core.CacheDB.sqlitecachedb import safenamedtuple

def getValidArgs(func, argsDict):
    args, _, _, defaults = getargspec(func)
    try:
        args.remove('self')
    except:
        pass
    
    argsDict = dict((key, value) for key, value in argsDict.iteritems() if key in args)
    if defaults:
        args = args[:-len(defaults)]
        
    notOk = set(args).difference(argsDict)
    if notOk:
        print >> sys.stderr, "Missing",notOk,"arguments for",func 
    return argsDict

#Niels: from http://wiki.python.org/moin/PythonDecoratorLibrary#Memoize

def cache(func):
    def _get(self):
        key = func.__name__
        try:
            return self._cache[key]
        except AttributeError:
            self._cache = {}
            x = self._cache[key] = func(self)
            return x
        except KeyError:
            x = self._cache[key] = func(self)
            return x
    return _get

def cacheProperty(func):
    
    def _get(self):
        key = func.__name__
        try:
            return self._cache[key]
        except AttributeError:
            self._cache = {}
            x = self._cache[key] = func(self)
            return x
        except KeyError:
            x = self._cache[key] = func(self)
            return x
        return func(self)
    
    def _del(self):
        key = func.__name__
        try:
            del self._cache[key]
        except:
            pass
    return property(_get, None, _del)

class Helper(object):
    def get(self, key, default = None):
        return getattr(self, key, default)
    
    def __contains__(self, key):
        return key in self.__slots__

class Torrent(Helper):
    __slots__ = ('_torrent_id', 'infohash', 'name', 'length', 'category_id', 'status_id', 'num_seeders', 'num_leechers' ,'_channel_id', '_channel_permid', '_channel_name', '_channel_posvotes', '_channel_negvotes', 'torrent_db', 'ds')
    def __init__(self, torrent_id, infohash, name, length, category_id, status_id, num_seeders, num_leechers, channel_id, channel_permid, channel_name, subscriptions, neg_votes):
        self._torrent_id = torrent_id
        self.infohash = infohash
        self.name = name
        self.length = length
        self.category_id = category_id
        self.status_id = status_id
        self.num_seeders = num_seeders
        self.num_leechers = num_leechers
        
        self._channel_id = channel_id
        self._channel_permid = channel_permid
        self._channel_name = channel_name
        self._channel_posvotes = subscriptions
        self._channel_negvotes = neg_votes
        
        self.torrent_db = None
        self.ds = None
   
    @cacheProperty
    def categories(self):
        return [self.torrent_db.id2category[self.category_id]]
    
    @cacheProperty
    def status(self):
        return self.torrent_db.id2status[self.status_id]
    
    @cacheProperty
    def torrent_id(self):
        if not self._torrent_id:
            self._torrent_id = self.torrent_db.getTorrentID(self.infohash)
        return self._torrent_id
    
    @property
    def channel_id(self):
        return self._channel_id
    
    @property
    def channel_permid(self):
        return self._channel_permid
    
    @property
    def channel_name(self):
        return self._channel_name
    
    @property
    def channel_posvotes(self):
        return self._channel_posvotes
    
    @property
    def channel_negvotes(self):
        return self._channel_negvotes
    
    def hasChannel(self):
        return self.channel_permid != ''
    
class RemoteTorrent(Torrent):
    __slots__ = ('query_permids')
    def __init__(self, torrent_id, infohash, name, length, category_id, status_id, num_seeders, num_leechers, query_permids, channel_id, channel_permid, channel_name, subscriptions, neg_votes):
        Torrent.__init__(self, torrent_id, infohash, name, length, category_id, status_id, num_seeders, num_leechers, channel_id, channel_permid, channel_name, subscriptions, neg_votes)
        self.query_permids = query_permids

class CollectedTorrent(Torrent):
    __slots__ = ('comment', 'trackers', 'creation_date', 'files', 'last_check')
    def __init__(self, torrent, torrentdef):
        Torrent.__init__(self, torrent.torrent_id, torrent.infohash, torrent.name, torrent.length, torrent.category_id, torrent.status_id, torrent.num_seeders, torrent.num_leechers, torrent.channel_id, torrent.channel_permid, torrent.channel_name, torrent.channel_posvotes, torrent.channel_negvotes)
        self.torrent_db = torrent.torrent_db
        self.ds = torrent.ds
        
        self.comment = torrentdef.get_comment_as_unicode()
        if torrentdef.get_tracker_hierarchy():
            self.trackers = torrentdef.get_tracker_hierarchy()
        else:
            self.trackers = [[torrentdef.get_tracker()]]
        self.creation_date = torrentdef.get_creation_date()
        self.files = torrentdef.get_files_as_unicode_with_length()
        self.last_check = -1
    
    @cacheProperty
    def swarminfo(self):
        swarminfo = self.torrent_db.getSwarmInfo(self.torrent_id)
        if swarminfo:
            self.num_seeders = swarminfo[1]
            self.num_leechers = swarminfo[2]
            self.last_check = swarminfo[4]
        return swarminfo
    
    @cacheProperty
    def videofiles(self):
        videofiles = []
        for filename, _ in self.files:
            _, ext = os.path.splitext(filename)
            if ext.startswith('.'):
                ext = ext[1:] 
            
            if ext in videoextdefaults:
                videofiles.append(filename)
        return videofiles
    
    @cacheProperty
    def largestvideofile(self):
        _, filename = max([(size, filename) for filename, size in self.files if filename in self.videofiles])
        return filename
    
    @cacheProperty
    def subtitlefiles(self):
        subtitles = []
        for filename, length in self.files:
            prefix, ext = os.path.splitext(filename)
            if ext.startswith('.'):
                ext = ext[1:]
            if ext in VLC_SUPPORTED_SUBTITLES:
                subtitles.append(filename)
        return subtitles
    
    @cache
    def isPlayable(self):
        return len(self.videofiles) > 0
    
class NotCollectedTorrent(CollectedTorrent):
    def __init__(self, torrent, files, trackers):
        Torrent.__init__(self, torrent.torrent_id, torrent.infohash, torrent.name, torrent.length, torrent.category_id, torrent.status_id, torrent.num_seeders, torrent.num_leechers, torrent.channel_id, torrent.channel_permid, torrent.channel_name, torrent.channel_posvotes, torrent.channel_negvotes)
        self.torrent_db = torrent.torrent_db
        self.ds = torrent.ds
        
        self.comment = None
        self.trackers = trackers
        self.creation_date = -1
        self.files = files
        self.last_check = -1
        
class LibraryTorrent(Torrent):
    __slots__ = ('progress', 'channelcast_db')
    
    def __init__(self, torrent_id, infohash, name, length, category_id, status_id, num_seeders, num_leechers, progress):
        Torrent.__init__(self, torrent_id, infohash, name, length, category_id, status_id, num_seeders, num_leechers, 0, '', '', 0, 0)
        self.progress = progress
        
    @cache
    def _get_channel(self):
        channel = self.channelcast_db.getMostPopularChannelFromTorrent(self.infohash)
        if channel:
            self._channel_id, self._channel_permid, self._channel_name, self._channel_posvotes, self._channel_negvotes = channel
    
    @property
    def channel_id(self):
        self._get_channel()
        return self._channel_id
    
    @property
    def channel_permid(self):
        self._get_channel()
        return self._channel_permid
    
    @property
    def channel_name(self):
        self._get_channel()
        return self._channel_name
    
    @property
    def channel_posvotes(self):
        self._get_channel()
        return self._channel_posvotes
    
    @property
    def channel_negvotes(self):
        self._get_channel()
        return self._channel_negvotes

class ChannelTorrent(Torrent):
    __slots__ = ('channeltorrent_id', 'channel_id', 'colt_name', 'chant_name', 'description', 'time_stamp', 'inserted')
    def __init__(self, torrent_id, infohash, name, length, category_id, status_id, num_seeders, num_leechers, channeltorrent_id, channel_id, chant_name, colt_name, description, time_stamp, inserted):
        Torrent.__init__(self, torrent_id, infohash, name, length, category_id, status_id, num_seeders, num_leechers, -1, '', '', 0, 0)
        self.channeltorrent_id = channeltorrent_id
        self.channel_id = channel_id
        self.colt_name = colt_name
        self.chant_name = chant_name
        self.description = description
        self.time_stamp = time_stamp
        self.inserted = inserted
        
    @property
    def name(self):
        return self.chant_name or self.colt_name
    
    @name.setter
    def name(self, name):
        pass
    
class Channel(Helper):
    __slots__ = ('id','dispersy_cid', 'name', 'description', 'nr_torrents', 'nr_favorites', 'nr_spam', 'my_vote', 'modified')
    def __init__(self, id, dispersy_cid, name, description, nr_torrents, nr_favorites, nr_spam, my_vote, modified):
        self.id = id
        self.dispersy_cid = dispersy_cid
        self.name = name[:40]
        self.description = description
        self.nr_torrents = nr_torrents
        self.nr_favorites = nr_favorites
        self.nr_spam = nr_spam
        self.my_vote = my_vote
        self.modified = modified
    
    @cache
    def isDispersy(self):
        return self.dispersy_cid != '-1'
    
    @cache
    def isFavorite(self):
        return self.my_vote == 2
    
    @cache
    def isSpam(self):
        return self.my_vote == -1
    
    @cache
    def isEmpty(self):
        return self.nr_torrents == 0
        
class Comment(Helper):
    __slots__ = ('id', 'dispersy_id', 'playlist_id', 'channeltorrent_id', 'name', 'peer_id', 'comment', 'time_stamp')
    def __init__(self, id, dispersy_id, playlist_id, channeltorrent_id, name, peer_id, comment, time_stamp):
        self.id = id
        self.dispersy_id = dispersy_id
        self.playlist_id = playlist_id
        self.channeltorrent_id = channeltorrent_id
        self._name = name
        self.peer_id = peer_id
        self.comment = comment
        self.time_stamp = time_stamp
        
    @cacheProperty
    def name(self):
        if self.peer_id == None:
            return self.get_nickname()
        if not self._name:
            return 'Peer %d'%self.peer_id
        return self._name
    
class Modification(Helper):
    __slots__ = ('id', 'type_id', 'value', 'inserted', 'channelcast_db')
    def __init__(self, id, type_id, value, inserted):
        self.id = id
        self.type_id = type_id
        self.value = value
        self.inserted = inserted
        
    @cacheProperty
    def name(self):
        return self.channelcast_db.id2modification[self.type_id]