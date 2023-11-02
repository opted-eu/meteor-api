# Ugly hack to allow absolute import from the root folder
# whatever its name is. Please forgive the heresy.

from sys import path
from os.path import dirname
import datetime
import unittest

path.append(dirname(path[0]))
from test_setup import BasicTestSetup
from meteor import dgraph
from meteor.api.notifications import *

class TestNotifications(BasicTestSetup):

    def setUp(self):
        self.Contributor = User(uid=self.contributor_uid)
        self.Reviewer = User(uid=self.reviewer_uid)
        self.Admin = User(uid=self.admin_uid)
        
        # delete all notifications
        notifications = dgraph.query('{ n(func: type(Notification)) { uid } }')
        dgraph.delete(notifications['n'])

        # remove all followings
        delete = [{'uid': self.contributor_uid,
                   'follows_entities': None,
                   'follows_types': None},
                   {'uid': self.reviewer_uid,
                   'follows_entities': None,
                   'follows_types': None},
                   {'uid': self.admin_uid,
                   'follows_entities': None,
                   'follows_types': None}]
        dgraph.delete(delete)


    def test_dispatch_notification(self):
        notification = dispatch_notification(self.Reviewer, "Test Notification", "some content", self.derstandard_facebook)

        dgraph.delete({'uid': notification})

    def test_read_notification(self):
        new_notification = dispatch_notification(self.Reviewer, "Test Notification", "some content", self.derstandard_facebook)

        unread = get_unread_notifications(self.Reviewer)
        self.assertEqual(unread[0]['uid'], new_notification)
        self.assertFalse(unread[0]['_read'])

        mark_notifications_as_read([new_notification], self.Reviewer)
        unread = get_unread_notifications(self.Reviewer)
        self.assertEqual(len(unread), 0)

        read = get_all_notifications(self.Reviewer)
        self.assertEqual(read[0]['uid'], new_notification)
        self.assertTrue(read[0]['_read'])

        dgraph.delete({'uid': new_notification})

    def test_follow_type(self):
        self.Reviewer.follow_type('Entry')
        following = self.Reviewer.show_follow_types()
        self.assertCountEqual(following, ['Entry'])

        self.Reviewer.unfollow_type('Entry')
        following = self.Reviewer.show_follow_types()
        self.assertCountEqual(following, [])

    def test_follow_entity(self):
        self.Reviewer.follow_entity(self.derstandard_facebook)
        following = self.Reviewer.show_follow_entities()
        self.assertEqual(len(following), 1)
        self.assertEqual(following[0]['uid'], self.derstandard_facebook)

        self.Reviewer.unfollow_entity(self.derstandard_facebook)
        following = self.Reviewer.show_follow_entities()
        self.assertCountEqual(following, [])

    def test_notify_new_type(self):
        self.Reviewer.follow_type('Entry')
        result = dgraph.upsert(None, set_obj={'uid': '_:test_entry',
                                        '_unique_name': 'test_entry',
                                        'dgraph.type': 'Entry',
                                        'name': 'Test Entry',
                                        'entry_review_status': 'pending'})
        
        new_entry = result.uids['test_entry']
        notify_new_type('Entry', new_entry)

        notifications = get_unread_notifications(self.Reviewer)
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]['_linked']['uid'], new_entry)
        self.assertEqual(notifications[0]['_title'], "New Entry")

        dgraph.delete({'uid': notifications[0]['uid']})
        dgraph.delete({'uid': new_entry})
        self.Reviewer.unfollow_type('Entry')

    def test_notify_new_entity(self):
        self.Reviewer.follow_entity(self.lang_german)
        result = dgraph.upsert(None, set_obj={'uid': '_:test_entry',
                                        '_unique_name': 'test_entry',
                                        'dgraph.type': ['Entry', 'Tool'],
                                        'name': 'Test Entry',
                                        'entry_review_status': 'pending',
                                        'languages': [{'uid': self.lang_german}]})
        
        new_entry = result.uids['test_entry']
        notify_new_entity(new_entry)

        notifications = get_unread_notifications(self.Reviewer)
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]['_linked']['uid'], new_entry)
        self.assertEqual(notifications[0]['_title'], "New pending Tool: <Test Entry>!")

        dgraph.delete({'uid': notifications[0]['uid']})
        dgraph.delete({'uid': new_entry})
        self.Reviewer.unfollow_entity(self.lang_german)

    
    def test_review_notification(self):
        result = dgraph.upsert(None, set_obj={'uid': '_:test_entry',
                                        '_unique_name': 'test_entry',
                                        'dgraph.type': ['Entry', 'Tool'],
                                        'name': 'Test Entry',
                                        'entry_review_status': 'accepted',
                                        '_date_created': datetime.datetime.now().isoformat(),
                                        '_added_by': {'uid': self.contributor_uid},
                                        'languages': [{'uid': self.lang_german}]})
        
        new_entry = result.uids['test_entry']
        send_review_notification(new_entry, status='accepted')

        notifications = get_unread_notifications(self.Contributor)
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]['_linked']['uid'], new_entry)
        self.assertEqual(notifications[0]['_title'], "New Entry was accepted")

        dgraph.delete({'uid': notifications[0]['uid']})
        dgraph.delete({'uid': new_entry})


    def test_notify_new_comment(self):
        self.Reviewer.follow_entity(self.derstandard_facebook)
        
        send_comment_notifications(self.derstandard_facebook)

        # Notify Author of Entry
        notifications = get_unread_notifications(self.Admin)
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]['_linked']['uid'], self.derstandard_facebook)
        self.assertEqual(notifications[0]['_title'], "New Comment on <derStandardat>!")

        dgraph.delete({'uid': notifications[0]['uid']})

        # Notify follower of Entry
        notifications = get_unread_notifications(self.Reviewer)
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]['_linked']['uid'], self.derstandard_facebook)
        self.assertEqual(notifications[0]['_title'], "New Comment on <derStandardat>!")

        dgraph.delete({'uid': notifications[0]['uid']})
        self.Reviewer.unfollow_entity(self.derstandard_facebook)



# class TestAPILoggedInContributor(TestAPILoggedOut):

#     user_login = {'email': 'contributor@opted.eu',
#                   'password': 'contributor123'}
#     logged_in = 'contributor'

#     display_name = 'Contributor'

#     def setUp(self):
#         try:
#             _ = self.headers.pop('Authorization')
#         except:
#             pass
#         with self.client as client:
#             response = client.post(
#                 '/api/user/login/token', data=self.user_login)
#             assert response.status_code == 200, response.status_code
#             token = response.json['access_token']
#             self.headers['Authorization'] = 'Bearer ' + token

#             is_logged_in = client.get('/api/user/is_logged_in',
#                                       headers=self.headers)
#             assert is_logged_in.json['status'] == 200, is_logged_in.json['status']
#             assert is_logged_in.json['is_logged_in'] == True, is_logged_in.json['is_logged_in']

#     def tearDown(self):
#         with self.client:
#             r = self.client.get('/api/user/logout',
#                                 headers=self.headers)


# class TestAPILoggedInReviewer(TestAPILoggedInContributor):

#     user_login = {'email': 'reviewer@opted.eu', 'password': 'reviewer123'}
#     logged_in = 'reviewer'

#     display_name = 'Reviewer'


# class TestAPILoggedInAdmin(TestAPILoggedInContributor):

#     user_login = {'email': 'wp3@opted.eu', 'password': 'admin123'}
#     logged_in = 'admin'

#     display_name = 'Admin'


if __name__ == "__main__":
    unittest.main(verbosity=2)
