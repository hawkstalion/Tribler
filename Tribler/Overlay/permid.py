# Written by Arno Bakker
# see LICENSE.txt for license information

import sys
from sha import sha
from base64 import encodestring
from copy import deepcopy
import traceback,os

from M2Crypto import Rand,EC,EVP
from BitTornado.bencode import bencode, bdecode
from BitTornado.BT1.MessageID import *

DEBUG = 0

# Internal constants
keypair_ecc_curve = EC.NID_sect233k1
num_random_bits = 1024*8 # bits

# Protocol states
STATE_INITIAL = 0
STATE_AWAIT_R1 = 1
STATE_AWAIT_R2 = 2
STATE_AUTHENTICATED = 3
STATE_FAILED = 4

# Global variable holding our EC keypair
_ec_keypair = None

# Exported functions
def init(config_dir = None):
    Rand.load_file(get_rand_filename(config_dir.encode(sys.getfilesystemencoding())), -1) 
    try:
        read_keypair(config_dir)
    except:
        generate_keypair()
        save_keypair(config_dir)
        save_pub_key(config_dir)

def exit(config_dir = None):
    Rand.save_file(get_rand_filename(config_dir.encode(sys.getfilesystemencoding())))

# def show_permid(permid):
# See Tribler/utilities.py

def permid_for_user(permid):
    # Full BASE64-encoded 
    return encodestring(permid).replace("\n","")

# For convenience
def sign_data(plaintext):
    global _ec_keypair
    digest = sha(plaintext).digest()
    return _ec_keypair.sign_dsa_asn1(digest)

def verify_data(plaintext,permid,blob):
    pubkey = EC.pub_key_from_der(permid)
    digest = sha(plaintext).digest()
    return pubkey.verify_dsa_asn1(digest,blob)

def get_my_keypair():
    global _ec_keypair
    return _ec_keypair
    

# Internal functions
def generate_keypair():
    global _ec_keypair
    _ec_keypair=EC.gen_params(keypair_ecc_curve)
    _ec_keypair.gen_key()

def read_keypair(config_dir = None):
    global _ec_keypair
    _ec_keypair=EC.load_key(get_keypair_filename(config_dir))

def save_keypair(config_dir = None):
    global _ec_keypair
    _ec_keypair.save_key(get_keypair_filename(config_dir), None)    

def save_pub_key(config_dir = None):
    global _ec_keypair
    _ec_keypair.save_pub_key(get_pub_key_filename(config_dir))    

def get_rand_filename(config_dir=None):
    return make_filename(config_dir,'randpool.dat')

def get_keypair_filename(config_dir=None):
    return make_filename(config_dir,'ec.pem')

def get_pub_key_filename(config_dir=None):
    return make_filename(config_dir,'ecpub.pem')

def make_filename(config_dir,filename):
    if config_dir is None:
        return filename
    else:
        return os.path.join(config_dir,filename)

#
# The following methods and ChallengeResponse class implement a
# Challenge/Response identification protocol, notably the
# ISO/IEC 9798-3 protocol, as described in $10.3.3 (ii) (2) of the 
# ``Handbook of Applied Cryptography''by  Alfred J. Menezes et al.
#

def generate_challenge():
    randomB = Rand.rand_bytes(num_random_bits/8)
    return [randomB,bencode(randomB)]

def check_challenge(cdata):
    try:
        randomB = bdecode(cdata)
    except:
        return None
    if len(randomB) != num_random_bits/8:
        return None
    else:
        return randomB

def generate_response1(randomB,peeridB,keypairA):
    randomA = Rand.rand_bytes(num_random_bits/8)
    response1 = {}
    response1['certA'] = str(keypairA.pub().get_der())
    response1['rA'] = randomA
    response1['B'] = peeridB
    response1['SA'] = sign_response(randomA,randomB,peeridB,keypairA)
    return [randomA,bencode(response1)]

def check_response1(rdata1,randomB,peeridB):
    try:
        response1 = bdecode(rdata1)
    except:
        return [None,None]
    if response1['B'] != peeridB:
        return [None,None]
    pubA_der = response1['certA']
    pubA = EC.pub_key_from_der(pubA_der)
    sigA = response1['SA']
    randomA = response1['rA']
    if verify_response(randomA,randomB,peeridB,pubA,sigA):
        return [randomA,pubA]
    else:
        return [None,None]
    
def generate_response2(randomA,peeridA,randomB,keypairB):
    response2 = {}
    response2['certB'] = str(keypairB.pub().get_der())
    response2['A'] = peeridA
    response2['SB'] = sign_response(randomB,randomA,peeridA,keypairB)
    return bencode(response2)

