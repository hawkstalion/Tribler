# Written by Jelle Roozenburg, Maarten ten Brinke, Lucan Musat, Arno Bakker
# see LICENSE.txt for license information

#
# WARNING: To save memory, the torrent records read from database and kept in
# memory here have some fields removed. In particular, 'info' and for buddycasted
# torrents also 'torrent_dir' and 'torrent_name'. Saves 50MB on 30000 torrent DB.
# 

import os
import sys
from base64 import encodestring
from Tribler.utilities import friendly_time, sort_dictlist, remove_torrent_from_list, find_content_in_dictlist
from Tribler.unicode import str2unicode, dunno2unicode
from Utility.constants import * #IGNORE:W0611
from Tribler.Category.Category import Category
from Tribler.CacheDB.SynDBHandler import SynTorrentDBHandler
from Tribler.CacheDB.CacheDBHandler import OwnerDBHandler
from Tribler.Overlay.MetadataHandler import MetadataHandler
from copy import deepcopy
from traceback import print_exc, print_stack
from time import time
from bisect import insort
from sets import Set
from Tribler.Search.KeywordSearch import KeywordSearch
try:
    import web2
except ImportError:
    pass

DEBUG = False
DEBUG_RANKING = False

# Arno: save memory by reusing dict keys
# In principe, these should only be used in assignments, e.g. 
#     torrent[key_length] = 481
# In other cases you can just use 'length'.
key_length = 'length'
key_content_name = 'content_name'
key_torrent_name = 'torrent_name'
key_num_files = 'num_files'
key_date = 'date'
key_tracker = 'tracker'
key_leecher = 'leecher'
key_seeder = 'seeder'
key_swarmsize ='swarmsize'
key_relevance = 'relevance'
key_infohash = 'infohash'
key_myDownloadHistory = 'myDownloadHistory'
key_eventComingUp = 'eventComingUp'
key_simRank = 'simRank'
key_secret = 'secret'

class TorrentDataManager:
    # Code to make this a singleton
    __single = None
   
    def __init__(self, utility):
        if TorrentDataManager.__single:
            raise RuntimeError, "TorrentDataManager is singleton"
        TorrentDataManager.__single = self
        self.done_init = False
        self.utility = utility
        self.rankList = []
        self.isDataPrepared = False
        self.data = []
        self.hits = []
        self.remoteHits = None
        self.dod = None
        self.keywordsearch = KeywordSearch()
        # initialize the cate_dict
        self.info_dict = {}    # reverse map
        self.initDBs()
