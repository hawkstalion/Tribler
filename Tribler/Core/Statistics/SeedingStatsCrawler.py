# see LICENSE.txt for license information

from Tribler.Core.CacheDB.sqlitecachedb import SQLiteCacheDB
from Tribler.Core.CacheDB.SqliteSeedingStatsCacheDB import *

DEBUG = False

class SeedingStatsCrawler:
    __single = None

    @classmethod
    def get_instance(cls, *args, **kargs):
        if not cls.__single:
            cls.__single = cls(*args, **kargs)
        return cls.__single

    def __init__(self):
        self._sqlite_cache_db = SQLiteSeedingStatsCacheDB.getInstance()

    def query_initiator(self, permid, selversion, request_callback):
        """
        Established a new connection. Send a CRAWLER_DATABASE_QUERY request.
        @param permid The Tribler peer permid
        @param selversion The oberlay protocol version
        @param request_callback Call this function one or more times to send the requests: request_callback(message_id, payload)
        """
        if DEBUG: 
            print >>sys.stderr, "crawler: SeedingStatsDB_query_initiator"
        
        try:
            sql_query = "SELECT MAX(timestamp) FROM SeedingStats WHERE permID='%s' ORDER BY timestamp DESC"%(bin2str(permid), time())
            cursor = self._sqlite_cache_db.execute_read(sql_query)
        except:
            print_exc()
        else:
            if cursor:
                res = list(cursor)[0][0]
                if res is not None:
                    return request_callback(CRAWLER_SEEDINGSTATS_QUERY, "SELECT * FROM SeedingStats WHERE crawled = 0 and timestamp BETWEEN %s and %s ORDER BY timestamp DESC"%(res[0][0], time()))
                else:
                    return request_callback(CRAWLER_SEEDINGSTATS_QUERY, "SELECT * FROM SeedingStats WHERE crawled = 0 and timestamp BETWEEN %s and %s ORDER BY timestamp DESC"%(0, time()))
    
    
    def query_initiator(self, permid, selversion, request_callback):
        """
        Established a new connection. Send a CRAWLER_DATABASE_QUERY request.
        @param permid The Tribler peer permid
        @param selversion The oberlay protocol version
        @param request_callback Call this function one or more times to send the requests: request_callback(message_id, payload)
        """
        if DEBUG: 
            print >>sys.stderr, "crawler: SeedingStatsDB_update_settings_initiator"
        
        try:
            sql_query = "SELECT MAX(timestamp) FROM SeedingStats WHERE permID='%s' ORDER BY timestamp DESC"%(bin2str(permid), time())
            cursor = self._sqlite_cache_db.execute_read(sql_query)
        except:
            print_exc()
        else:
            if cursor:
                res = list(cursor)[0][0]
                if res is not None:
                    return request_callback(CRAWLER_SEEDINGSTATS_QUERY, cPickle.dumps(["SELECT * FROM SeedingStats WHERE crawled = 0 and timestamp BETWEEN %s and %s ORDER BY timestamp DESC"%(res[0][0], time()), 'UPDATE SeedingStats SET crawled=1 WHERE crawled=0 and timestamp <=%s'%res]))
                else:
                    return request_callback(CRAWLER_SEEDINGSTATS_QUERY, cPickle.dumps(["SELECT * FROM SeedingStats WHERE crawled = 0 and timestamp BETWEEN %s and %s ORDER BY timestamp DESC"%(0, time()), 'UPDATE SeedingStats SET crawled=1 WHERE crawled=0 and timestamp <=0']))
    
    
    def update_settings_initiator(self, permid, selversion, request_callback):
        """
        Established a new connection. Send a CRAWLER_DATABASE_QUERY request.
        @param permid The Tribler peer permid
        @param selversion The oberlay protocol version
        @param request_callback Call this function one or more times to send the requests: request_callback(message_id, payload)
        """
        if DEBUG: 
            print >>sys.stderr, "crawler: SeedingStatsDB_update_settings_initiator"
        
        try:
            sql_update = "UPDATE SeedingStatsSettings SET crawling_interval=%s WHERE crawling_enabled=%s"%(1800, 1)
        except:
            print_exc()
        else:
            return request_callback(CRAWLER_SEEDINGSTATS_QUERY, cPickle.dumps(sql_update))
               
    
    def handle_crawler_request(self, permid, selversion, channel_id, message, reply_callback):
        """
        Received a CRAWLER_DATABASE_QUERY request.
        @param permid The Crawler permid
        @param selversion The overlay protocol version
        @param channel_id Identifies a CRAWLER_REQUEST/CRAWLER_REPLY pair
        @param message The message payload
        @param reply_callback Call this function once to send the reply: reply_callback(payload [, error=123])
        """
        if DEBUG:
            print >> sys.stderr, "crawler: handle_crawler_SeedingStats_request", message

        # execute the sql
        sql_query, sql_update = cPickle.loads(message)
        
        try:
            cursor = self._sqlite_cache_db.execute_read(sql_query)
        except Exception, e:
            reply_callback(str(e), 1)
        else:
            if cursor:
                res = list(cursor)
                reply_callback(cPickle.dumps(res, 2))

                if timestamp:
                    # update crawled records
                    self._sqlite_cache_db.execute_write(sql_update)
            else:
                reply_callback("error", 1)

        return True

    def handle_crawler_reply(self, permid, selversion, channel_id, message, reply_callback):
        """
        Received a CRAWLER_DATABASE_QUERY request.
        @param permid The Crawler permid
        @param selversion The overlay protocol version
        @param channel_id Identifies a CRAWLER_REQUEST/CRAWLER_REPLY pair
        @param message The message payload
        @param request_callback Call this function one or more times to send the requests: request_callback(message_id, payload)
        """
        if DEBUG:
            print >> sys.stderr, "olapps: handle_crawler_SeedingStats_reply"

        try:
            results = cPickle.loads(message, 2)
            values = map(tuple, results)
            self._sqlite_cache_db.insertMany("SeedingStats", values)
        except Exception, e:
            print_exc()
            return False

        return True

    
    def handle_crawler_update_settings_request(self, permid, selversion, channel_id, message, reply_callback):
        """
        Received a CRAWLER_DATABASE_QUERY request.
        @param permid The Crawler permid
        @param selversion The overlay protocol version
        @param channel_id Identifies a CRAWLER_REQUEST/CRAWLER_REPLY pair
        @param message The message payload
        @param reply_callback Call this function once to send the reply: reply_callback(payload [, error=123])
        """
        if DEBUG:
            print >> sys.stderr, "crawler: handle_crawler_SeedingStats_request", message

        # execute the sql
        sql_update = cPickle.loads(message)
        
        try:
            self._sqlite_cache_db.execute_write(sql_query)
        except Exception, e:
            reply_callback(str(e), 1)

        return True

    def handle_crawler_update_setings_reply(self, permid, selversion, channel_id, message, reply_callback):
        """
        Received a CRAWLER_DATABASE_QUERY request.
        @param permid The Crawler permid
        @param selversion The overlay protocol version
        @param channel_id Identifies a CRAWLER_REQUEST/CRAWLER_REPLY pair
        @param message The message payload
        @param request_callback Call this function one or more times to send the requests: request_callback(message_id, payload)
        """
        if DEBUG:
            print >> sys.stderr, "olapps: handle_crawler_SeedingStats_reply"

        return True
