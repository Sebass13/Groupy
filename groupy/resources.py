import time
from datetime import datetime
from collections import namedtuple

from . import exceptions
from . import managers


class Resource:
    def __init__(self, manager, **data):
        self.manager = manager
        self.data = data

    def __getattr__(self, attr):
        if attr not in self.data:
            error_message = '{!s} resources do not have a {!r} field'
            raise AttributeError(error_message.format(self.__class__.__name__,
                                                      attr))
        return self.data[attr]


class Bot(Resource):
    def __repr__(self):
        klass = self.__class__.__name__
        return '<{}(name={!r})>'.format(klass, self.name)

    def post(self, text, attachments=None):
        return self.manager.post(self.bot_id, text, attachments)


class Group(Resource):
    def __init__(self, manager, **data):
        super().__init__(manager, **data)
        self.messages = managers.Messages(self.manager.session, self.id)
        self.leaderboard = managers.Leaderboard(self.manager.session, self.id)
        self.memberships = managers.Memberships(self.manager.session, self.id)

        members = self.data.get('members') or []
        self.members = [Member(self.manager, self.id, **m) for m in members]
        self.created_at = datetime.fromtimestamp(self.created_at)
        self.updated_at = datetime.fromtimestamp(self.updated_at)

    def __repr__(self):
        klass = self.__class__.__name__
        return '<{}(name={!r})>'.format(klass, self.name)

    def post(self, text=None, attachments=None):
        return self.messages.create(text, attachments)

    def update(self, **details):
        return self.manager.update(id=self.id, **details)

    def destroy(self):
        return self.manager.delete(id=self.id)

    def join(self, share_token):
        return self.manager.join(group_id=self.group_id,
                                 share_token=share_token)

    def rejoin(self):
        return self.manager.rejoin(group_id=self.group_id)

    def refresh(self):
        group = self.manager.get(id=self.id)
        self.__init__(self.manager, **group.data)

    def has_omission(self, field):
        try:
            value = getattr(self, field)
            return value != self.data[field]
        except AttributeError:
            return field in self.data


class Chat(Resource):
    def __init__(self, manager, **data):
        super().__init__(manager, **data)
        self.messages = managers.DirectMessages(self.manager.session,
                                                self.other_user['id'])

    def __repr__(self):
        klass = self.__class__.__name__
        return '<{}(other_user={!r})>'.format(klass, self.other_user['name'])

    def post(self, *args, **kwargs):
        return self.messages.create(*args, **kwargs)


class GenericMessage(Resource):
    preview_length = 42

    def __init__(self, manager, conversation_id, **data):
        super().__init__(manager, **data)
        self._likes = managers.Likes(self.manager.session, conversation_id,
                                     message_id=self.id)
        self.created_at = datetime.fromtimestamp(self.created_at)

        attachments = self.data.get('attachments') or []
        self.attachments = Attachment.from_bulk_data(self.manager, attachments)

    def __repr__(self):
        klass = self.__class__.__name__
        text = self.text
        if text and len(text) > self.preview_length:
            text = text[:self.preview_length - 3] + '...'
        return ('<{}(name={!r}, text={!r}, attachments={})>'
                .format(klass, self.name, text, len(self.attachments)))

    def like(self):
        return self._likes.like()

    def unlike(self):
        return self._likes.unlike()


class Message(GenericMessage):
    def __init__(self, manager, **data):
        conversation_id = data['group_id']
        super().__init__(manager, conversation_id, **data)


class DirectMessage(GenericMessage):
    # manager could be from a chat or from a group... is that a problem?
    def __init__(self, manager, **data):
        DirectMessage.ensure_conversation_id(data)
        super().__init__(manager, **data)

    @staticmethod
    def ensure_conversation_id(data):
        # tricky tricky! the API response for *creating* a direct message
        # doesn't contain the conversation id (facepalm) so we create it
        # if it's not in the data
        if 'conversation_id' not in data:
            participant_ids = data['recipient_id'], data['sender_id']
            data['conversation_id'] = '+'.join(sorted(participant_ids))


class Block(Resource):
    def __repr__(self):
        klass = self.__class__.__name__
        return '<{}(blocked_user_id={!r})>'.format(klass, self.blocked_user_id)

    def exists(self):
        return self.manager.between(other_user_id=self.blocked_user_id)

    def unblock(self):
        return self.manager.unblock(other_user_id=self.blocked_user_id)


class Member(Resource):
    def __init__(self, manager, group_id, **data):
        super().__init__(manager, **data)
        self.messages = managers.DirectMessages(self.manager.session,
                                                other_user_id=self.user_id)
        self._user = managers.User(self.manager.session)
        self._memberships = managers.Memberships(self.manager.session,
                                                 group_id=group_id)

    def __repr__(self):
        klass = self.__class__.__name__
        return '<{}(user_id={!r}, nickname={!r})>'.format(klass, self.user_id,
                                                          self.nickname)

    def is_blocked(self):
        return self._user.blocks.between(other_user_id=self.user_id)

    def block(self):
        return self._user.blocks.block(other_user_id=self.user_id)

    def unblock(self):
        return self._user.blocks.unblock(other_user_id=self.user_id)

    def remove(self):
        return self._memberships.remove(membership_id=self.id)


class AttachmentMeta(type):
    _types = {}

    def __init__(cls, name, bases, attrs):
        cls._types[name.lower()] = cls


class Attachment(Resource, metaclass=AttachmentMeta):
    def __init__(self, manager, type, **data):
        super().__init__(manager, type=type, **data)

    def to_json(self):
        return self.data

    @classmethod
    def from_data(cls, manager, **data):
        return cls._types.get(data['type'], cls)(manager, **data)

    @classmethod
    def from_bulk_data(cls, manager, attachments):
        return [cls.from_data(manager, **a) for a in attachments]


class Image(Attachment):
    def download(self):
        return self.manager.session.get(self.url)


class Location(Attachment):
    pass


class Split(Attachment):
    pass


class Emoji(Attachment):
    pass


class Mentions(Attachment):
    pass


class MembershipRequest(Resource):

    Results = namedtuple('Results', 'members failures')

    def __init__(self, manager, *requests, **data):
        super().__init__(manager, **data)
        self._requests = requests
        self._expired_exception = None
        self._not_ready_exception = None
        self._is_ready = False
        self.results = None

    def _check_if_ready(self):
        try:
            results = self.manager.check(self.results_id)
            self._is_ready = True
            self._not_ready_exception = None
            self._process_new_members(results)
        except exceptions.ResultsNotReady as e:
            self._is_ready = False
            self._not_ready_exception = e
        except exceptions.ResultsExpired as e:
            self._is_ready = True
            self._expired_exception = e

    def _process_new_members(self, results):
        members = []
        failures = []
        data = {member['guid']: member for member in results}
        for request in self._requests:
            try:
                member_data = data[request['guid']]
            except KeyError:
                failures.append(request)
            else:
                member_data.pop('guid')
                member = Member(self.manager, **member_data)
                members.append(member)
        self.results = self.Results(members, failures)

    def is_ready(self):
        if not self._is_ready:
            self._check_if_ready()
        return self._is_ready

    def poll(self, timeout=30, interval=2):
        start = time.time()
        while time.time() - start < timeout and not self.is_ready():
            time.sleep(interval)
        return self.get()

    def get(self):
        if self._expired_exception:
            raise self._expired_exception
        if self._not_ready_exception:
            raise self._not_ready_exception
        return self.results