#        self.loadData()
        self.dict_FunList = {}
        self.done_init = True
        self.standardOverview = None
        self.searchkeywords = {'filesMode':[], 'libraryMode':[]}
        self.oldsearchkeywords = {'filesMode':[], 'libraryMode':[]} # previous query
        self.metadata_handler = MetadataHandler.getInstance()
        
        self.collected_torrent_dir = os.path.join(self.utility.getConfigPath(),'torrent2')
        
        if DEBUG:
            print >>sys.stderr,'torrentManager: ready init'

        
    def getInstance(*args, **kw):
        if TorrentDataManager.__single is None:
            TorrentDataManager(*args, **kw)       
        return TorrentDataManager.__single
    getInstance = staticmethod(getInstance)

    def initDBs(self):
        time1 = time()
        self.torrent_db = SynTorrentDBHandler(updateFun=self.updateFun)
        self.owner_db = OwnerDBHandler()
        self.category = Category.getInstance()
        
    def loadData(self):
        try:
            self.data = self.torrent_db.getRecommendedTorrents(light=True,all=True) #gets torrents with mypref
            
            self.category.register(self.metadata_handler)
            updated = self.category.checkResort(self) # the database is upgraded from v1 to v2
            if updated:
                self.data = self.torrent_db.getRecommendedTorrents(light=False,all=True)
            self.prepareData()
            self.isDataPrepared = True
        except:
            print_exc()
            raise Exception('Could not load torrent data !!')
    def prepareData(self):
        
        for torrent in self.data:      
            # prepare to display
            torrent = self.prepareItem(torrent)
            self.info_dict[torrent["infohash"]] = torrent
            self.updateRankList(torrent, 'add', initializing = True)
        #self.printRankList()
        
        

    def getDownloadHistCount(self):
        #[mluc]{26.04.2007} ATTENTION: data is not updated when a new download starts, although it should
        def isDownloadHistory(torrent):
            return torrent.has_key('myDownloadHistory')
        return len(filter(isDownloadHistory,self.data))
    
    def getRecommendFilesCount(self):
        count = 0
        for torrent in self.data:
            if torrent.has_key('relevance'):
                if torrent['relevance']> 5: #minmal value for a file to be considered tasteful
                    count = count + 1
        return count
        
    def getCategory(self, categorykey, mode):
        if not self.done_init:
            return []
        
        categorykey = categorykey.lower()
        
        if not self.standardOverview:
            self.standardOverview = self.utility.guiUtility.standardOverview
            
        def torrentFilter(torrent):
            library = (mode == 'libraryMode')
            okLibrary = not library or torrent.has_key('myDownloadHistory')
            
            okCategory = False
            if categorykey == 'all':
                okCategory = True
            else:
                categories = torrent.get("category", [])
                if not categories:
                    categories = ["other"]
                if categorykey in [cat.lower() for cat in categories]:
                    okCategory = True
            
            okGood = torrent['status'] == 'good' or torrent.has_key('myDownloadHistory')
            
            return okLibrary and okCategory and okGood
        
        data = filter(torrentFilter, self.data)
        
        if DEBUG:
            print >>sys.stderr,'torrentManager: getCategory found: %d items' % len(data)
        # if searchkeywords are defined. Search instead of show all
        if self.inSearchMode(mode):
                data = self.search(data, mode)    #TODO RS: does it come from remote search or local search?
                self.standardOverview.setSearchFeedback('torrent', False, len(data), self.searchkeywords[mode])
                self.standardOverview.setSearchFeedback('web2', False, -1)
                self.standardOverview.setSearchFeedback('remote', False, -1)
                self.addRemoteResults(data, mode, categorykey)
                if DEBUG:
                    print >>sys.stderr,'torrentManager: getCategory found after search: %d items' % len(data)
        
        web2on = self.utility.config.Read('enableweb2search',"boolean")
        
        #if DEBUG:
        #    print >>sys.stderr,"torrentManager: getCategory: mode",mode,"webon",web2on,"insearch",self.inSearchMode(mode),"catekey",categorykey
        
        if mode == 'filesMode' and web2on and self.inSearchMode(mode) and \
                categorykey in ['video', 'all']:
                # if we are searching in filesmode
                self.standardOverview.setSearchFeedback('web2', False, 0)
                if self.dod:
                    self.dod.stop()
                self.dod = web2.DataOnDemandWeb2(" ".join(self.searchkeywords[mode]))
                self.dod.addItems(data)
                
                return self.dod
             
        else:
            if self.dod:
                self.dod.stop()
                self.dod = None
                