def check_response2(rdata2,randomA,peeridA,randomB,peeridB):
    try:
        response2 = bdecode(rdata2)
    except:
        return None
    if response2['A'] != peeridA:
        return None
    pubB_der = response2['certB']
    pubB = EC.pub_key_from_der(pubB_der)
    sigB = response2['SB']
    if verify_response(randomB,randomA,peeridA,pubB,sigB):
        return pubB
    else:
        return None

def sign_response(randomA,randomB,peeridB,keypairA):
    list = [ randomA, randomB, peeridB ]
    blist = bencode(list)
    digest = sha(blist).digest()
    blob = keypairA.sign_dsa_asn1(digest)
    return blob

def verify_response(randomA,randomB,peeridB,pubA,sigA):
    list = [ randomA, randomB, peeridB ]
    blist = bencode(list)
    digest = sha(blist).digest()
    return pubA.verify_dsa_asn1(digest,sigA)
    

# External functions

def create_torrent_signature(response):
    bresponse = bencode(response)
    digester = sha(bresponse[:])
    digest = digester.digest()
    if _ec_keypair is None:
        return False
    try:
        sigstr = _ec_keypair.sign_dsa_asn1(digest)
        response['signature'] = sigstr
        response['signer'] = str(_ec_keypair.pub().get_der())
        return True
    except Exception, e:
        traceback.print_exc()
        return False
    
def verify_torrent_signature(response):
    r = deepcopy(response)
    signature = r['signature']
    signer = r['signer']
    del r['signature']
    del r['signer']
    bresponse = bencode(r)
    digester = sha(bresponse[:])
    digest = digester.digest()
    return do_verify_torrent_signature(digest,signature,signer)


# Internal

def do_verify_torrent_signature(digest,sigstr,permid):
    if permid is None:
        return False
    try:
        ecpub = EC.pub_key_from_der(permid)
        if ecpub is None:
            return False
        intret = ecpub.verify_dsa_asn1(digest,sigstr)
        return intret == 1
    except Exception, e:
        print >> sys.stderr,"permid: Exception in verify_torrent_signature:",str(e) 
        return False


# Exported classes
class PermIDException(Exception): pass

class ChallengeResponse:
    """ Exchange Challenge/Response via Overlay Swarm """

    def __init__(self, my_keypair, my_id, secure_overlay):
        self.my_keypair = my_keypair
        self.my_id = my_id
        self.secure_overlay = secure_overlay

        self.my_random = None
        self.peer_id = None
        self.peer_random = None
        self.peer_pub = None
        self.state = STATE_INITIAL
        # Calculate message limits:
        [dummy_random,cdata] = generate_challenge()
        [dummy_random1,rdata1] = generate_response1(dummy_random,my_id,self.my_keypair)
        rdata2 = generate_response2(dummy_random,my_id,dummy_random,self.my_keypair)
        self.minchal = 1+len(cdata) # 1+ = message type
        self.minr1 = 1+len(rdata1) - 1 # Arno: hack, also here, just to be on the safe side
        self.minr2 = 1+len(rdata2) - 1 # Arno: hack, sometimes the official minimum is too big

    def starting_party(self,locally_initiated):
        if self.state == STATE_INITIAL and locally_initiated:
            self.state = STATE_AWAIT_R1
            return True
        else:
            return False

    def create_challenge(self):
        [self.my_random,cdata] = generate_challenge()
        return cdata

    def got_challenge_event(self,cdata,peer_id):
        if self.state != STATE_INITIAL:
            self.state = STATE_FAILED
            if DEBUG:
                print >> sys.stderr, "Got unexpected CHALLENGE message"
            raise PermIDException
        self.peer_random = check_challenge(cdata)
        if self.peer_random is None:
            self.state = STATE_FAILED
            if DEBUG:
                print >> sys.stderr,"Got bad CHALLENGE message"
            raise PermIDException
        self.peer_id = peer_id
        [self.my_random,rdata1] = generate_response1(self.peer_random,peer_id,self.my_keypair)
        self.state = STATE_AWAIT_R2
        return rdata1

    def got_response1_event(self,rdata1,peer_id):
        if self.state != STATE_AWAIT_R1:
            self.state = STATE_FAILED
            if DEBUG:
                print >> sys.stderr,"Got unexpected RESPONSE1 message"
            raise PermIDException
        [randomA,peer_pub] = check_response1(rdata1,self.my_random,self.my_id)
        if randomA is None:
            self.state = STATE_FAILED
            if DEBUG:
                print >> sys.stderr,"Got bad RESPONSE1 message"
            raise PermIDException
        self.peer_id = peer_id
        self.peer_random = randomA
        self.peer_pub = peer_pub
        self.set_peer_authenticated()
        rdata2 = generate_response2(self.peer_random,self.peer_id,self.my_random,self.my_keypair)
        return rdata2

    def got_response2_event(self,rdata2):
        if self.state != STATE_AWAIT_R2:
            self.state = STATE_FAILED
            if DEBUG:
                print >> sys.stderr,"Got unexpected RESPONSE2 message"
            raise PermIDException
        self.peer_pub = check_response2(rdata2,self.my_random,self.my_id,self.peer_random,self.peer_id)
        if self.peer_pub is None:
            self.state = STATE_FAILED
            if DEBUG:
                print >> sys.stderr,"Got bad RESPONSE2 message, authentication failed."
            raise PermIDException
        else:
            self.set_peer_authenticated()

    def set_peer_authenticated(self):
        if DEBUG:
            print >> sys.stderr,"permid: Challenge response succesful!"
        self.state = STATE_AUTHENTICATED

    def get_peer_authenticated(self):
        return self.state == STATE_AUTHENTICATED
    
    def get_peer_permid(self):
        if self.state != STATE_AUTHENTICATED:
            raise PermIDException
        return self.peer_pub.get_der()

    def get_auth_peer_id(self):
        if self.state != STATE_AUTHENTICATED:
            raise PermIDException
        return self.peer_id

    def get_challenge_minlen(self):
        return self.minchal

    def get_response1_minlen(self):
        return self.minr1

    def get_response2_minlen(self):
        return self.minr2

