from conversion import BarterCommunityConversion
from database import BarterDatabase
from payload import BarterRecordPayload

from Tribler.Core.dispersy.community import Community
from Tribler.Core.dispersy.message import Message, DropMessage
from Tribler.Core.dispersy.authentication import MultiMemberAuthentication
from Tribler.Core.dispersy.resolution import PublicResolution
from Tribler.Core.dispersy.distribution import LastSyncDistribution
from Tribler.Core.dispersy.destination import CommunityDestination

if __debug__:
    from Tribler.Core.dispersy.dprint import dprint
    from lencoder import log

class BarterCommunity(Community):
    """
    Community to that stored barter records (person A uploaded so and so much data to person B)
    distributely.  Using these barter records we can order members based on how much they
    contributed and consumed from the community.
    """

    def __init__(self, cid):
        super(BarterCommunity, self).__init__(cid)

        self._database = BarterDatabase.get_instance()

        # mapping
        self._incoming_message_map = {u"barter-record":self.on_barter_record}

        # add the Dispersy message handlers to the _incoming_message_map
        for message, handler in self._dispersy.get_message_handlers(self):
            assert message.name not in self._incoming_message_map
            self._incoming_message_map[message.name] = handler

        # available conversions
        self.add_conversion(BarterCommunityConversion(self), True)

    def initiate_meta_messages(self):
        return [Message(self, u"barter-record", MultiMemberAuthentication(count=2, allow_signature_func=self.on_signature_request), PublicResolution(), LastSyncDistribution(enable_sequence_number=False, synchronization_direction=u"out-order", history_size=10), CommunityDestination(node_count=10), BarterRecordPayload())]

    def create_barter_record(self, second_member, first_upload, second_upload, store_and_forward=True):
        """
        Create and return a signature request for a new barter record.

        A barter-record message is created, this message is owned by self._my_member.  A
        dispersy-signature-request message is then created to encapsulate the barter-record, send to
        OTHER_MEMBER, and returned.

        OTHER_MEMBER: the second person who will be asked to sign the barter-record message.

        MY_UPLOAD: the number of MB uploaded by self._my_member.

        OTHER_UPLOAD: the number of MB uploaded by OTHER_MEMBER.

        STORE_AND_FORWARD: when True, dispersy-signature-request is send to OTHER_MEMBER.
        """
        if __debug__:
            from Tribler.Core.dispersy.member import Public, Private
        assert isinstance(second_member, Public)
        assert not isinstance(second_member, Private)
        assert isinstance(first_upload, (int, long))
        assert isinstance(second_upload, (int, long))
        assert isinstance(store_and_forward, bool)

        meta = self.get_meta_message(u"barter-record")
        message = meta.implement(meta.authentication.implement((self._my_member, second_member)),
                                 meta.distribution.implement(self._timeline.claim_global_time()),
                                 meta.destination.implement(),
                                 meta.payload.implement(first_upload, second_upload))
        if __debug__: log("barter.log", "created", second_member=second_member.mid, footprint=message.footprint, message=message.name)
        return self.create_signature_request(message, self.on_signature_response, store_and_forward=store_and_forward)

    def on_signature_request(self, message):
        """ Decide whether to reply or not to a signature request

        Currently I always sign for testing proposes
        """
        assert message.name == u"barter-record"
        assert not message.authentication.is_signed
        if __debug__: dprint(message)

        is_signed, other_member = message.authentication.signed_members[0]
        if other_member == self._my_member:
            raise DropMessage("We should be the first signer")

        if not is_signed:
            raise DropMessage("The other member did not sign it")

        my_member = message.authentication.members[1]
        if not my_member == self._my_member:
            raise DropMessage("We should be the second signer")

        # todo: decide if we want to use add our signature to this # record
        if True:
            # recalculate the limits of what we want to upload to member.authentication.members[0]
            return True

        # we will not add our signature
        return False

    def on_signature_response(self, address, message):
        """ Handle a newly created double signed message or a timeout while signing

        When request for signing times out I just return. When I receive the signature for the
        message that I created then I send it to myself and then store and forward it to others of
        the community
        """
        if __debug__: dprint(message)

        if message:
            assert message.name == u"barter-record"
            assert message.authentication.is_signed

            if __debug__: dprint(message)

            # send it to self
            self.on_barter_record(('', -1), message)

            # we need to decide if we want to spread this record
            if True:
                # send to everybody in this community
                self._dispersy.store_and_forward([message])

        else:
            # signature timeout
            # close the transfer
            if __debug__: dprint("Signature request timeout")

    def on_barter_record(self, address, message):
        """ I handle received barter records

        I create or update a row in my database
        """
        if __debug__: dprint(message)
        with self._database as execute:
            # check if there is already a record about this pair
            try:
                first_member, second_member, global_time = \
                              execute(u"SELECT first_member, second_member, global_time FROM \
                              record WHERE (first_member = ? AND second_member = ?) OR \
                              (first_member = ? AND second_member = ?)",
                                      (message.authentication.members[0].database_id,
                                       message.authentication.members[1].database_id,
                                       message.authentication.members[1].database_id,
                                       message.authentication.members[0].database_id)).next()
            except StopIteration:
                global_time = -1
                first_member = message.authentication.members[0].database_id
                second_member = message.authentication.members[1].database_id

            if global_time >= message.distribution.global_time:
                # ignore the message
                if __debug__:
                    dprint("Ignoring older message")
            else:
                self._database.execute(u"INSERT OR REPLACE INTO \
                record(community, global_time, first_member, second_member, \
                upload_first_member, upload_second_member) \
                VALUES(?, ?, ?, ?, ?, ?)",
                                       (self._database_id,
                                        message.distribution.global_time,
                                        first_member,
                                        second_member,
                                        message.payload.first_upload,
                                        message.payload.second_upload))

    def on_message(self, address, message):
        """ Decide which function to feed the message to.
        """
        if self._timeline.check(message):
            self._incoming_message_map[message.name](address, message)
        else:
            raise DropMessage("TODO: implement delay by proof")