#            if self.inSearchMode(mode):
#                self.standardOverview.setSearchFeedback('torrent', True, len(data))                
            
            return data
                

    def getTorrents(self, hash_list):
        """builds a list with torrents that have the infohash in the list provided as an input parameter"""
        torrents_list = []
        for torrent_data in self.data:
            if torrent_data['infohash'] in hash_list:
                torrents_list.append(torrent_data)
        return torrents_list
            
    def getTorrent(self, infohash):
        return self.torrent_db.getTorrent(infohash)

    def deleteTorrent(self, infohash, delete_file=False):
        self.torrent_db.deleteTorrent(infohash, delete_file=False, updateFlag=True)

    # register update function
    def register(self, fun, key, library):
        if DEBUG:
            print >>sys.stderr,'torrentManager: Registered for key: %s' % key
        try:
            key = key.lower()
            self.dict_FunList[(key, library)].index(fun)
            # if no exception, fun already exist!
            if DEBUG:
                print >>sys.stderr,"torrentManager: register error. " + str(fun.__name__) + " already exist for key %s!" % str((key, library))
            return
        except KeyError:
            self.dict_FunList[(key, library)] = []
            self.dict_FunList[(key, library)].append(fun)
        except ValueError:
            self.dict_FunList[(key, library)].append(fun)
        except Exception, msg:
            if DEBUG:
                print >>sys.stderr,"torrentDataManager: register error.", Exception, msg
            print_exc()
        
        
    def unregister(self, fun, key, library):
        if DEBUG:
            print >>sys.stderr,'torrentDataManager: Unregistered for key: %s' % key
        try:
            key = key.lower()
            self.dict_FunList[(key, library)].remove(fun)
        except Exception, msg:
            if DEBUG:
                print >>sys.stderr,"torrentDataManager: unregister error.", Exception, msg
            print_exc()
            
    def unregisterAll(self, fun):
        rem = 0
        for tuple, funList in self.dict_FunList.iteritems():
            if fun in funList:
                funList.remove(fun)
                rem+=1
        if DEBUG:
            print >>sys.stderr,'torrentDataManager: UnregisteredAll function %s (%d unregisters)' % (fun.__name__, rem)
            
    def updateFun(self, infohash, operate):
        if not self.done_init:    # don't call update func before init finished
            return
        if not self.isDataPrepared:
            return
        if DEBUG:
            print "torrentDataManager: updateFun called, param", operate
        if self.info_dict.has_key(infohash):
            if operate == 'add':
                self.addItem(infohash)
            elif operate == 'update':
                self.updateItem(infohash)
            elif operate == 'delete':
                self.deleteItem(infohash)
        else:
            if operate == 'update' or operate == 'delete':
                return
            else:
                self.addItem(infohash)
                
    def notifyView(self, torrent, operate, libraryDelete = False):        
#        if torrent["category"] == ["?"]:
#            torrent["category"] = self.category.calculateCategory(torrent["info"], torrent["info"]['name'])
        
        isLibraryItem = torrent.get('myDownloadHistory', libraryDelete)
        categories = torrent.get('category', ['other']) + ["all"]
        funCalled = False
        
        for key in categories:
