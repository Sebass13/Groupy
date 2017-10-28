from unittest import mock

from groupy.api import memberships
from groupy.exceptions import ResultsNotReady
from groupy.exceptions import ResultsExpired
from .base import get_fake_response
from .base import TestCase


def get_fake_member_data(**kwargs):
    data = {
        'id': 'foo',
        'group_id': 'bar',
        'user_id': 'baz',
        'nicknack': 'nick',
    }
    data.update(kwargs)
    return data


class MembershipsTests(TestCase):
    def setUp(self):
        self.m_session = mock.Mock()
        self.memberships = memberships.Memberships(self.m_session,
                                                   group_id='foo')


class AddMembershipTests(MembershipsTests):
    def setUp(self):
        super().setUp()
        self.members = [{'bar': 'baz'}, {'baz': 'qux'}]
        self.m_session.post.return_value = get_fake_response(data={'qux': 'quux'})
        self.result = self.memberships.add(*self.members)

    def test_result_is_MembershipRequest(self):
        self.assertIsInstance(self.result, memberships.MembershipRequest)

    def test_payload_contained_guids(self):
        __, kwargs = self.m_session.post.call_args
        for member in kwargs['json']['members']:
            with self.subTest(member=member):
                self.assertIn('guid', member)


class CheckMembershipTests(MembershipsTests):
    def test_results_not_ready_yet(self):
        self.m_session.get.return_value = get_fake_response(code=503)
        with self.assertRaises(ResultsNotReady):
            self.memberships.check('bar')

    def test_results_expired(self):
        self.m_session.get.return_value = get_fake_response(code=404)
        with self.assertRaises(ResultsExpired):
            self.memberships.check('bar')

    def test_results_available(self):
        data = {'members': [{'baz': 'qux'}]}
        self.m_session.get.return_value = get_fake_response(data=data)
        result = self.memberships.check('bar')
        self.assertEqual(result, data['members'])


class RemoveMembershipTests(MembershipsTests):
    def test_result_is_True(self):
        self.m_session.post.return_value = mock.Mock(ok=True)
        self.assertTrue(self.memberships.remove('bar'))


class MemberTests(TestCase):
    @mock.patch('groupy.api.memberships.Memberships')
    @mock.patch('groupy.api.memberships.user')
    def setUp(self, *__):
        self.m_manager = mock.Mock()
        self.data = get_fake_member_data()
        self.member = memberships.Member(self.m_manager, **self.data)
        self._blocks = self.member._user.blocks
        self._memberships = self.member._memberships


class MemberIsBlockedTests(MemberTests):
    def setUp(self):
        super().setUp()
        self.member.is_blocked()

    def test_uses_user_id(self):
        self.assert_kwargs(self._blocks.between,
                           other_user_id=self.data['user_id'])


class BlockMemberTests(MemberTests):
    def setUp(self):
        super().setUp()
        self.member.block()

    def test_uses_user_id(self):
        self.assert_kwargs(self._blocks.block,
                           other_user_id=self.data['user_id'])


class UnblockMemberTests(MemberTests):
    def setUp(self):
        super().setUp()
        self.member.unblock()

    def test_uses_user_id(self):
        self.assert_kwargs(self._blocks.unblock,
                           other_user_id=self.data['user_id'])


class RemoveMemberTests(MemberTests):
    def setUp(self):
        super().setUp()
        self.member.remove()

    def test_uses_user_id(self):
        self.assert_kwargs(self.member._memberships.remove,
                           membership_id=self.data['id'])