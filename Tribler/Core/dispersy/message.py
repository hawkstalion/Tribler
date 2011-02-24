from meta import MetaObject

#
# Exceptions
#
class DelayPacket(Exception):
    """
    Raised by Conversion.decode_message when the packet can not be
    converted into a Message yet.  Delaying for 'some time' or until
    'some event' occurs.
    """
    def __init__(self, msg, pattern, request_packet):
        if __debug__:
            import re
        assert isinstance(msg, str)
        assert isinstance(pattern, str)
        assert re.compile(pattern)
        assert isinstance(request_packet, str)
        super(DelayPacket, self).__init__(msg)
        self._pattern = pattern
        self._request_packet = request_packet

    @property
    def pattern(self):
        return self._pattern

    @property
    def request_packet(self):
        return self._request_packet

class DelayPacketByMissingMember(DelayPacket):
    """
    Raised during Conversion.decode_message when an unknown member id
    was received.  A member id is the sha1 hash over the member's
    public key, hence there is a small chance that members with
    different public keys will have the same member id.

    Raising this exception should result in a request for all public
    keys associated to the missing member id.
    """
    def __init__(self, community, missing_member_id):
        if __debug__:
            from community import Community
        assert isinstance(community, Community)
        assert isinstance(missing_member_id, str)
        assert len(missing_member_id) == 20
        # the footprint that will trigger the delayed packet
        footprint = community.get_meta_message(u"dispersy-identity").generate_footprint(authentication=([missing_member_id],))

        # the request message that asks for the message that will
        # trigger the delayed packet
        meta = community.get_meta_message(u"dispersy-identity-request")
        message = meta.implement(meta.authentication.implement(),
                                 meta.distribution.implement(community._timeline.global_time),
                                 meta.destination.implement(),
                                 meta.payload.implement(missing_member_id))

        super(DelayPacketByMissingMember, self).__init__("Missing member", footprint, message.packet)

class DelayPacketBySimilarity(DelayPacket):
    """
    Raised during Conversion.decode_message when no similarity is
    known for the message owner.

    Delaying until a dispersy-similarity-message is received that
    contains the missing similarity bitstream
    """
    def __init__(self, community, member, destination):
        if __debug__:
            from community import Community
            from member import Member
            from destination import SimilarityDestination
        assert isinstance(community, Community)
        assert isinstance(member, Member)
        assert isinstance(destination, SimilarityDestination)
        # the footprint that will trigger the delayed packet
        meta = community.get_meta_message(u"dispersy-identity")
        footprint = meta.generate_footprint()
        # footprint = "dispersy-identity Community:{0.cid} MemberAuthentication:{1.mid} LastSyncDistribution SimilarityDestination{2.cluster}".format(community, member, destination)

        # the request message that asks for the message that will
        # trigger the delayed packet
        meta = community.get_meta_message(u"dispersy-identity-request")
        message = meta.implement(meta.authentication.implement(),
                                 meta.distribution.implement(community._timeline.global_time),
                                 meta.destination.implement(),
                                 meta.payload.implement(member.mid))

        super(DelayPacketBySimilarity, self).__init__("Missing similarity", footprint, message.packet)

class DropPacket(Exception):
    """
    Raised by Conversion.decode_message when the packet is invalid.
    I.e. does not conform to valid syntax, contains malicious
    behaviour, etc.
    """
    pass

class DelayMessage(Exception):
    """
    Raised during Community.on_incoming_message or
    Community.on_incoming_message; delaying for 'some time' or until
    'some event' occurs.
    """
    def __init__(self, msg, pattern, request_packet):
        if __debug__:
            import re
        assert isinstance(msg, str)
        assert isinstance(pattern, str)
        assert re.compile(pattern)
        assert isinstance(request_packet, str)
        super(DelayMessage, self).__init__(msg)
        self._pattern = pattern
        self._request_packet = request_packet

    @property
    def pattern(self):
        return self._pattern

    @property
    def request_packet(self):
        return self._request_packet