#            if key == '?':
#                continue
            try:
                key = key.lower()
                if isLibraryItem:
                    for fun in self.dict_FunList.get((key, True), []): # call all functions for a certain key
                        fun(torrent, libraryDelete and 'delete' or operate)
                        funCalled = True
                # Always notify discovered files (also for library items)
                for fun in self.dict_FunList.get((key, False), []):
                    fun(torrent, operate)
                    funCalled = True
                    
            except Exception, msg:
                #print >> sys.stderr, "abcfileframe: TorrentDataManager update error. Key: %s" % (key), Exception, msg
                #print_exc()
                pass
            
        return funCalled # return if a view was actually notified
    
    def addItem(self, infohash):
        if self.info_dict.has_key(infohash):
            return
        torrent = self.torrent_db.getTorrent(infohash,savemem=True)
        if not torrent:
            return
        torrent[key_infohash] = infohash
        item = self.prepareItem(torrent)
        self.data.append(item)
        self.info_dict[infohash] = item
        self.updateRankList(item, 'add')
        self.notifyView(item, 'add')
    
    
    def setBelongsToMyDowloadHistory(self, infohash, b, secret = False):
        """Set a certain new torrent to be in the download history or not"
        Should not be changed by updateTorrent calls"""
        old_torrent = self.info_dict.get(infohash, None)
        if not old_torrent:
            return
        
        if b:
            old_torrent[key_myDownloadHistory] = True
        else:
            if old_torrent.has_key(key_myDownloadHistory):
                del old_torrent[key_myDownloadHistory]
        
        self.notifyView(old_torrent, 'update', libraryDelete = not b)
        
        
        self.updateRankList(old_torrent, 'update')
        
        if b:    # update buddycast after view was updated
            #self.utility.buddycast.addMyPref(infohash)    # will be called somewhere
            pass
        else:
            self.utility.buddycast.delMyPref(infohash)
                
    def addNewPreference(self, infohash): 
        if self.info_dict.has_key(infohash):
            return
        torrent = self.torrent_db.getTorrent(infohash)
        if not torrent:
            return
        torrent[key_infohash] = infohash
        item = self.prepareItem(torrent)
        torrent[key_myDownloadHistory] = True
        self.data.append(item)
        self.info_dict[infohash] = item
        self.notifyView(item, 'add')
        
    def updateItem(self, infohash):
        old_torrent = self.info_dict.get(infohash, None)
        if not old_torrent:
            return
        torrent = self.torrent_db.getTorrent(infohash)
        if not torrent:
            return
        torrent[key_infohash] = infohash
        item = self.prepareItem(torrent)
        
        #old_torrent.update(item)
        for key in torrent.keys():    # modify reference
            old_torrent[key] = torrent[key]
    
        self.updateRankList(torrent, 'update')
        self.notifyView(old_torrent, 'update')
    
    def deleteItem(self, infohash):
        old_torrent = self.info_dict.get(infohash, None)
        if not old_torrent:
            return
        self.info_dict.pop(infohash)
        # Replaces remove() function because of unicode error
        #self.data.remove(old_torrent)
        remove_torrent_from_list(self.data, old_torrent)
        self.updateRankList(old_torrent, 'delete')
        self.notifyView(old_torrent, 'delete')

    def prepareItem(self, torrent):    # change self.data
        
        info = torrent['info']
        if not info.get('name'):
            print 'Error in torrent. No name found'
        
        torrent[key_length] = info.get('length', 0)
        torrent[key_content_name] = dunno2unicode(info.get('name', '?'))
        if key_torrent_name not in torrent or torrent[key_torrent_name] == '':
            torrent[key_torrent_name] = '?'
        torrent[key_num_files] = int(info.get('num_files', 0))
        torrent[key_date] = info.get('creation date', 0) 
        torrent[key_tracker] = info.get('announce', '')
        torrent[key_leecher] = torrent.get('leecher', -1)
        torrent[key_seeder] = torrent.get('seeder', -1)
        torrent[key_swarmsize] = torrent['seeder'] + torrent['leecher']
        if torrent.has_key('simRank'):
            raise Exception('simRank in database!')
            del torrent['simRank']
            
        # Arno: to save mem I delete some fields here
        del torrent['info']
        
        if 'torrent_dir' in torrent and torrent['torrent_dir'] == self.collected_torrent_dir:
            # Will be determined on the fly
            #print "torrentManager: deleting torrent_dir"
            del torrent['torrent_dir']
            del torrent['torrent_name']
        
        # Thumbnail is read from file only when it is shown on screen by
        # thumbnailViewer or detailsPanel
        return torrent
         
    def updateRankList(self, torrent, operate, initializing = False):
        "Update the ranking list, so that it always shows the top20 most similar torrents"
        
        if DEBUG_RANKING:
            print >>sys.stderr,'torrentManager: UpdateRankList: %s, for: %s' % (operate, repr(torrent.get('content_name')))
        
        sim = torrent.get('relevance')
        good = sim > 0 and torrent.get('status') == 'good' and not torrent.get('myDownloadHistory', False)
        infohash = torrent.get('infohash')
        updated = False
        dataTuple = (sim, infohash)
        
        if operate == 'add' and good:
            insort(self.rankList, dataTuple)
            
        
        elif operate == 'update':
            # Check if not already there
            for rankedTuple in self.rankList:
                infohashRanked = rankedTuple[1]
                if infohash == infohashRanked:
                    updated = True
                    self.rankList.remove(rankedTuple)
                    self.updateRemovedItem(infohash, initializing)
                    self.recompleteRankList()
                    break
                    
            if good:
                # be sure that ungood torrents are at the bottom of the list
                insort(self.rankList, dataTuple)
            
        elif operate == 'delete':
            for rankedTuple in self.rankList:
                infohashRanked = rankedTuple[1]
                if infohash == infohashRanked:
                    updated = True
                    self.rankList.remove(rankedTuple)
                    self.updateRemovedItem(infohash, initializing)
                    self.recompleteRankList()
                    break
                
                
        # Always leave rankList with <=20 items
        #assert initializing or len(self.data) < 20 or len(self.rankList) in [20,21],'torrentManager: Error, ranklist had length: %d' % len(self.rankList)
        
        droppedItemInfohash = None
        if len(self.rankList) == 21:
            (sim, droppedItemInfohash) = self.rankList.pop(0)

            
        if updated or dataTuple in self.rankList:
            # Only update the items when something changed in the ranking list

            if droppedItemInfohash:
                # if we have added a new ranked item, one is dropped out of the list
                # the rank of this one will be removed
                self.updateRemovedItem(droppedItemInfohash, initializing)
                
            self.updateRankedItems(initializing)
