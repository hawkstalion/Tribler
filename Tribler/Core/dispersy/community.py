"""
the community module provides the Community baseclass that should be used when a new Community is
implemented.  It provides a simplified interface between the Dispersy instance and a running
Community instance.

@author: Boudewijn Schoon
@organization: Technical University Delft
@contact: dispersy@frayja.com
"""

from hashlib import sha1
from math import sqrt
from random import gauss

from authentication import NoAuthentication, MemberAuthentication, MultiMemberAuthentication
from bloomfilter import BloomFilter
from conversion import DefaultConversion
from crypto import ec_generate_key, ec_to_public_bin, ec_to_private_bin
from decorator import documentation
from destination import CommunityDestination, AddressDestination
from dispersy import Dispersy
from dispersydatabase import DispersyDatabase
from distribution import FullSyncDistribution, LastSyncDistribution, DirectDistribution
from encoding import encode
from member import Private, MasterMember, MyMember, Member
from message import Message, DropMessage
from resolution import PublicResolution
from timeline import Timeline

if __debug__:
    from dprint import dprint

class Community(object):
    @classmethod
    def create_community(cls, my_member, *args, **kargs):
        """
        Create a new community owned by my_member.

        Each unique community, that exists out in the world, is identified by a public/private key
        pair.  When the create_community method is called such a key pair is generated.

        Furthermore, my_member will be granted permission to use all the messages that the community
        provides.

        @param my_member: The Member that will be granted Permit, Authorize, and Revoke for all
         messages.
        @type my_member: Member

        @param args: optional argumets that are passed to the community constructor.
        @type args: tuple

        @param kargs: optional keyword arguments that are passed to the community constructor.
        @type args: dictionary

        @return: The created community instance.
        @rtype: Community
        """
        assert isinstance(my_member, MyMember), my_member

        # master key and community id
        ec = ec_generate_key(u"high")
        public_key = ec_to_public_bin(ec)
        private_key = ec_to_private_bin(ec)
        cid = sha1(public_key).digest()

        database = DispersyDatabase.get_instance()
        with database as execute:
            execute(u"INSERT INTO community (user, cid, public_key) VALUES(?, ?, ?)", (my_member.database_id, buffer(cid), buffer(public_key)))
            database_id = database.last_insert_rowid
            execute(u"INSERT INTO user (mid, public_key) VALUES(?, ?)", (buffer(cid), buffer(public_key)))
            execute(u"INSERT INTO key (public_key, private_key) VALUES(?, ?)", (buffer(public_key), buffer(private_key)))
            execute(u"INSERT INTO routing (community, host, port, incoming_time, outgoing_time) SELECT ?, host, port, incoming_time, outgoing_time FROM routing WHERE community = 0", (database_id,))

        # new community instance
        community = cls(cid, *args, **kargs)

        # authorize MY_MEMBER for each message
        permission_triplets = []
        for message in community.get_meta_messages():
            if not isinstance(message.resolution, PublicResolution):
                for allowed in (u"authorize", u"revoke", u"permit"):
                    permission_triplets.append((my_member, message, allowed))
        if permission_triplets:
            community.create_dispersy_authorize(permission_triplets, sign_with_master=True)

        # send out my initial dispersy-identity
        community.create_identity()

        return community

    @classmethod
    def join_community(cls, master_key, my_member, *args, **kargs):
        """
        Join an existing community.

        Once you have discovered an existing community, i.e. you have obtained the public master key
        from a community, you can join this community.

        Joining a community does not mean that you obtain permissions in that community, those will
        need to be granted by another member who is allowed to do so.  However, it will let you
        receive, send, and disseminate messages that do not require any permission to use.

        @param master_key: The public key of the master member of the community that is to be
         joined.
        @type master_key: string

        @param my_member: The Member that will be granted Permit, Authorize, and Revoke for all
         messages.
        @type my_member: Member

        @param args: optional argumets that are passed to the
        community constructor.
        @type args: tuple

        @param kargs: optional keyword arguments that are passed to
        the community constructor.
        @type args: dictionary

        @return: The created community instance.
        @rtype: Community

        @todo: we should probably change MASTER_KEY to require a master member instance, or the cid
         that we want to join.
        """
        assert isinstance(master_key, str)
        assert isinstance(my_member, MyMember)
        cid = sha1(master_key).digest()
        database = DispersyDatabase.get_instance()
        database.execute(u"INSERT INTO community(user, cid, public_key) VALUES(?, ?, ?)",
                         (my_member.database_id, buffer(cid), buffer(master_key)))

        # new community instance
        community = cls(cid, *args, **kargs)

        # send out my initial dispersy-identity
        community.create_identity()

        return community

    @staticmethod
    def load_communities():
        """
        Load all joined or created communities of this type.

        Typically the load_communities is called when the main application is launched.  This will
        ensure that all communities are loaded and attached to Dispersy.

        @return: A list with zero or more Community instances.
        @rtype: list
        """
        raise NotImplementedError()

    def __init__(self, cid):
        """
        Initialize a community.

        Generally a new community is created using create_community.  Or an existing community is
        loaded using load_communities.  These two methods prepare and call this __init__ method.

        @param cid: The community identifier, i.e. the sha1 digest over the public key of the
         community master member.
        @type cid: string
        """
        assert isinstance(cid, str)
        assert len(cid) == 20

        # community identifier
        self._cid = cid

        # dispersy
        self._dispersy = Dispersy.get_instance()
        self._dispersy_database = DispersyDatabase.get_instance()

        try:
            community_id, master_key, user_public_key = self._dispersy_database.execute(u"""
            SELECT community.id, community.public_key, user.public_key
            FROM community
            LEFT JOIN user ON community.user = user.id
            WHERE cid == ?
            LIMIT 1""", (buffer(self._cid),)).next()

            # the database returns <buffer> types, we use the binary <str> type internally
            master_key = str(master_key)
            user_public_key = str(user_public_key)

        except StopIteration:
            raise ValueError(u"Community not found in database")
        self._database_id = community_id
        self._my_member = MyMember.get_instance(user_public_key)
        self._master_member = MasterMember.get_instance(master_key)

        # define all available messages
        self._meta_messages = {}
        for meta_message in self._dispersy.initiate_meta_messages(self):
            assert meta_message.name not in self._meta_messages
            self._meta_messages[meta_message.name] = meta_message
        for meta_message in self.initiate_meta_messages():
            assert meta_message.name not in self._meta_messages
            self._meta_messages[meta_message.name] = meta_message

        # the list with bloom filters.  the list will grow as the global time increases.  older time
        # ranges are at higher indexes in the list, new time ranges are inserted at the start of the
        # list.
        self._bloom_filter_step = 1000
        self._bloom_filter_size = (10, 512) # 10, 512 -> 640 bytes
        self._bloom_filters = [(1, self._bloom_filter_step, BloomFilter(*self._bloom_filter_size))]

        # dictionary containing available conversions.  currently only contains one conversion.
        self._conversions = {}
        self.add_conversion(DefaultConversion(self), True)

        # initial timeline.  the timeline will keep track of member permissions
        self._timeline = Timeline(self)

        # tell dispersy that there is a new community
        self._dispersy.add_community(self)

        # the subjective sets.  the dictionary contains all our, most recent, subjective sets per
        # cluster.  These are made when a meta message uses the SubjectiveDestination policy.
        # self._subjective_sets = self.get_subjective_sets(self._my_member)

    @property
    def dispersy_sync_interval(self):
        """
        The interval between sending dispersy-sync messages.
        @rtype: float
        """
        return 20.0

    @property
    def dispersy_sync_bloom_filters(self):
        """
        The bloom filters that should be sent this interval.

        The list that is returned must contain (time_low, time_high, bloom_filter) tuples.  For the
        most recent bloom filter it is good practice to send 0 (zero) instead of time_high, this
        will ensure that messages newer than time_high are also retrieved.

        Bloom filters at index 0 indicates the most recent bloom filter range, while a higher number
        indicates an older range.

        It sounds reasonable to ensure that the more recent ranges are returned more frequently.
        Several strategied can be used:

         1. Always return index 0 and pick another index at random.

         2. Always return index 0 and pick another index using a gaussian probability distribution
            favoring the more recent ranges.

         3. Use a gaussion probability distribution favoring the more recent ranges.

        The default is option 3.  However, each community is free to implement this how they see
        fit.

        @note: The returned indexes need to exist.
        @rtype [(time_low, time_high, bloom_filter)]
        """
        size = len(self._bloom_filters)
        index = int(abs(gauss(0, sqrt(size))))
        while index >= size:
            index = int(abs(gauss(0, sqrt(size))))

        if index == 0:
            time_low, _, bloom_filter = self._bloom_filters[index]
            return [(time_low, 0, bloom_filter)]

        else:
            return [self._bloom_filters[index]]

    @property
    def dispersy_sync_member_count(self):
        """
        The number of members that are selected each time a dispersy-sync message is send.
        @rtype: int
        """
        return 10

    @property
    def dispersy_sync_response_limit(self):
        """
        The maximum number of bytes to send back per received dispersy-sync message.
        @rtype: int
        """
        return 5 * 1025

    @property
    def dispersy_missing_sequence_response_limit(self):
        """
        The maximum number of bytes to send back per received dispersy-missing-sequence message.
        @rtype: (int, int)
        """
        return 10 * 1025

    @property
    def cid(self):
        """
        The 20 byte sha1 digest of the public master key, in other words: the community identifier.
        @rtype: string
        """
        return self._cid

    @property
    def database_id(self):
        """
        The number used to identify this community in the local Dispersy database.
        @rtype: int or long
        """
        return self._database_id

    @property
    def master_member(self):
        """
        The community MasterMember instance.
        @rtype: MasterMember
        """
        return self._master_member

    @property
    def my_member(self):
        """
        Our own MyMember instance that is used to sign the messages that we create.
        @rtype: MyMember
        """
        return self._my_member

    @property
    def dispersy(self):
        """
        The Dispersy instance.
        @rtype: Dispersy
        """
        return self._dispersy

    def get_bloom_filter(self, global_time):
        """
        Returns the bloom filter associated to global-time.

        @param global_time: The global time indicating the time range.
        @type global_time: int or long

        @return: The bloom filter where messages in global_time are stored.
        @rtype: BloomFilter

        @todo: this name should be more distinct... this bloom filter is specifically used by the
         SyncDistribution policy.
        """
        # iter existing bloom filters
        for time_low, time_high, bloom_filter in self._bloom_filters:
            if time_low <= global_time <= time_high:
                return bloom_filter

        # create as many filter as needed to reach global_time
        for time_low in xrange(time_low + self._bloom_filter_step, global_time, self._bloom_filter_step):
            time_high = time_low + self._bloom_filter_step
            bloom_filter = BloomFilter(*self._bloom_filter_size)
            self._bloom_filters.insert(0, (time_low, time_high, bloom_filter))
            if time_low <= global_time <= time_high:
                return bloom_filter

    @property
    def bloom_filter_count(self):
        return len(self._bloom_filters)

    def get_current_bloom_filter(self, index=0):
        """
        Returns the global time and bloom filter associated to the current time frame.

        @param index: The index of the returned filter.  Where 0 is the most recent, 1 the second
         last, etc.
        @rtype int or long

        @return: The time-low, time-high and bloom filter associated to the current time frame.
        @rtype: (number, number, BloomFilter) tuple

        @raise IndexError: When index does not exist.  Index 0 will always exist.

        @todo: this name should be more distinct... this bloom filter is specifically used by the
         SyncDistribution policy.
        """
        return self._bloom_filters[index]

    def get_subjective_set(self, member, cluster):
        """
        Returns the subjective set for a certain member and cluster.

        @param member: The member for who we want the subjective set.
        @type member: Member

        @param cluster: The cluster identifier.  Where 0 < cluster < 255.
        @type cluster: int

        @return: The bloom filter associated to the member and cluster or None
        @rtype: BloomFilter or None

        @raise KeyError: When the subjective set is not known.
        """
        assert isinstance(member, Member)
        assert isinstance(cluster, int)
        assert 0 < cluster < 2^8, "CLUSTER must fit in one byte"
        # assert cluster in self._subjective_sets
        subjective_set = self.get_subjective_sets(member)
        return subjective_set[cluster]
        # if not member in self._subjective_sets:
        #     self._subjective_sets[member] = self.get_subjective_sets(member)
        # return self._subjective_sets[cluster]

    def get_subjective_sets(self, member):
        """
        Returns all subjective sets for a certain member.

        We can return an empty dictionary when no sets are available for this member.

        @param member: The member for who we want the subjective set.
        @type member: Member

        @return: A dictionary with all cluster / bloom filter pairs
        @rtype: {cluster:bloom-filter}
        """
        assert isinstance(member, Member)

        # retrieve all the subjective sets that were created by member
        meta_message = self.get_meta_message(u"dispersy-subjective-set")
        existing_sets = {}
        sql = u"""SELECT sync.packet
                  FROM sync
                  JOIN reference_user_sync ON (reference_user_sync.sync = sync.id)
                  WHERE sync.community = ? AND reference_user_sync.user = ? AND sync.name = ?"""

        # dprint(sql)
        # dprint((self._database_id, member.database_id, meta_message.database_id))

        for packet, in self._dispersy_database.execute(sql, (self._database_id, member.database_id, meta_message.database_id)):
            assert isinstance(packet, buffer)
            packet = str(packet)
            conversion = self.get_conversion(packet[:22])
            message = conversion.decode_message(packet)
            assert message.name == "dispersy-subjective-set"
            assert not message.payload.cluster in existing_sets
            existing_sets[message.payload.cluster] = message.payload.subjective_set

        # # either use an existing or create a new bloom filter for each subjective set (cluster)
        # # that we are using
        # subjective_sets = {}
        # for meta_message in self._meta_messages.iter_values():
        #     if isinstance(meta_message.destination, SubjectiveDestination):
        #         cluster = meta_message.destination.cluster
        #         if not cluster in subjective_sets:
        #             if cluster in existing_sets:
        #                 subjective_sets[cluster] = existing_sets[cluster]
        #             elif create_new:
        #                 subjective_sets[cluster] = BloomFilter(500, 0.1)

        # # 3. return the sets.  this will be stored in self._subjective_sets for later reference.
        # return subjective_sets

        return existing_sets

    def get_member(self, public_key):
        """
        Returns a Member instance associated with public_key.

        since we have the public_key, we can create this user when it didn't already exist.  Hence,
        this method always succeeds.

        @param public_key: The public key of the member we want to obtain.
        @type public_key: string

        @return: The Member instance associated with public_key.
        @rtype: Member

        @note: This returns -any- Member, it may not be a member that is part of this community.

        @todo: Since this method returns Members that are not specifically bound to any community,
         this method should be moved to Dispersy
        """
        assert isinstance(public_key, str)
        return Member.get_instance(public_key)

    def get_members_from_id(self, mid):
        """
        Returns zero or more Member instances associated with mid, where mid is the sha1 digest of a
        member public key.

        As we are using only 20 bytes to represent the actual member public key, this method may
        return multiple possible Member instances.  In this case, other ways must be used to figure
        out the correct Member instance.  For instance: if a signature or encryption is available,
        all Member instances could be used, but only one can succeed in verifying or decrypting.

        Since we may not have the public key associated to MID, this method may return an empty
        list.  In such a case it is sometimes possible to DelayPacketByMissingMember to obtain the
        public key.

        @param mid: The 20 byte sha1 digest indicating a member.
        @type mid: string

        @return: A list containing zero or more Member instances.
        @rtype: [Member]

        @note: This returns -any- Member, it may not be a member that is part of this community.

        @todo: Since this method returns Members that are not specifically bound to any community,
         this method should be moved to Dispersy
        """
        assert isinstance(mid, str)
        assert len(mid) == 20
        return [Member.get_instance(str(public_key)) for public_key, in self._dispersy_database.execute(u"SELECT public_key FROM user WHERE mid = ?", (buffer(mid),))]

    def get_conversion(self, prefix=None):
        """
        returns the conversion associated with prefix.

        prefix is an optional 22 byte sting.  Where the first 20 bytes are the community id and the
        last 2 bytes are the conversion version.

        When no prefix is given, i.e. prefix is None, then the default Conversion is returned.
        Conversions are assigned to a community using add_conversion().

        @param prefix: Optional prefix indicating a conversion.
        @type prefix: string

        @return A Conversion instance indicated by prefix or the default one.
        @rtype: Conversion
        """
        assert prefix is None or isinstance(prefix, str)
        assert prefix is None or len(prefix) == 22
        return self._conversions[prefix]

    def add_conversion(self, conversion, default=False):
        """
        Add a Conversion to the Community.

        A conversion instance converts between the internal Message structure and the on-the-wire
        message.

        When default is True the conversion is set to be the default conversion.  The default
        conversion is used (by default) when a message is implemented and no prefix is given.

        @param conversion: The new conversion instance.
        @type conversion: Conversion

        @param default: Indicating if this is to become the default conversion.
        @type default: bool
        """
        if __debug__:
            from conversion import Conversion
        assert isinstance(conversion, Conversion)
        assert isinstance(default, bool)
        assert not conversion.prefix in self._conversions
        if default:
            self._conversions[None] = conversion
        self._conversions[conversion.prefix] = conversion

    @documentation(Dispersy.create_authorize)
    def create_dispersy_authorize(self, permission_triplets, sign_with_master=False, update_locally=True, store_and_forward=True):
        return self._dispersy.create_authorize(self, permission_triplets, sign_with_master, update_locally, store_and_forward)

    @documentation(Dispersy.create_identity)
    def create_identity(self, store_and_forward=True):
        return self._dispersy.create_identity(self, store_and_forward)

    @documentation(Dispersy.create_signature_request)
    def create_signature_request(self, message, response_func, response_args=(), timeout=10.0, store_and_forward=True):
        return self._dispersy.create_signature_request(self, message, response_func, response_args, timeout, store_and_forward)

    @documentation(Dispersy.create_similarity)
    def create_similarity(self, message, keywords, update_locally=True, store_and_forward=True):
        return self._dispersy.create_similarity(self, message, keywords, update_locally, store_and_forward)

    @documentation(Dispersy.create_destroy_community)
    def create_dispersy_destroy_community(self, degree):
        return self._dispersy.create_destroy_community(self, degree)

    @documentation(Dispersy.create_subjective_set)
    def create_dispersy_subjective_set(self, cluster, members, reset=True, update_locally=True, store_and_forward=True):
        return self._dispersy.create_subjective_set(self, cluster, members, reset, update_locally, store_and_forward)

    def on_message(self, address, message):
        """
        Process a permit (regular) message.

        This method is called to process an unknown permit message.  This message is either received
        from an external source or locally generated.

        When the message is locally generated the address will be set to ('', -1).

        This is an abstract method that must be implemented in community specific code.

        @param address: The address from where we received this message.
        @type address: (string, int)

        @param message: The received message.
        @type message: Message.Implementation
        @raise DropMessage: When unable to verify that this message is valid.
        @todo: We should raise a DelayMessageByProof to ensure that we request the proof for this
         message immediately.
        """
        if __debug__:
            from message import Message
        assert isinstance(address, (type(None), tuple))
        assert isinstance(message, Message.Implementation)
        raise NotImplementedError()

    def on_dispersy_destroy_community(self, address, message):
        """
        A dispersy-destroy-community message is received.

        Depending on the degree of the destroy message, we will need to cleanup in different ways.

         - soft-kill: The community is frozen.  Dispersy will retain the data it has obtained.
           However, no messages beyond the global-time of the dispersy-destroy-community message
           will be accepted.  Responses to dispersy-sync messages will be send like normal.

         - hard-kill: The community is destroyed.  Dispersy will throw away everything except the
           dispersy-destroy-community message and the authorize chain that is required to verify
           this message.  The community should also remove all its data and cleanup as much as
           possible.

        Similar to other on_... methods, this method may raise a DropMessage exception.  In this
        case the message will be ignored and no data is removed.  However, each dispersy-sync that
        is sent is likely to result in the same dispersy-destroy-community message to be received.

        @param address: The address from where we received this message.
        @type address: (string, int)

        @param message: The received message.
        @type message: Message.Implementation

        @raise DropMessage: When unable to verify that this message is valid.
        """
        # override to implement community cleanup
        pass

    def get_meta_message(self, name):
        """
        Returns the meta message by its name.

        @param name: The name of the message.
        @type name: unicode

        @return: The meta message.
        @rtype: Message

        @raise KeyError: When there is no meta message by that name.
        """
        assert isinstance(name, unicode)
        return self._meta_messages[name]

    def get_meta_messages(self):
        """
        Returns all meta messages.

        @return: The meta messages.
        @rtype: [Message]
        """
        return self._meta_messages.values()

    def initiate_meta_messages(self):
        """
        Create the meta messages for one community instance.

        This method is called once for each community when it is created.  The resulting meta
        messages can be obtained by either get_meta_message(name) or get_meta_messages().

        To distinct the meta messages that the community provides from those that Dispersy provides,
        none of the messages may have a name that starts with 'dispersy-'.

        @return: The new meta messages.
        @rtype: [Message]
        """
        raise NotImplementedError()