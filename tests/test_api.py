# Ugly hack to allow absolute import from the root folder
# whatever its name is. Please forgive the heresy.

if __name__ == "__main__":
    from sys import path
    from os.path import dirname
    from flask import request
    import unittest

    path.append(dirname(path[0]))
    from test_setup import BasicTestSetup
    from meteor import dgraph


class TestAPILoggedOut(BasicTestSetup):

    headers = {'accept': 'application/json'}

    """ View Routes """

    def setUp(self):
        try:
            _ = self.headers.pop('Authorization')
        except:
            pass
        with self.client as client:
            is_logged_in = client.get('/api/user/is_logged_in',
                                      headers=self.headers)
            assert is_logged_in.json['status'] == 200, is_logged_in.json['status']
            assert is_logged_in.json['is_logged_in'] == False, is_logged_in.json['is_logged_in']


    def test_view_uid(self):

        # /view/entry/<unique_name>
        # /view/uid/<uid>
        with self.client as c:

            response = c.get('/api/view',
                             headers=self.headers)

            self.assertEqual(response.status_code, 404)

            response = c.get('/api/view/uid/' + self.derstandard_mbh_uid,
                             headers=self.headers)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['uid'], self.derstandard_mbh_uid)

            for channel in self.channels:
                response = c.get('/api/view/uid/' + channel,
                                 headers=self.headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json['uid'], channel)

            # edge cases
            response = c.get('/api/view/uid/0x0',
                             headers=self.headers)
            self.assertEqual(response.status_code, 404)

            response = c.get('/api/view/uid/0',
                             headers=self.headers)
            
            self.assertEqual(response.status_code, 404)

            response = c.get('/api/view/uid/0xffffffffffffff',
                             headers=self.headers)
            self.assertEqual(response.status_code, 404)

    def test_view_uid_pending(self):

        # pending entries

        # /view/<uid>
        with self.client as c:
            # view some one elses entry
            mutation = dgraph.mutation(
                {'uid': self.derstandard_print, 'entry_review_status': 'pending'})

            response = c.get('/api/view/uid/' + self.derstandard_print,
                             headers=self.headers)

            if not self.logged_in:
                self.assertEqual(response.status_code, 401)
            elif self.logged_in == 'contributor':
                self.assertEqual(response.status_code, 403)
            elif self.logged_in == 'reviewer':
                self.assertEqual(response.status_code, 200)
            else:
                self.assertEqual(response.status_code, 200)
                
            # view one's own entry
            mutation = dgraph.mutation(
                {'uid': self.derstandard_print,
                 'entry_review_status': 'pending',
                 '_added_by': {'uid': self.contributor_uid}})

            response = c.get('/api/view/uid/' + self.derstandard_print,
                             headers=self.headers)

            if not self.logged_in:
                self.assertEqual(response.status_code, 401)
            elif self.logged_in == 'contributor':
                self.assertEqual(response.status_code, 200)
            elif self.logged_in == 'reviewer':
                self.assertEqual(response.status_code, 200)
            else:
                self.assertEqual(response.status_code, 200)

            mutation = dgraph.mutation(
                {'uid': self.derstandard_print,
                 'entry_review_status': 'accepted',
                 '_added_by': {'uid': self.admin_uid}})

    def test_view_uid_draft(self):

        # draft entries

        # /view/<uid>
        with self.client as c:
            # view someone else's draft

            mutation = dgraph.mutation(
                {'uid': self.derstandard_print,
                 'entry_review_status': 'draft'})

            response = c.get('/api/view/uid/' + self.derstandard_print,
                             headers=self.headers)

            if not self.logged_in:
                self.assertEqual(response.status_code, 401)
            elif self.logged_in == 'contributor':
                self.assertEqual(response.status_code, 403)
            elif self.logged_in == 'reviewer':
                self.assertEqual(response.status_code, 403)
            else:
                self.assertEqual(response.status_code, 200)

            # view one's own entry
            mutation = dgraph.mutation(
                {'uid': self.derstandard_print,
                 'entry_review_status': 'draft',
                 '_added_by': {'uid': self.contributor_uid}})

            response = c.get('/api/view/uid/' + self.derstandard_print,
                             headers=self.headers)

            if not self.logged_in:
                self.assertEqual(response.status_code, 401)
            elif self.logged_in == 'contributor':
                self.assertEqual(response.status_code, 200)
            elif self.logged_in == 'reviewer':
                self.assertEqual(response.status_code, 403)
            else:
                self.assertEqual(response.status_code, 200)

            mutation = dgraph.mutation(
                {'uid': self.derstandard_print,
                 'entry_review_status': 'accepted',
                 '_added_by': {'uid': self.admin_uid}})

    def test_view_rejected(self):

        # /view/uid/<uid>
        with self.client as c:

            response = c.get('/api/view/rejected/' + self.rejected_entry,
                             headers=self.headers)

            if not self.logged_in:
                self.assertEqual(response.status_code, 401)
            else:
                self.assertEqual(response.status_code, 200)

    def test_view_unique_name(self):

        # /view/entry/<unique_name>

        with self.client as c:

            response = c.get('/api/view/entry/' + 'derstandard_mbh',
                                headers=self.headers)
            self.assertEqual(response.status_code, 200)

            response = c.get('/api/view/entry/' + 'falter_print',
                                 headers=self.headers)
            self.assertEqual(response.status_code, 200)

            response = c.get('/api/view/entry/' + 'instagram',
                                 headers=self.headers)
            self.assertEqual(response.status_code, 200)

            response = c.get('/api/view/entry/' + 'austria',
                                 headers=self.headers)
            self.assertEqual(response.status_code, 200)

    def test_view_recent(self):
        with self.client as c:

            response = c.get('/api/view/recent',
                             headers=self.headers)
            self.assertEqual(len(response.json), 5) 

            response = c.get('/api/view/recent',
                             query_string={'limit': 100},
                             headers=self.headers)
            self.assertEqual(len(response.json), 50) 

            response = c.get('/api/view/recent',
                             query_string={'limit': -10},
                             headers=self.headers)
            self.assertEqual(len(response.json), 1) 

    def test_view_comments(self):
        
        with self.client as c:
            response = c.get('/api/view/comments/' + self.www_derstandard_at,
                             headers=self.headers)

            if not self.logged_in:
                self.assertEqual(response.status_code, 401)
            else:
                self.assertEqual(response.json[0]['_creator']['uid'], self.admin_uid)
                self.assertEqual(response.json[1]['_creator']['uid'], self.reviewer_uid)


    """ Search and Lookup """

    def test_quicksearch(self):

        # /quicksearch?term=bla&limit=10
        with self.client as c:

            response = c.get('/api/quicksearch',
                             headers=self.headers)

            self.assertEqual(response.status_code, 400)

            response = c.get('/api/quicksearch', query_string={'term': 'bla'},
                             headers=self.headers)

            self.assertEqual(response.status_code, 200)

            response = c.get('/api/quicksearch', query_string={'term': "10.1080/1461670X.2020.1745667"},
                             headers=self.headers)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json), 1)

    
    def test_lookup(self):

        # /quicksearch?term=bla&limit=10
        with self.client as c:

            response = c.get('/api/lookup',
                             headers=self.headers)

            self.assertEqual(response.status_code, 400)

            response = c.get('/api/lookup', query_string={'query': 'derstandardat',
                                                               'predicate': 'identifier',
                                                               'dgraph_type': 'NewsSource'},
                             headers=self.headers)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json[0]['uid'], self.derstandard_instagram)

            response = c.get('/api/lookup', query_string={'query': "10.1080/1461670X.2020.1745667",
                                                               'predicate': 'doi'},
                             headers=self.headers)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json), 1)

    # """ Review Routes """

    # def test_overview(self):

    #     # /review/overview
    #     # /review/overview?country=0x123&entity=0x234
    #     with self.client as c:

    #         response = c.get('/review/overview')
    #         if not self.logged_in:
    #             # redirect to login page
    #             self.assertEqual(response.status_code, 302)
    #         elif self.logged_in == 'contributor':
    #             self.assertEqual(response.status_code, 403)
    #         else:
    #             self.assertEqual(response.status_code, 200)

    #         response = c.get('/review/overview',
    #                          query_string={'country': self.austria_uid})
    #         if not self.logged_in:
    #             # redirect to login page
    #             self.assertEqual(response.status_code, 302)
    #         elif self.logged_in == 'contributor':
    #             self.assertEqual(response.status_code, 403)
    #         else:
    #             self.assertEqual(response.status_code, 200)

    #         response = c.get('/review/overview',
    #                          query_string={'entity': 'Tool'})
    #         if not self.logged_in:
    #             # redirect to login page
    #             self.assertEqual(response.status_code, 302)
    #         elif self.logged_in == 'contributor':
    #             self.assertEqual(response.status_code, 403)
    #         else:
    #             self.assertEqual(response.status_code, 200)

    # def test_review_submit(self):

    #     # POST /review/submit

    #     # prepare a temp entry
    #     tmp_entry = {'uid': '_:tempentry',
    #                  'dgraph.type': ['Entry', 'NewsSource'],
    #                  'name': 'Temp Entry',
    #                  '_unique_name': 'tmp_entry',
    #                  '_date_created': '2022-05-17T10:00:00',
    #                  '_added_by': {'uid': self.contributor_uid,
    #                                  '_added_by|timestamp': '2022-05-17T10:00:00',
    #                                  '_added_by|ip': '192.168.0.1'
    #                                  }
    #                  }

    #     # accept entry

    #     with self.client as c:
    #         response = dgraph.mutation(tmp_entry)
    #         tmp_entry_uid = response.uids['tempentry']

    #     delete_tmp = {'uid': tmp_entry_uid,
    #                   'dgraph.type': None,
    #                   'name': None,
    #                   '_unique_name': None,
    #                   '_added_by': {'uid': self.contributor_uid},
    #                   '_date_created': None}

    #     with self.client as c:

    #         response = c.post('/review/submit',
    #                           data={'uid': tmp_entry_uid, 'accept': True},
    #                           headers=self.headers)
    #         if not self.logged_in:
    #             # redirect to login page
    #             self.assertEqual(response.status_code, 200)
    #             self.assertEqual(response.request.path, url_for('users.login'))
    #         elif self.logged_in == 'contributor':
    #             self.assertEqual(response.status_code, 403)
    #         else:
    #             self.assertEqual(response.status_code, 200)

    #         dgraph.delete(delete_tmp)

    #     # reject entry

    #     with self.client as c:
    #         response = dgraph.mutation(tmp_entry)
    #         tmp_entry_uid = response.uids['tempentry']

    #     delete_tmp['uid'] = tmp_entry_uid

    #     with self.client as c:

    #         response = c.post('/review/submit',
    #                           data={'uid': tmp_entry_uid, 'reject': True},
    #                           headers=self.headers)
    #         if not self.logged_in:
    #             # redirect to login page
    #             self.assertEqual(response.status_code, 200)
    #             self.assertEqual(response.request.path, url_for('users.login'))
    #         elif self.logged_in == 'contributor':
    #             self.assertEqual(response.status_code, 403)
    #         else:
    #             self.assertEqual(response.status_code, 200)

    #         dgraph.delete(delete_tmp)