#            if not initializing:
#                print 'RankList is now: %s' % self.rankList
        
        if DEBUG_RANKING:
            self.printRankList()
        
    def updateRemovedItem(self, infohash, initializing):
        if self.info_dict.has_key(infohash):
            torrent = self.info_dict[infohash]
            if DEBUG_RANKING:
                print >>sys.stderr,'torrentManager: Del rank %d of %s' % (torrent.get('simRank', -1), repr(torrent.get('content_name')))
            if torrent.has_key('simRank'):
                del torrent['simRank']
            if not initializing:
                self.notifyView(torrent, 'update')
        elif DEBUG_RANKING:
            raise Exception('(removeRank) Not found infohash: %s in info_dict.' % repr(infohash))
            
    
    def updateRankedItems(self, initializing):
        rank = len(self.rankList)
        for (sim, infohash) in self.rankList:
            if self.info_dict.has_key(infohash):
                torrent = self.info_dict[infohash]
                if DEBUG_RANKING:
                    print >>sys.stderr,'torrentManager: Give rank %d to %s' % (rank, repr(torrent.get('content_name')))
                torrent[key_simRank] = rank
                if not initializing:
                    self.notifyView(torrent, 'update')
            else:
                raise Exception('Not found infohash: %s in info_dict.' % repr(infohash))
            rank -= 1
        
            
            
    def recompleteRankList(self):
        """
        Get most similar item with status=good, not in library and not in ranklist 
        and insort it in ranklist
        """
        highest_sim = 0
        highest_infohash = None
        for torrent in self.data:
            sim = torrent.get('relevance')
            good = torrent.get('status') == 'good' and not torrent.get('myDownloadHistory', False)
            infohash = torrent.get('infohash')
            
            if sim > 0 and good and (sim, infohash) not in self.rankList:
                # item is not in rankList
                if sim > highest_sim:
                    highest_sim = sim
                    highest_infohash = infohash
                    
        if highest_infohash:
            insort(self.rankList, (highest_sim, highest_infohash))
        
    def printRankList(self):
        self.rankList.reverse()
        print >>sys.stderr,'torrentManager: Ranklist:'
        rank = 1
        
        for (sim, infohash) in self.rankList:
            if self.info_dict.has_key(infohash):
                torrent = self.info_dict[infohash]
                print >>sys.stderr,'torrentManager: %d: %.2f, %s' % (rank, torrent.get('relevance', -1), repr(torrent.get('content_name', 'no name')))
            else:
                print_stack()
                print >>sys.stderr,'torrentManager: Not found infohash: %s in info_dict.' % repr(infohash)
            rank += 1
        
        self.rankList.reverse()
        
        print >>sys.stderr,'torrentManager: Checking all torrents'
        wrong = right = 0
        for infohash, torrent in self.info_dict.items():
            inRankList = False
            for (s, infohashRanked) in self.rankList:
                if infohash == infohashRanked:
                    inRankList = True
            if not inRankList:
                if torrent.has_key('simRank'):
                    wrong += 1
                    print >>sys.stderr,'torrentManager: Torrent %s was not in ranklist: sim: %f, rank: %d' % (repr(torrent.get('content_name')), torrent.get('relevance'), torrent['simRank'])
                else:
                    right+=1
        print >>sys.stderr,'torrentManager: %d right, %d wrong torrents' % (right, wrong)
        if wrong > 0:
            raise Exception('wrong torrents')
            
    def setSearchKeywords(self,wantkeywords, mode):
        self.searchkeywords[mode] = wantkeywords
         
    def inSearchMode(self, mode):
        return bool(self.searchkeywords[mode])
    
    def search(self, data, mode):