#---------------------------------------

    def start_cr(self, conn):
        if not self.get_peer_authenticated() and self.starting_party(conn.is_locally_initiated()):
            self.send_challenge(conn)

    def send_challenge(self, conn):
        cdata = self.create_challenge()
        conn.send_message(CHALLENGE + str(cdata) )

    def got_challenge(self, cdata, conn):
        rdata1 = self.got_challenge_event(cdata, conn.get_unauth_peer_id())
        conn.send_message(RESPONSE1 + rdata1)

    def got_response1(self, rdata1, conn):
        rdata2 = self.got_response1_event(rdata1, conn.get_unauth_peer_id())
        conn.send_message(RESPONSE2 + rdata2)
        # get_peer_permid() throws exception if auth has failed
        self.secure_overlay.got_auth_connection(conn,self.get_peer_permid(),self.get_auth_peer_id())
     
    def got_response2(self, rdata2, conn):
        self.got_response2_event(rdata2)
        if self.get_peer_authenticated():
            #conn.send_message('')    # Send KeepAlive message as reply
            self.secure_overlay.got_auth_connection(conn,self.get_peer_permid(),self.get_auth_peer_id())


    def got_message(self, conn, message):
        """ Handle message for PermID exchange and return if the message is valid """
        
        if not conn:
            return False
        t = message[0]
        if message[1:]:
            msg = message[1:]
            
        if t == CHALLENGE:
            if len(message) < self.get_challenge_minlen():
                if DEBUG:
                    print >> sys.stderr,"permid: Close on bad CHALLENGE: msg len",len(message)
                self.state = STATE_FAILED
                return False
            try:
                self.got_challenge(msg, conn)
            except Exception,e:
                if DEBUG:
                    print >> sys.stderr,"permid: Close on bad CHALLENGE: exception",str(e)
                    traceback.print_exc()
                return False
        elif t == RESPONSE1:
            if len(message) < self.get_response1_minlen():
                if DEBUG:
                    print >> sys.stderr,"permid: Close on bad RESPONSE1: msg len",len(message)
                self.state = STATE_FAILED
                return False
            try:
                self.got_response1(msg, conn)
            except Exception,e:
                if DEBUG:
                    print >> sys.stderr,"permid: Close on bad RESPONSE1: exception",str(e)
                    traceback.print_exc()
                return False
        elif t == RESPONSE2:
            if len(message) < self.get_response2_minlen():
                if DEBUG:
                    print >> sys.stderr,"permid: Close on bad RESPONSE2: msg len",len(message)
                self.state = STATE_FAILED
                return False
            try:
                self.got_response2(msg, conn)
            except Exception,e:
                if DEBUG:
                    print >> sys.stderr,"permid: Close on bad RESPONSE2: exception",str(e)
                    traceback.print_exc()
                return False
        else:
            return False
        return True

if __name__ == '__main__':
    init()
#    ChallengeResponse(None, None)
