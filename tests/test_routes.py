# Ugly hack to allow absolute import from the root folder
# whatever its name is. Please forgive the heresy.

if __name__ == "__main__":
    from sys import path
    from os.path import dirname
    from flask import request, url_for
    from flask_login import current_user
    import unittest

    path.append(dirname(path[0]))
    from test_setup import BasicTestSetup
    from flaskinventory import dgraph


class TestRoutesLoggedOut(BasicTestSetup):

    """ View Routes """

    def test_view_search(self):

        # /search?query=bla
        with self.client as c:

            response = c.get('/search',
                             follow_redirects=True)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(request.path, url_for('main.home'))

            response = c.get('/search', query_string={'query': 'bla'},
                             follow_redirects=True)

            self.assertEqual(response.status_code, 200)

            response = c.get('/search', query_string={'query': self.derstandard_facebook},
                             follow_redirects=True)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(request.path, url_for('view.view_generic',
                                                   unique_name='derstandard_facebook',
                                                   dgraph_type='NewsSource'))

    def test_view_uid(self):

        # /view
        # /view?uid=<uid>
        # /view/uid/<uid>
        with self.client as c:

            response = c.get('/view',
                             follow_redirects=True)

            self.assertEqual(response.status_code, 404)

            response = c.get('/view',
                             query_string={'uid': self.derstandard_instagram},
                             follow_redirects=True)
            self.assertEqual(request.path, url_for('view.view_generic',
                                                   unique_name='derstandard_instagram',
                                                   dgraph_type='NewsSource'))
            self.assertEqual(response.status_code, 200)

            response = c.get('/view/uid/' + self.derstandard_mbh_uid,
                             follow_redirects=True)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(request.path, url_for('view.view_generic',
                                                   unique_name='derstandard_mbh',
                                                   dgraph_type='Organization'))

            for channel in self.channels:
                response = c.get('/view/uid/' + channel,
                                 follow_redirects=True)
                self.assertEqual(response.status_code, 200)

                response = c.get('/view',
                                 query_string={'uid': channel},
                                 follow_redirects=True)
                self.assertEqual(response.status_code, 200)

            # edge cases
            response = c.get('/view/uid/0x0', follow_redirects=True)
            self.assertEqual(response.status_code, 404)

            response = c.get('/view/uid/0', follow_redirects=True)
            self.assertEqual(response.status_code, 404)

    def test_view_uid_pending(self):

        # pending entries

        # /view?uid=<uid>
        with self.client as c:
            # view some one elses entry
            mutation = dgraph.mutation(
                {'uid': self.derstandard_print, 'entry_review_status': 'pending'})

            response = c.get('/view',
                             query_string={'uid': self.derstandard_print},
                             follow_redirects=True)

            if not self.logged_in:
                self.assertEqual(response.status_code, 200)
                self.assertEqual(request.path, url_for('users.login'))
            elif self.logged_in == 'contributor':
                self.assertEqual(response.status_code, 403)
            elif self.logged_in == 'reviewer':
                self.assertEqual(response.status_code, 200)
            else:
                self.assertEqual(response.status_code, 200)
                self.assertEqual(request.path, url_for(
                    'view.view_generic', unique_name="derstandard_print", dgraph_type='NewsSource'))

            # view one's own entry
            mutation = dgraph.mutation(
                {'uid': self.derstandard_print,
                 'entry_review_status': 'pending',
                 '_added_by': {'uid': self.contributor_uid}})

            response = c.get('/view',
                             query_string={'uid': self.derstandard_print},
                             follow_redirects=True)

            if not self.logged_in:
                self.assertEqual(response.status_code, 200)
                self.assertEqual(request.path, url_for('users.login'))
            elif self.logged_in == 'contributor':
                self.assertEqual(response.status_code, 200)
            elif self.logged_in == 'reviewer':
                self.assertEqual(response.status_code, 200)
            else:
                self.assertEqual(response.status_code, 200)
                self.assertEqual(request.path, url_for(
                    'view.view_generic', unique_name="derstandard_print", dgraph_type='NewsSource'))

            mutation = dgraph.mutation(
                {'uid': self.derstandard_print,
                 'entry_review_status': 'accepted',
                 '_added_by': {'uid': self.admin_uid}})

    def test_view_uid_draft(self):

        # draft entries

        # /view?uid=<uid>
        with self.client as c:

            mutation = dgraph.mutation(
                {'uid': self.derstandard_print,
                 'entry_review_status': 'draft'})

            response = c.get('/view',
                             query_string={'uid': self.derstandard_print},
                             follow_redirects=True)

            if not self.logged_in:
                self.assertEqual(response.status_code, 200)
                self.assertEqual(request.path, url_for('users.login'))
            elif self.logged_in == 'contributor':
                self.assertEqual(response.status_code, 403)
            elif self.logged_in == 'reviewer':
                self.assertEqual(response.status_code, 403)
            else:
                self.assertEqual(response.status_code, 200)
                self.assertEqual(request.path, url_for(
                    'view.view_generic', unique_name="derstandard_print", dgraph_type='NewsSource'))

            # view one's own entry
            mutation = dgraph.mutation(
                {'uid': self.derstandard_print,
                 'entry_review_status': 'draft',
                 '_added_by': {'uid': self.contributor_uid}})

            response = c.get('/view',
                             query_string={'uid': self.derstandard_print},
                             follow_redirects=True)

            if not self.logged_in:
                self.assertEqual(response.status_code, 200)
                self.assertEqual(request.path, url_for('users.login'))
            elif self.logged_in == 'contributor':
                self.assertEqual(response.status_code, 200)
            elif self.logged_in == 'reviewer':
                self.assertEqual(response.status_code, 403)
            else:
                self.assertEqual(response.status_code, 200)
                self.assertEqual(request.path, url_for(
                    'view.view_generic', unique_name="derstandard_print", dgraph_type='NewsSource'))

            mutation = dgraph.mutation(
                {'uid': self.derstandard_print,
                 'entry_review_status': 'accepted',
                 '_added_by': {'uid': self.admin_uid}})

    def test_view_rejected(self):

        # /view
        # /view?uid=<uid>
        # /view/uid/<uid>
        with self.client as c:

            response = c.get('/view/rejected/')
            self.assertEqual(response.status_code, 404)

            response = c.get('/view/rejected/' + self.rejected_entry)

            if not self.logged_in:
                self.assertEqual(response.status_code, 403)
            else:
                self.assertEqual(response.status_code, 200)

    def test_view_generic(self):

        # /view/<string:dgraph_type>/uid/<uid>
        # /view/<string:dgraph_type>/<string:unique_name>

        with self.client as c:

            for organization in self.organizations:
                response = c.get('/view/Organzation/uid/' + organization,
                                 follow_redirects=True)
                self.assertEqual(response.status_code, 200)

            for source in self.sources:
                response = c.get('/view/NewsSource/uid/' + source,
                                 follow_redirects=True)
                self.assertEqual(response.status_code, 200)

            for channel in self.channels:
                response = c.get('/view/channel/uid/' + channel,
                                 follow_redirects=True)
                self.assertEqual(response.status_code, 200)

            for country in self.countries:
                response = c.get('/view/country/uid/' + country,
                                 follow_redirects=True)
                self.assertEqual(response.status_code, 200)

            response = c.get('/view/MetaVariable/uid/' + self.derstandard_facebook)
            self.assertEqual(response.status_code, 302)

            response = c.get('/view/Tool/uid/0xffffffffffffff',
                             follow_redirects=True)
            self.assertEqual(response.status_code, 404)

    """ Review Routes """

    def test_overview(self):

        # /review/overview
        # /review/overview?country=0x123&entity=0x234
        with self.client as c:

            response = c.get('/review/overview')
            if not self.logged_in:
                # redirect to login page
                self.assertEqual(response.status_code, 302)
            elif self.logged_in == 'contributor':
                self.assertEqual(response.status_code, 403)
            else:
                self.assertEqual(response.status_code, 200)

            response = c.get('/review/overview',
                             query_string={'country': self.austria_uid})
            if not self.logged_in:
                # redirect to login page
                self.assertEqual(response.status_code, 302)
            elif self.logged_in == 'contributor':
                self.assertEqual(response.status_code, 403)
            else:
                self.assertEqual(response.status_code, 200)

            response = c.get('/review/overview',
                             query_string={'entity': 'Tool'})
            if not self.logged_in:
                # redirect to login page
                self.assertEqual(response.status_code, 302)
            elif self.logged_in == 'contributor':
                self.assertEqual(response.status_code, 403)
            else:
                self.assertEqual(response.status_code, 200)

    def test_review_submit(self):

        # POST /review/submit

        # prepare a temp entry
        tmp_entry = {'uid': '_:tempentry',
                     'dgraph.type': ['Entry', 'NewsSource'],
                     'name': 'Temp Entry',
                     '_unique_name': 'tmp_entry',
                     '_date_created': '2022-05-17T10:00:00',
                     '_added_by': {'uid': self.contributor_uid,
                                     '_added_by|timestamp': '2022-05-17T10:00:00',
                                     '_added_by|ip': '192.168.0.1'
                                     }
                     }

        # accept entry

        with self.client as c:
            response = dgraph.mutation(tmp_entry)
            tmp_entry_uid = response.uids['tempentry']

        delete_tmp = {'uid': tmp_entry_uid,
                      'dgraph.type': None,
                      'name': None,
                      '_unique_name': None,
                      '_added_by': {'uid': self.contributor_uid},
                      '_date_created': None}

        with self.client as c:

            response = c.post('/review/submit',
                              data={'uid': tmp_entry_uid, 'accept': True},
                              follow_redirects=True)
            if not self.logged_in:
                # redirect to login page
                self.assertEqual(response.status_code, 200)
                self.assertEqual(request.path, url_for('users.login'))
            elif self.logged_in == 'contributor':
                self.assertEqual(response.status_code, 403)
            else:
                self.assertEqual(response.status_code, 200)

            dgraph.delete(delete_tmp)

        # reject entry

        with self.client as c:
            response = dgraph.mutation(tmp_entry)
            tmp_entry_uid = response.uids['tempentry']

        delete_tmp['uid'] = tmp_entry_uid

        with self.client as c:

            response = c.post('/review/submit',
                              data={'uid': tmp_entry_uid, 'reject': True},
                              follow_redirects=True)
            if not self.logged_in:
                # redirect to login page
                self.assertEqual(response.status_code, 200)
                self.assertEqual(request.path, url_for('users.login'))
            elif self.logged_in == 'contributor':
                self.assertEqual(response.status_code, 403)
            else:
                self.assertEqual(response.status_code, 200)

            dgraph.delete(delete_tmp)


class TestRoutesLoggedInContributor(TestRoutesLoggedOut):

    user_login = {'email': 'contributor@opted.eu',
                  'password': 'contributor123'}
    logged_in = 'contributor'

    display_name = 'Contributor'

    def setUp(self):
        with self.client:
            response = self.client.post(
                '/login', data=self.user_login)
            assert response.status_code == 302
            assert "profile" in response.location
            assert current_user.display_name == self.display_name

    def tearDown(self):
        with self.client:
            self.client.get('/logout')


class TestRoutesLoggedInReviewer(TestRoutesLoggedInContributor):

    user_login = {'email': 'reviewer@opted.eu', 'password': 'reviewer123'}
    logged_in = 'reviewer'

    display_name = 'Reviewer'


class TestRoutesLoggedInAdmin(TestRoutesLoggedInContributor):

    user_login = {'email': 'wp3@opted.eu', 'password': 'admin123'}
    logged_in = 'admin'

    display_name = 'Admin'


if __name__ == "__main__":
    unittest.main(verbosity=2)