#        if self.searchkeywords[mode] == self.oldsearchkeywords[mode] and len(self.hits) > 0:
#            if DEBUG:
#                print >>sys.stderr,"torrentDataManager: search: returning old hit list",len(self.hits)
#            return self.hits
            
        if DEBUG:
            print >>sys.stderr,"torrentDataManager: search: Want",self.searchkeywords[mode]
        
        if len(self.searchkeywords[mode]) == 0 or len(self.searchkeywords[mode]) == 1 and self.searchkeywords[mode][0] == '':
            return data
        
        self.hits = self.keywordsearch.search(data, self.searchkeywords[mode])
        
        return self.hits

    def addRemoteResults(self, data, mode, cat):
        if self.remoteHits and self.remoteHits[0] == self.searchkeywords[mode]:
            numResults = 0
            def catFilter(item):
                icat = item.get('category')
                if type(icat) == list:
                    icat = icat[0].lower()
                elif type(icat) == str:
                    icat = icat.lower()
                else:
                    return False
                return icat == cat or cat == 'all'
            
            catResults = filter(catFilter, self.remoteHits[1])
            if DEBUG:
                print >> sys.stderr, "Adding %d remote results (%d in category)" % (len(self.remoteHits[1]), len(catResults))
            
            
            for remoteItem in catResults:
                if find_content_in_dictlist(data, remoteItem) == -1:
                    data.append(remoteItem)
                    numResults+=1
            self.standardOverview.setSearchFeedback('remote', False, numResults, self.searchkeywords[mode])
        
        
    def remoteSearch(self,kws,maxhits=None):
        if DEBUG:
            print >>sys.stderr,"torrentDataManager: remoteSearch",kws
        
        haystack = []
        for torrent in self.data:
            if torrent['status'] != 'good':
                continue
            haystack.append(torrent)
        hits = self.keywordsearch.search(haystack,kws)
        if maxhits is None:
            return hits
        else:
            return hits[:maxhits]

    
    def gotRemoteHits(self,permid,kws,answers,mode='filesMode'):
        """ Called by standardOverview """
        if DEBUG:
            print >>sys.stderr,"torrentDataManager: gotRemoteHist: got",len(answers)
        
        # We got some replies. First check if they are for the current query
        if self.searchkeywords[mode] == kws:
            self.remoteHits = (self.searchkeywords[mode], [])
            numResults = 0
            for key,value in answers.iteritems():
                
                if self.info_dict.has_key(key):
                    continue # do not show results we have ourselves
                
                value['infohash'] = key
                # Set from which peer this info originates
                value['query_permid'] = permid
                # We trust the peer
                value['status'] = 'good'
                
                # Add values to enable filters (popular/rec/size) to work
                value['swarmsize'] = value['seeder']+value['leecher']
                value['relevance'] = 0
                value['date'] = None # gives '?' in GUI
                
                if DEBUG:
                    print >>sys.stderr,"torrentDataManager: gotRemoteHist: appending hit",`value['content_name']`
                    value['content_name'] = 'REMOTE '+value['content_name']
                self.hits.append(value)
                self.remoteHits[1].append(value)
                if self.notifyView(value, 'add'):
                    numResults +=1
            self.standardOverview.setSearchFeedback('remote', False, numResults, self.searchkeywords[mode])
            return True
        elif DEBUG:
            print >>sys.stderr,"torrentDataManager: gotRemoteHist: got hits for",kws,"but current search is for",self.searchkeywords[mode]
        return False


    def getFromSource(self,source):
        hits = []
        for torrent in self.data:
            if torrent['source'] == source:
                hits.append(torrent)
        return hits
    
    def getSimItems(self, infohash, num=15):
        return self.owner_db.getSimItems(infohash, num)

    def getNumDiscoveredFiles(self):
        if not self.isDataPrepared:
            return -1
        else:
            ntorrents = self.metadata_handler.get_num_torrents()
            if ntorrents < 0:    # metadatahandler is not ready to load torents yet
                ntorrents = len(self.data)
            return ntorrents
        
    def setSecret(self, infohash, b):
        if b:
            self.torrent_db.updateTorrent(infohash, **{'secret':True})
        else:
            self.torrent_db.updateTorrent(infohash, **{'secret':False})
        
            