class TestAPILoggedInContributor(TestAPILoggedOut):

    user_login = {'email': 'contributor@opted.eu',
                  'password': 'contributor123'}
    logged_in = 'contributor'

    display_name = 'Contributor'

    def setUp(self):
        try:
            _ = self.headers.pop('Authorization')
        except:
            pass
        with self.client as client:
            response = client.post(
                '/api/user/login/token', data=self.user_login)
            assert response.status_code == 200, response.status_code
            token = response.json['access_token']
            self.headers['Authorization'] = 'Bearer ' + token

            is_logged_in = client.get('/api/user/is_logged_in',
                                      headers=self.headers)
            assert is_logged_in.json['status'] == 200, is_logged_in.json['status']
            assert is_logged_in.json['is_logged_in'] == True, is_logged_in.json['is_logged_in']

    def tearDown(self):
        with self.client:
            r = self.client.get('/api/user/logout',
                                headers=self.headers)


class TestAPILoggedInReviewer(TestAPILoggedInContributor):

    user_login = {'email': 'reviewer@opted.eu', 'password': 'reviewer123'}
    logged_in = 'reviewer'

    display_name = 'Reviewer'


class TestAPILoggedInAdmin(TestAPILoggedInContributor):

    user_login = {'email': 'wp3@opted.eu', 'password': 'admin123'}
    logged_in = 'admin'

    display_name = 'Admin'


if __name__ == "__main__":
    unittest.main(verbosity=2)