class DelayMessageBySequence(DelayMessage):
    """
    Raised during Community.on_incoming_message or
    Community.on_incoming_message.

    Delaying until all missing sequence numbers have been received.
    """
    def __init__(self, message, missing_low, missing_high):
        if __debug__:
            from message import Message
        assert isinstance(message, Message.Implementation)
        assert isinstance(missing_low, (int, long))
        assert isinstance(missing_high, (int, long))
        assert 0 < missing_low <= missing_high
        # the footprint that will trigger the delayed packet
        footprint = "".join((message.name.encode("UTF-8"),
                             " Community:", message.community.cid.encode("HEX"),
                             " MemberAuthentication:", message.authentication.member.mid.encode("HEX"),
                             " SyncDistribution:", str(missing_high),
                             " CommunityDestination"))

        # the request message that asks for the message that will
        # trigger the delayed packet
        meta = message.community.get_meta_message(u"dispersy-missing-sequence")
        message = meta.implement(meta.authentication.implement(),
                                 meta.distribution.implement(message.community._timeline.global_time),
                                 meta.destination.implement(),
                                 meta.payload.implement(message.authentication.member, message.meta, missing_low, missing_high))

        super(DelayMessageBySequence, self).__init__("Missing sequence numbers", footprint, message.packet)

class DelayMessageBySubjectiveSet(DelayMessage):
    """
    Raised when a message is received and a dispersy-subjective-set message is required to process
    it.

    Delaying until a dispersy-subjective-set message is received that contains the missing data or
    until a timeout occurs.
    """
    def __init__(self, message, cluster):
        if __debug__:
            from message import Message
        assert isinstance(message, Message.Implementation)
        assert isinstance(cluster, int)
        # the footprint that will trigger the delayed packet
        meta = message.community.get_meta_message(u"dispersy-subjective-set")
        footprint = meta.generate_footprint(authentication=([message.authentication.member.mid],))

        # the request message that asks for the message that will trigger the delayed packet
        meta = message.community.get_meta_message(u"dispersy-subjective-set-request")
        message = meta.implement(meta.authentication.implement(),
                                 meta.distribution.implement(message.community._timeline.global_time),
                                 meta.destination.implement(),
                                 meta.payload.implement(cluster, [message.authentication.member]))

        super(DelayMessageBySubjectiveSet, self).__init__("Missing subjective set", footprint, message.packet)

class DelayMessageBySimilarity(DelayMessage):
    """
    Raised during Community.on_message when no similarity is known for
    the message owner.

    Delaying until a dispersy-similarity-message is received that
    contains the missing similarity bitstream
    """
    def __init__(self, message, cluster):
        if __debug__:
            from message import Message
        assert isinstance(message, Message.Implementation)
        assert isinstance(cluster, int)
        # the footprint that will trigger the delayed packet
        meta = message.community.get_meta_message(u"dispersy-similarity")
        footprint = meta.generate_footprint(authentication=([message.authentication.member.mid],))

        # the request message that asks for the message that will
        # trigger the delayed packet
        meta = message.community.get_meta_message(u"dispersy-similarity-request")
        message = meta.implement(meta.authentication.implement(),
                                 meta.distribution.implement(message.community._timeline.global_time),
                                 meta.destination.implement(),
                                 meta.payload.implement(cluster, [message.authentication.member]))

        super(DelayMessageBySimilarity, self).__init__("Missing similarity", footprint, message.packet)

class DropMessage(Exception):
    """
    Raised during Community.on_message.

    Drops a message because it violates 'something'.  More specific
    reasons can be given with by raising a spectific subclass.
    """
    pass

class DropMessageByProof(DropMessage):
    """
    Raised during Community.on_message.

    Drops a message because it violates a previously received message.
    This message should be provided to the origionator of this message
    to allow them to correct their mistake.
    """
    def __init__(self, message):
        DropMessage.__init__(self, "Provide proof")
        self._proof = message

    @property
    def proof(self):
        return self._proof

#
# packet
#

