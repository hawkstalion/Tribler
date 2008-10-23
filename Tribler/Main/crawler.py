#!/usr/bin/python

import sys
import shutil
import time
import tempfile
import random
from traceback import print_exc

from Tribler.Core.API import *

if __name__ == "__main__":

    if len(sys.argv) == 1:
        print "Usage: python Tribler/Main/crawler.py [database|seedingstats|friendship|natcheck]+"
        exit(1)

    print "Press Ctrl-C to stop the crawler"

    sscfg = SessionStartupConfig()
#     statedir = tempfile.mkdtemp()
#     sscfg.set_state_dir(statedir)
#     sscfg.set_listen_port(random.randint(10000, 60000))
    sscfg.set_megacache(True)
    sscfg.set_overlay(True)
    sscfg.set_dialback(False)
    sscfg.set_internal_tracker(False)

    s = Session(sscfg)

# 22/10/08. Boudewijn: connect to a specific peer
    # connect to a specific peer using the overlay
#     def after_connect(*args):
#         print args
#     from Tribler.Core.Overlay.SecureOverlay import SecureOverlay
#     overlay = SecureOverlay.getInstance()
#     overlay.connect_dns(("130.161.158.24", 7762), after_connect)

    # condition variable would be prettier, but that don't listen to 
    # KeyboardInterrupt
    #time.sleep(sys.maxint/2048)
    try:
        while True:
            x = sys.stdin.read()
    except:
        print_exc()
    
    s.shutdown()
    time.sleep(3)    

    