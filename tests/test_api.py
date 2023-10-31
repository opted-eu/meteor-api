# Ugly hack to allow absolute import from the root folder
# whatever its name is. Please forgive the heresy.

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

    def test_post_comments(self):

        with self.client as c:
            response = c.post('/api/comment/post/' + self.derstandard_twitter, 
                              headers=self.headers,
                              json={'message': 'Testing Comment'})
            
            if not self.logged_in:
                self.assertEqual(response.status_code, 401)
            elif self.logged_in == 'Contributor':
                self.assertEqual(response.status_code, 403)
            else:
                self.assertEqual(response.status_code, 200)

            if 'uid' in response.json:
                deleted = c.get('/api/comment/delete/' + response.json['uid'],
                                headers=self.headers)
                

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


    """ Query Routs """

    def test_query_route(self):

        with self.client as c:
            query = {'languages': [self.lang_german, self.lang_english],
                     'languages*connector': ['OR'],
                     'channel': self.channel_print
                     }

            response = c.get('/api/query', query_string=query,
                              headers=self.headers)

            self.assertEqual(len(response.json), 3)

            response = c.get('/api/query/count', query_string=query,
                              headers=self.headers)

            self.assertEqual(response.json, 3)

    def test_query_private_predicates(self):

        with self.client as c:
            query = {'email': "wp3@opted.eu"}

            response = c.get('/api/query',
                              query_string=query,
                              headers=self.headers)

            self.assertEqual(response.json['status'], 400)

            query = {'display_name': "Contributor"}

            response = c.get('/api/query/count', 
                             query_string=query,
                             headers=self.headers)

            self.assertEqual(response.json['status'], 400)

    def test_query_different_predicates(self):

        with self.client as c:
            query = {"languages": [self.lang_german],
                     "publication_kind": "alternative media",
                     "channel": self.channel_print}

            response = c.get('/api/query',
                             query_string=query,
                             headers=self.headers)

            self.assertEqual(
                response.json[0]['_unique_name'], "direkt_print")

            query = {"publication_kind": "newspaper",
                     "channel": self.channel_website,
                     "country": self.austria_uid}

            response = c.get('/api/query',
                             query_string=query,
                             headers=self.headers)
            self.assertEqual(
                response.json[0]['_unique_name'], "www.derstandard.at")

    def test_query_same_scalar_predicates(self):
        # same Scalar predicates are combined with OR operators
        # e.g., payment_model == "free" OR payment_model == "partly free"

        with self.client as c:
            # German that is free OR partly for free
            query = {"languages": [self.lang_german],
                     "payment_model": ["free", "partly free"]
                     }

            response = c.get('/api/query',
                             query_string=query,
                             headers=self.headers)
            
            res = [entry['_unique_name'] for entry in response.json]
            self.assertCountEqual(res,
                                  ["www.derstandard.at", "globalvoices_org_website"])

            # English that is free OR partly for free
            query = {"languages": [self.lang_english],
                     "payment_model": ["free", "partly free"]
                     }

            response = c.get('/api/query',
                             query_string=query,
                             headers=self.headers)
            self.assertEqual(
                response.json[0]['_unique_name'], "globalvoices_org_website")

            # Free or partly for free IN Germany, but in English
            query = {"languages": [self.lang_english],
                     "payment_model": ["free", "partly free"],
                     "countries": self.germany_uid
                     }

            response = c.get('/api/query',
                             query_string=query,
                             headers=self.headers)
            self.assertEqual(len(response.json), 0)

            # twitter OR instagram IN austria
            query = {"channel": [self.channel_twitter, self.channel_instagram],
                     "country": self.austria_uid
                     }

            response = c.get('/api/query',
                             query_string=query)
            self.assertEqual(len(response.json), 2)


    def test_query_same_list_predicates(self):

        with self.client as c:
            # Spanish AND German speaking that is either free or partly free
            query = {"languages": [self.lang_spanish, self.lang_german],
                     "payment_model": ["free", "partly free"]
                     }

            response = c.get('/api/query',
                             query_string=query,
                             headers=self.headers)
            self.assertEqual(len(response.json), 0)

            # English AND Hungarian speaking that is either free or partly free
            query = {"languages": [self.lang_english, self.lang_hungarian],
                     "payment_model": ["free", "partly free"]
                     }

            response = c.get('/api/query',
                             query_string=query,
                             headers=self.headers)
            self.assertEqual(
                response.json[0]['_unique_name'], "globalvoices_org_website")

    def test_query_date_predicates(self):

        with self.client as c:
            # Founded by exact year
            query = {"date_founded": ["1995"]}

            response = c.get('/api/query',
                             query_string=query,
                             headers=self.headers)
            self.assertEqual(len(response.json), 2)

            # Founded in range
            query = {"date_founded": ["1990", "2000"]}

            response = c.get('/api/query',
                             query_string=query)
            self.assertEqual(len(response.json), 4)

            # Founded before year
            query = {"date_founded": ["2000"],
                     "date_founded*operator": 'lt'}

            response = c.get('/api/query',
                             query_string=query)
            self.assertEqual(len(response.json), 6)

            # Founded after year
            query = {"date_founded": ["2000"],
                     "date_founded*operator": 'gt'}

            response = c.get('/api/query',
                             query_string=query)
            
            self.assertEqual(len(response.json), 5)

    def test_query_boolean_predicates(self):
        with self.client as c:
            # verified social media account
            query = {"verified_account": True}

            response = c.get('/api/query',
                             query_string=query,
                             headers=self.headers)
            
            self.assertEqual(len(response.json), 3)

            query = {"verified_account": 'true'}
            response = c.get('/api/query',
                             query_string=query)
            
            self.assertEqual(len(response.json), 3)

    def test_query_facet_filters(self):
        with self.client as c:
            query = {"audience_size|unit": "copies sold",
                     "audience_size|count": 52000,
                     "audience_size|count*operator": 'gt'}

            response = c.get('/api/query',
                             query_string=query,
                             headers=self.headers)
            self.assertEqual(
                response.json[0]['_unique_name'], 'derstandard_print')

    def test_query_type_filters(self):

        with self.client as c:
            query = {"dgraph.type": "NewsSource",
                     "countries": self.germany_uid}

            response = c.get('/api/query',
                             query_string=query,
                             headers=self.headers)
            self.assertEqual(len(response.json), 1)

            query = {"dgraph.type": ["NewsSource", "Organization"],
                     "countries": self.austria_uid}

            response = c.get('/api/query/count',
                             query_string=query)
            self.assertEqual(response.json, 11)

    """ Edit Routes """

    def test_duplicate_check(self):

        with self.client as c:
            res = c.get('/api/add/check',
                        query_string={'name': 'AmCAT',
                                      'dgraph_type': 'Tool'},
                        headers=self.headers)
            
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            else:
                self.assertEqual(res.json[0]['name'], 'AmCAT')

            res = c.get('/api/add/check',
                        headers=self.headers)
            
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            else:
                self.assertEqual(res.status_code, 400)

            res = c.get('/api/add/check',
                        query_string={'name': 'AmCAT',
                                      'dgraph_type': 'Tooler'},
                        headers=self.headers)
            
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            else:
                self.assertEqual(res.status_code, 400)

            res = c.get('/api/add/check',
                        query_string={'name': 'AmCAT'},
                        headers=self.headers)
            
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            else:
                self.assertEqual(res.status_code, 400)


            res = c.get('/api/add/check',
                        query_string={'name': "10.1080/1461670X.2020.1745667",
                                      'dgraph_type': 'ScientificPublication'},
                        headers=self.headers)
            
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            else:
                self.assertEqual(res.json[0]['doi'], "10.1080/1461670X.2020.1745667")

    
    def test_new_entry(self):

        """ Test the basic functionality of the route with not too complicated edge cases """

        mock_organization = {
            'name': 'Deutsche Bank',
            'alternate_names': 'TC, ',
            'wikidata_id': "Q66048",
            'date_founded': 1956,
            'ownership_kind': 'private ownership',
            'country': self.germany_uid,
            'address': 'Schwanheimer Str. 149A, 60528 Frankfurt am Main, Deutschland',
            'employees': '5000',
            'publishes': [self.falter_print_uid, self.derstandard_print],
            'owns': self.derstandard_mbh_uid,
            'party_affiliated': 'no'
        }

        with self.client as c:
            
            res = c.post('/api/add/Organization',
                         json={'data': mock_organization},
                         headers=self.headers)
            
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            else:
                self.assertIn('uid', res.json)
                # clean up
                uid = res.json['uid']
                mutation = dgraph.delete({'uid': uid})
                self.assertTrue(mutation)

            
            res = c.post('/api/add/Organizationasd',
                         json={'data': mock_organization},
                         headers=self.headers)
            
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            else:
                self.assertEqual(res.status_code, 400)


            res = c.post('/api/add/Notification',
                         json={'data': mock_organization},
                         headers=self.headers)
            
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            else:
                self.assertEqual(res.status_code, 403)

            res = c.post('/api/add/Organization',
                         data={'data': mock_organization},
                         headers=self.headers)
            
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            else:
                self.assertEqual(res.status_code, 400)

            # ensure users cannot circumvent review system
            mock_organization['entry_review_status'] = 'accepted'
            res = c.post('/api/add/Organization',
                         json={'data': mock_organization},
                         headers=self.headers)
            
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            else:
                self.assertIn('uid', res.json)
                uid = res.json['uid']
                # clean up
                entry = dgraph.query(f"query check($uid: string) {{ q(func: uid($uid)) {{ uid expand(_all_) }}  }}",
                             variables={'$uid': uid})
                self.assertNotEqual(entry['q'][0]['entry_review_status'], 'accepted')
                mutation = dgraph.delete({'uid': uid})
                self.assertTrue(mutation)

    def test_edit_entry(self):

        with self.client as c:
            # no UID
            edit_entry = {
                'data': {
                'name': 'Test',
                'entry_review_status': 'accepted'}
            }
            
            res = c.post('/api/edit/' + self.derstandard_print,
                         json=edit_entry,
                         headers=self.headers)
            
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            elif self.logged_in == 'admin':
                self.assertEqual(res.json['uid'], self.derstandard_print)
            elif self.logged_in == 'reviewer':
                self.assertEqual(res.json['uid'], self.derstandard_print)
            else:
                self.assertEqual(res.status_code, 403)
            
            # clean up
            res = dgraph.mutation({'uid': self.derstandard_print,
                             'name': "Der Standard"})
            self.assertNotEqual(res, False)


            # wrong uid
            wrong_uid = {'uid': '0xfffffffff', **edit_entry}
            res = c.post('/api/edit/0xfffffffff',
                         json=edit_entry,
                         headers=self.headers)
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            else:
                self.assertEqual(res.status_code, 404)

            # list predicates
            data = {'data': {
                'alternate_names': ['DeR StAnDaRd']
            }}

            res = c.post('/api/edit/' + self.derstandard_print,
                         json=data,
                         headers=self.headers)
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            elif self.logged_in in ['admin', 'reviewer']:
                self.assertEqual(res.json['uid'], self.derstandard_print)
                q = dgraph.query('query ListFacets($uid: string) { q(func: uid($uid)) { alternate_names } }', 
                                 variables={'$uid': self.derstandard_print})
                self.assertEqual(len(q['q'][0]['alternate_names']), 1)
                self.assertEqual(q['q'][0]['alternate_names'][0], 'DeR StAnDaRd')
            else:
                self.assertEqual(res.status_code, 403)
            
            # clean up
            res = dgraph.mutation({'uid': self.derstandard_print,
                                    'alternate_names': ["DerStandard", "DER STANDARD"]})
            self.assertNotEqual(res, False)

            # delete list predicates
            data = {'data': {
                'alternate_names': None
            }}

            res = c.post('/api/edit/' + self.derstandard_print,
                         json=data,
                         headers=self.headers)
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            elif self.logged_in in ['admin', 'reviewer']:
                self.assertEqual(res.json['uid'], self.derstandard_print)
                q = dgraph.query('query ListFacets($uid: string) { q(func: uid($uid)) { alternate_names } }', 
                                 variables={'$uid': self.derstandard_print})
                self.assertEqual(len(q['q']), 0)
            else:
                self.assertEqual(res.status_code, 403)
            
            # clean up
            res = dgraph.mutation({'uid': self.derstandard_print,
                                    'alternate_names': ["DerStandard", "DER STANDARD"]})
            self.assertNotEqual(res, False)

           
    def test_new_learning_material(self):
        sample_data =  {
                        "authors": ["0000-0002-0387-5377", "0000-0001-5971-8816"],
                        "date_published": "2023",
                        "name": "Replication Crisis Solved with Julia",
                        "description": "Manual for making replicable research in Julia",
                        "dgraph.type": ["Entry", "Dataset"],
                        "doi": "10.1177/0165551515598926",
                        "urls": ["https://awesometutorials.org/part1","https://awesometutorials.org/part2"],
                        "programming_languages": [self.programming_julia]
                    }
  
        with self.client as c:
            res = c.post('/api/add/LearningMaterial',
                     json = {'data': sample_data},
                         headers=self.headers)
            
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            else:
                self.assertIn('uid', res.json)
                # clean up
                uid = res.json['uid']
                mutation = dgraph.delete({'uid': uid})
                self.assertTrue(mutation)

            # test empty orderedlistrelationship
            # authors are required, so empty list should raise an error
            sample_data['authors'] = []
            res = c.post('/api/add/LearningMaterial',
                        json = {'data': sample_data},
                         headers=self.headers)
            
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            else:
                # should actually be a 4xx error
                self.assertEqual(res.status_code, 500)

            

    """ Review Routes """

    def test_review_overview(self):

        # /review/overview
        # /review/overview?country=0x123&entity=0x234
        with self.client as c:
            # set sample data to "pending"
            res = dgraph.mutation({'uid': self.derstandard_print,
                                    'entry_review_status': "pending"})
            self.assertNotEqual(res, False)

            response = c.get('/api/review',
                             headers=self.headers)
            if not self.logged_in:
                self.assertEqual(response.status_code, 401)
            elif self.logged_in == 'contributor':
                self.assertEqual(response.status_code, 403)
            else:
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json[0]['uid'], self.derstandard_print)

            response = c.get('/api/review',
                             query_string={'country': self.austria_uid},
                             headers=self.headers)

            if not self.logged_in:
                self.assertEqual(response.status_code, 401)
            elif self.logged_in == 'contributor':
                self.assertEqual(response.status_code, 403)
            else:
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json[0]['uid'], self.derstandard_print)


            response = c.get('/api/review',
                             query_string={'dgraph_type': 'Tool'},
                             headers=self.headers)
            if not self.logged_in:
                self.assertEqual(response.status_code, 401)
            elif self.logged_in == 'contributor':
                self.assertEqual(response.status_code, 403)
            else:
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.json), 0)

            res = dgraph.mutation({'uid': self.derstandard_print,
                                    'entry_review_status': "accepted"})
            self.assertNotEqual(res, False)


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

            response = c.post('/api/review/submit',
                              data={'uid': tmp_entry_uid, 'status': 'accepted'},
                              headers=self.headers)
            if not self.logged_in:
                self.assertEqual(response.status_code, 401)
            elif self.logged_in == 'contributor':
                self.assertEqual(response.status_code, 403)
            else:
                print(response.json)
                self.assertEqual(response.status_code, 200)

            dgraph.delete(delete_tmp)

            response = dgraph.mutation(tmp_entry)
            tmp_entry_uid = response.uids['tempentry']

            delete_tmp['uid'] = tmp_entry_uid

            response = c.post('/api/review/submit',
                              data={'uid': tmp_entry_uid, 'status': "rejected"},
                              headers=self.headers)
            if not self.logged_in:
                # redirect to login page
                self.assertEqual(response.status_code, 401)
            elif self.logged_in == 'contributor':
                self.assertEqual(response.status_code, 403)
            else:
                self.assertEqual(response.status_code, 200)

            dgraph.delete(delete_tmp)


    """ User Profiles """

    def test_user_profile(self):
        
        with self.client as c:
            res = c.get('/api/user/profile',
                        headers=self.headers)
            
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            elif self.logged_in == 'admin':
                self.assertEqual(res.status_code, 200)
                self.assertEqual(res.json['email'], "wp3@opted.eu")
            elif self.logged_in == 'reviewer':
                self.assertEqual(res.status_code, 200)
                self.assertEqual(res.json['email'], "reviewer@opted.eu")
            elif self.logged_in == 'contributor':
                self.assertEqual(res.status_code, 200)
                self.assertEqual(res.json['email'], "contributor@opted.eu")

            # update profile
            res = c.post('/api/user/profile/update',
                        headers=self.headers,
                        json={'data': {'affiliation': 'Hogwarts'}})
            
            updated = c.get('/api/user/profile',
                            headers=self.headers)
            
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            else:
                self.assertEqual(res.status_code, 200)
                self.assertEqual(updated.json['affiliation'], "Hogwarts")

            res = c.post('/api/user/profile/update',
                        headers=self.headers,
                       json={'data': {'affiliation': None}})
            
            updated = c.get('/api/user/profile',
                            headers=self.headers)
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            else:
                self.assertEqual(res.status_code, 200)
                self.assertNotIn("affiliation", updated.json)

            # try to change email address
            # should not be allowed / have no effect
            res = c.post('/api/user/profile/update',
                        headers=self.headers,
                       json={'data': {'email': "someother@email.com"}})
            
            updated = c.get('/api/user/profile',
                            headers=self.headers)
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            elif self.logged_in == 'admin':
                self.assertEqual(res.status_code, 200)
                self.assertEqual(updated.json['email'], "wp3@opted.eu")
            elif self.logged_in == 'reviewer':
                self.assertEqual(res.status_code, 200)
                self.assertEqual(updated.json['email'], "reviewer@opted.eu")
            elif self.logged_in == 'contributor':
                self.assertEqual(res.status_code, 200)
                self.assertEqual(updated.json['email'], "contributor@opted.eu")

            # try to delete private field
            # should not be allowed / have no effect
            res = c.post('/api/user/profile/update',
                        headers=self.headers,
                       json={'data': {'_account_status': None}})
            
            updated = c.get('/api/user/profile',
                            headers=self.headers)
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            elif self.logged_in == 'admin':
                self.assertEqual(res.status_code, 200)
                self.assertEqual(updated.json['_account_status'], "active")
            elif self.logged_in == 'reviewer':
                self.assertEqual(res.status_code, 200)
                self.assertEqual(updated.json['_account_status'], "active")
            elif self.logged_in == 'contributor':
                self.assertEqual(res.status_code, 200)
                self.assertEqual(updated.json['_account_status'], "active")

    def test_show_user_entries(self):

        with self.client as c:
            res = c.get('/api/user/' + self.contributor_uid + '/entries',
                        headers=self.headers)
            
            if not self.logged_in:
                self.assertEqual(len(res.json), 0)
            elif self.logged_in == 'contributor':
                self.assertEqual(len(res.json), 1)
            else:
                self.assertEqual(len(res.json), 1)

            res = c.get('/api/user/0xfffffffffffffff/entries',
                        headers=self.headers)
            
            self.assertEqual(res.status_code, 404)

            res = c.get('/api/user/' + self.admin_uid + '/entries',
                        headers=self.headers)
            
            self.assertEqual(len(res.json), 100)

            res = c.get('/api/user/' + self.admin_uid + '/entries',
                        query_string={'page': 2},
                        headers=self.headers)
            
            self.assertEqual(len(res.json), 100)

            res = c.get('/api/user/' + self.admin_uid + '/entries',
                        query_string={'dgraph_type': 'Country'},
                        headers=self.headers)
            
            self.assertEqual(len(res.json), 100)

            res = c.get('/api/user/' + self.contributor_uid + '/entries',
                        headers=self.headers,
                        query_string={'entry_review_status': 'draft'})
            
            if not self.logged_in:
                # not logged in just gets to see all accepted entries
                self.assertEqual(len(res.json), 0)
                self.assertEqual(res.status_code, 200)
            elif self.logged_in == 'contributor':
                # can view oneself's drafts
                self.assertEqual(len(res.json), 0)
                self.assertEqual(res.status_code, 200)
            else:
                self.assertEqual(res.status_code, 403)


    """ User Management """

    def test_admin_users(self):
        with self.client as c:
            res = c.get('/api/admin/users',
                        headers=self.headers)
            
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            elif self.logged_in != 'admin':
                self.assertEqual(res.status_code, 403)
            else:
                self.assertGreaterEqual(len(res.json), 3)

    
    def test_edit_user_role(self):
        with self.client as c:
            res = c.get('/api/admin/users/' + self.contributor_uid,
                        headers=self.headers,
                        query_string={'role': 2})
            
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            elif self.logged_in != 'admin':
                self.assertEqual(res.status_code, 403)
            else:
                self.assertEqual(res.status_code, 200)
                user = dgraph.query("query User($uid: string) { q(func: uid($uid)) { role } }",
                                    variables={'$uid': self.contributor_uid})
                self.assertEqual(user['q'][0]['role'], 2)
            
            # clean up
            dgraph.update_entry({'role': 1}, self.contributor_uid)

            # use illegal value
            res = c.get('/api/admin/users/' + self.contributor_uid,
                        headers=self.headers,
                        query_string={'role': 7})
            
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            elif self.logged_in != 'admin':
                self.assertEqual(res.status_code, 403)
            else:
                self.assertEqual(res.status_code, 400)
                user = dgraph.query("query User($uid: string) { q(func: uid($uid)) { role } }",
                                    variables={'$uid': self.contributor_uid})
                self.assertEqual(user['q'][0]['role'], 1)
            
            # clean up
            dgraph.update_entry({'role': 1}, self.contributor_uid)

            # wrong user uid
            res = c.get('/api/admin/users/0xffffffffffffff',
                        headers=self.headers,
                        query_string={'role': 2})
            
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            elif self.logged_in != 'admin':
                self.assertEqual(res.status_code, 403)
            else:
                self.assertEqual(res.status_code, 404)


    """ Commenting """

    def test_view_comments(self):
        with self.client as c:
            res = c.get('/api/comment/view/' + self.derstandard_facebook,
                        headers=self.headers)

        if not self.logged_in:
            self.assertEqual(res.status_code, 401)
        else:
            self.assertEqual(res.status_code, 200)
            self.assertEqual(len(res.json), 2)

    def test_post_comment(self):

        comment = {'message': 'This is a new comment'}

        with self.client as c:

            res = c.post('/api/comment/post/' + self.derstandard_print,
                   headers=self.headers,
                   json=comment)
            
            comment_uid = None
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            else:
                self.assertEqual(res.status_code, 200)
                self.assertIn('uid', res.json)
                comment_uid = res.json['uid']

            # delete new comment
            if comment_uid:
                res = c.get('/api/comment/delete/' + comment_uid,
                    headers=self.headers)
                
                if not self.logged_in:
                    self.assertEqual(res.status_code, 401)
                else:
                    self.assertEqual(res.status_code, 200)
                    self.assertEqual(res.json['uid'], comment_uid)

    def test_delete_comment(self):

        # prepare a comment
        comment = {'uid': '_:comment',
                     'dgraph.type': ['Comment'],
                     'message': 'Will be deleted',
                     '_creator': {'uid': self.contributor_uid}
                     }

        # accept entry
        with self.client as c:
            response = dgraph.mutation(comment)
            comment_uid = response.uids['comment']

            res = c.get('/api/comment/delete/' + comment_uid,
                        headers=self.headers)
            if not self.logged_in:
                self.assertEqual(res.status_code, 401)
            elif self.logged_in == 'contributor':
                self.assertEqual(res.status_code, 200)
            elif self.logged_in == 'reviewer':
                self.assertEqual(res.status_code, 403)
            else:
                self.assertEqual(res.status_code, 200)
            
            # clean up
            mutation = dgraph.delete({'uid': comment_uid})
            self.assertTrue(mutation)


    """ Follow Entries """

    """ Notifications """

    """ Recommender System """


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