class Packet(MetaObject.Implementation):
    def __init__(self, meta, packet):
        assert isinstance(packet, str)
        super(Packet, self).__init__(meta)
        self._packet = packet
        self._packet_id = 0

    @property
    def community(self):
        return self._meta._community

    @property
    def name(self):
        return self._meta._name

    @property
    def database_id(self):
        return self._meta._database_id

    @property
    def resolution(self):
        return self._meta._resolution

    @property
    def check_callback(self):
        return self._meta._check_callback

    @property
    def handle_callback(self):
        return self._meta._handle_callback

    @property
    def packet(self):
        return self._packet

    @property
    def packet_id(self):
        return self._packet_id

    @packet_id.setter
    def packet_id(self, packet_id):
        assert isinstance(packet_id, (int, long))
        self._packet_id = packet_id

    def load_message(self):
        return self._meta.community.get_conversion(self._packet[:22]).decode_message(self._packet)

    def __str__(self):
        return "<{0.meta.__class__.__name__}.{0.__class__.__name__} {0.name} {1}>".format(self, len(self._packet))

#
# message
#
class Message(MetaObject):
    class Implementation(Packet):
        def __init__(self, meta, authentication, distribution, destination, payload, conversion=None, packet=""):
            if __debug__:
                from payload import Payload
                from conversion import Conversion
            assert isinstance(meta, Message), "META has invalid type '{0}'".format(type(meta))
            assert isinstance(authentication, meta._authentication.Implementation), "AUTHENTICATION has invalid type '{0}'".format(type(authentication))
            assert isinstance(distribution, meta._distribution.Implementation), "DISTRIBUTION has invalid type '{0}'".format(type(distribution))
            assert isinstance(destination, meta._destination.Implementation), "DESTINATION has invalid type '{0}'".format(type(destination))
            assert isinstance(payload, meta._payload.Implementation), "PAYLOAD has invalid type '{0}'".format(type(payload))
            assert conversion is None or isinstance(conversion, Conversion), "CONVERSION has invalid type '{0}'".format(type(conversion))
            assert isinstance(packet, str)
            super(Message.Implementation, self).__init__(meta, packet)
            self._authentication = authentication
            self._distribution = distribution
            self._destination = destination
            self._payload = payload
            self._footprint = "".join((meta._name.encode("UTF-8"), " Community:", meta._community.cid.encode("HEX"), " ", authentication.footprint, " ", distribution.footprint, " ", destination.footprint, " ", payload.footprint))

            # allow setup parts.  used to setup callback when something changes that requires the
            # self._packet to be generated again
            self._authentication.setup(self)
            # self._resolution.setup(self)
            # self._distribution.setup(self)
            # self._destination.setup(self)
            # self._payload.setup(self)

            if conversion:
                self._conversion = conversion
            elif packet:
                self._conversion = meta._community.get_conversion(packet[:22])
            else:
                self._conversion = meta._community.get_conversion()

            if packet:
                self._packet = packet
            else:
                self._packet = self._conversion.encode_message(self)

        @property
        def conversion(self):
            return self._conversion

        @property
        def authentication(self):
            return self._authentication

        @property
        def distribution(self):
            return self._distribution

        @property
        def destination(self):
            return self._destination

        @property
        def payload(self):
            return self._payload

        @property
        def footprint(self):
            return self._footprint

        @property
        def packet(self):
            return self._packet

        def load_message(self):
            return self

        def regenerate_packet(self, packet=""):
            if packet:
                self._packet = packet
            else:
                self._packet = self._conversion.encode_message(self)

        def __str__(self):
            return "<{0.meta.__class__.__name__}.{0.__class__.__name__} {0.name} {1}>".format(self, len(self._packet))

    def __init__(self, community, name, authentication, resolution, distribution, destination, payload, check_callback, handle_callback):
        if __debug__:
            from community import Community
            from authentication import Authentication
            from resolution import Resolution
            from destination import Destination
            from distribution import Distribution
            from payload import Payload
        assert isinstance(community, Community), "COMMUNITY has invalid type '{0}'".format(type(community))
        assert isinstance(name, unicode), "NAME has invalid type '{0}'".format(type(name))
        assert isinstance(authentication, Authentication), "AUTHENTICATION has invalid type '{0}'".format(type(authentication))
        assert isinstance(resolution, Resolution), "RESOLUTION has invalid type '{0}'".format(type(resolution))
        assert isinstance(distribution, Distribution), "DISTRIBUTION has invalid type '{0}'".format(type(distribution))
        assert isinstance(destination, Destination), "DESTINATION has invalid type '{0}'".format(type(destination))
        assert isinstance(payload, Payload), "PAYLOAD has invalid type '{0}'".format(type(payload))
        assert hasattr(check_callback, "__call__")
        assert hasattr(handle_callback, "__call__")
        assert self.check_policy_combination(authentication, resolution, distribution, destination)
        self._community = community
        self._name = name
        self._authentication = authentication
        self._resolution = resolution
        self._distribution = distribution
        self._destination = destination
        self._payload = payload
        self._check_callback = check_callback
        self._handle_callback = handle_callback

        # setup
        database = community.dispersy.database

        # ensure that there is a database id associated to this
        # meta message name
        try:
            self._database_id, = database.execute(u"SELECT id FROM name WHERE value = ?", (name,)).next()
        except StopIteration:
            database.execute(u"INSERT INTO name (value) VALUES (?)", (name,))
            self._database_id = database.last_insert_rowid

        # allow optional setup methods to initialize the specific
        # parts of the meta message
        self._authentication.setup(self)
        self._resolution.setup(self)
        self._distribution.setup(self)
        self._destination.setup(self)
        self._payload.setup(self)

    @property
    def community(self):
        return self._community

    @property
    def name(self):
        return self._name

    @property
    def database_id(self):
        return self._database_id

    @property
    def authentication(self):
        return self._authentication

    @property
    def resolution(self):
        return self._resolution

    @property
    def distribution(self):
        return self._distribution

    @property
    def destination(self):
        return self._destination

    @property
    def payload(self):
        return self._payload

    @property
    def check_callback(self):
        return self._check_callback

    @property
    def handle_callback(self):
        return self._handle_callback

    def generate_footprint(self, authentication=(), distribution=(), destination=(), payload=()):
        assert isinstance(authentication, tuple)
        assert isinstance(distribution, tuple)
        assert isinstance(destination, tuple)
        assert isinstance(payload, tuple)
        return "".join((self._name.encode("UTF-8"),
                        " Community:", self._community.cid.encode("HEX"),
                        " ", self._authentication.generate_footprint(*authentication),
                        " ", self._distribution.generate_footprint(*distribution),
                        " ", self._destination.generate_footprint(*destination),
                        " ", self._payload.generate_footprint(*payload)))

    def __str__(self):
        return "<{0.__class__.__name__} {0.name}>".format(self)

    @staticmethod
    def check_policy_combination(authentication, resolution, distribution, destination):
        from authentication import Authentication, NoAuthentication, MemberAuthentication, MultiMemberAuthentication
        from resolution import Resolution, PublicResolution, LinearResolution
        from distribution import Distribution, RelayDistribution, DirectDistribution, FullSyncDistribution, LastSyncDistribution
        from destination import Destination, AddressDestination, MemberDestination, CommunityDestination, SubjectiveDestination, SimilarityDestination

        assert isinstance(authentication, Authentication)
        assert isinstance(resolution, Resolution)
        assert isinstance(distribution, Distribution)
        assert isinstance(destination, Destination)

        def require(a, b, c):
            if not isinstance(b, c):
                raise ValueError("{0.__class__.__name__} does not support {1.__class__.__name__}.  Allowed options are: {2}".format(a, b, ", ".join([x.__name__ for x in c])))

        if isinstance(authentication, NoAuthentication):
            require(authentication, resolution, PublicResolution)
            require(authentication, distribution, (RelayDistribution, DirectDistribution))
            require(authentication, destination, (AddressDestination, MemberDestination, CommunityDestination))
        elif isinstance(authentication, MemberAuthentication):
            require(authentication, resolution, (PublicResolution, LinearResolution))
            require(authentication, distribution, (RelayDistribution, DirectDistribution, FullSyncDistribution, LastSyncDistribution))
            require(authentication, destination, (AddressDestination, MemberDestination, CommunityDestination, SubjectiveDestination, SimilarityDestination))
        elif isinstance(authentication, MultiMemberAuthentication):
            require(authentication, resolution, (PublicResolution, LinearResolution))
            require(authentication, distribution, (RelayDistribution, DirectDistribution, FullSyncDistribution, LastSyncDistribution))
            require(authentication, destination, (AddressDestination, MemberDestination, CommunityDestination, SubjectiveDestination, SimilarityDestination))
        else:
            raise ValueError("{0.__class__.__name__} is not supported".format(authentication))

        if isinstance(resolution, PublicResolution):
            require(resolution, authentication, (NoAuthentication, MemberAuthentication, MultiMemberAuthentication))
            require(resolution, distribution, (RelayDistribution, DirectDistribution, FullSyncDistribution, LastSyncDistribution))
            require(resolution, destination, (AddressDestination, MemberDestination, CommunityDestination, SubjectiveDestination, SimilarityDestination))
        elif isinstance(resolution, LinearResolution):
            require(resolution, authentication, (MemberAuthentication, MultiMemberAuthentication))
            require(resolution, distribution, (RelayDistribution, DirectDistribution, FullSyncDistribution, LastSyncDistribution))
            require(resolution, destination, (AddressDestination, MemberDestination, CommunityDestination, SubjectiveDestination, SimilarityDestination))
        else:
            raise ValueError("{0.__class__.__name__} is not supported".format(resolution))

        if isinstance(distribution, RelayDistribution):
            require(distribution, authentication, (NoAuthentication, MemberAuthentication, MultiMemberAuthentication))
            require(distribution, resolution, (PublicResolution, LinearResolution))
            require(distribution, destination, (AddressDestination, MemberDestination))
        elif isinstance(distribution, DirectDistribution):
            require(distribution, authentication, (NoAuthentication, MemberAuthentication, MultiMemberAuthentication))
            require(distribution, resolution, (PublicResolution, LinearResolution))
            require(distribution, destination, (AddressDestination, MemberDestination, CommunityDestination))
        elif isinstance(distribution, FullSyncDistribution):
            require(distribution, authentication, (MemberAuthentication, MultiMemberAuthentication))
            require(distribution, resolution, (PublicResolution, LinearResolution))
            require(distribution, destination, (CommunityDestination, SubjectiveDestination, SimilarityDestination))
            if isinstance(authentication, MultiMemberAuthentication) and distribution.enable_sequence_number:
                raise ValueError("{0.__class__.__name__} may not be used with {1.__class__.__name__} when sequence numbers are enabled".format(distribution, authentication))
        elif isinstance(distribution, LastSyncDistribution):
            require(distribution, authentication, (MemberAuthentication, MultiMemberAuthentication))
            require(distribution, resolution, (PublicResolution, LinearResolution))
            require(distribution, destination, (CommunityDestination, SubjectiveDestination, SimilarityDestination))
            if isinstance(authentication, MultiMemberAuthentication) and distribution.enable_sequence_number:
                raise ValueError("{0.__class__.__name__} may not be used with {1.__class__.__name__} when sequence numbers are enabled".format(distribution, authentication))
        else:
            raise ValueError("{0.__class__.__name__} is not supported".format(distribution))

        if isinstance(destination, AddressDestination):
            require(destination, authentication, (NoAuthentication, MemberAuthentication, MultiMemberAuthentication))
            require(destination, resolution, (PublicResolution, LinearResolution))
            require(destination, distribution, (RelayDistribution, DirectDistribution))
        elif isinstance(destination, MemberDestination):
            require(destination, authentication, (NoAuthentication, MemberAuthentication, MultiMemberAuthentication))
            require(destination, resolution, (PublicResolution, LinearResolution))
            require(destination, distribution, (RelayDistribution, DirectDistribution))
        elif isinstance(destination, CommunityDestination):
            require(destination, authentication, (NoAuthentication, MemberAuthentication, MultiMemberAuthentication))
            require(destination, resolution, (PublicResolution, LinearResolution))
            require(destination, distribution, (DirectDistribution, FullSyncDistribution, LastSyncDistribution))
        elif isinstance(destination, SubjectiveDestination):
            require(destination, authentication, (MemberAuthentication, MultiMemberAuthentication))
            require(destination, resolution, (PublicResolution, LinearResolution))
            require(destination, distribution, (FullSyncDistribution, LastSyncDistribution))
        elif isinstance(destination, SimilarityDestination):
            require(destination, authentication, (MemberAuthentication, MultiMemberAuthentication))
            require(destination, resolution, (PublicResolution, LinearResolution))
            require(destination, distribution, (FullSyncDistribution, LastSyncDistribution))
        else:
            raise ValueError("{0.__class__.__name__} is not supported".format(destination))

        return True
