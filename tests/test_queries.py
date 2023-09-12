#  Ugly hack to allow absolute import from the root folder
# whatever its name is. Please forgive the heresy.

if __name__ == "__main__":
    import unittest
    from sys import path
    from os.path import dirname

    path.append(dirname(path[0]))
    from test_setup import BasicTestSetup
    from flaskinventory.view.routes import build_query_string
    from flaskinventory import dgraph
    from flaskinventory.main.model import Country

class TestQueries(BasicTestSetup):

    def test_query_builder(self):
        query = {'languages': [self.lang_german],
                 'channel': [self.channel_print],
                 'email': ["wp3@opted.eu"],
                 }

        query_string = build_query_string(query, count=True)
        res = dgraph.query(query_string)
        self.assertEqual(res['total'][0]['count'], 3)

        query = {'languages': [self.lang_german, self.lang_english],
                 'languages*connector': ['OR'],
                 'channel': [self.channel_website],
                 }

        query_string = build_query_string(query, count=True)
        res = dgraph.query(query_string)
        self.assertEqual(res['total'][0]['count'], 2)

        query = {'countries': [self.austria_uid, self.germany_uid],
                 'countries*connector': ['AND'],
                 }

        query_string = build_query_string(query, count=True)
        res = dgraph.query(query_string)
        self.assertEqual(res['total'][0]['count'], 1)

        query = {'country': [self.switzerland_uid, self.germany_uid],
                 'country*connector': ['OR'],
                 }

        query_string = build_query_string(query, count=True)
        res = dgraph.query(query_string)
        self.assertEqual(res['total'][0]['count'], 1)

        query = {'dgraph.type': ['ScientificPublication'],
                 'date_published': [2010],
                 'date_published*operator': ['gt']
                 }

        query_string = build_query_string(query, count=True)
        res = dgraph.query(query_string)
        self.assertEqual(res['total'][0]['count'], 1)

        query = {'dgraph.type': ['NewsSource'],
                 'audience_size|count': [300000],
                 'audience_size|count*operator': ['lt']
                 }

        query_string = build_query_string(query, count=True)
        res = dgraph.query(query_string)
        self.assertEqual(res['total'][0]['count'], 4)

    def test_query_route_post(self):

        with self.client as c:
            query = {'languages': [self.lang_german, self.lang_english],
                     'languages*connector': ['OR'],
                     'channel': self.channel_print,
                     'email': "wp3@opted.eu",
                     'json': True
                     }

            response = c.post('/query', data=query,
                              follow_redirects=True)

            self.assertEqual(response.json['_total_results'], 3)

    def test_private_predicates(self):

        with self.client as c:
            query = {'email': "wp3@opted.eu",
                     'json': True
                     }

            response = c.post('/query', data=query,
                              follow_redirects=True)

            self.assertEqual(response.json['_total_results'], 0)

            query = {'display_name': "Contributor",
                     'json': True
                     }

            response = c.post('/query', data=query,
                              follow_redirects=True)

            self.assertEqual(response.json['_total_results'], 0)

    def test_different_predicates(self):

        with self.client as c:
            query = {"languages": [self.lang_german],
                     "publication_kind": "alternative media",
                     "channel": self.channel_print,
                     'json': True}

            response = c.get('/query',
                             query_string=query)

            self.assertEqual(
                response.json['result'][0]['_unique_name'], "direkt_print")

            query = {"publication_kind": "newspaper",
                     "channel": self.channel_website,
                     "country": self.austria_uid,
                     "json": True}

            response = c.get('/query',
                             query_string=query)
            self.assertEqual(
                response.json['result'][0]['_unique_name'], "www.derstandard.at")

    def test_same_scalar_predicates(self):
        # same Scalar predicates are combined with OR operators
        # e.g., payment_model == "free" OR payment_model == "partly free"

        with self.client as c:
            # German that is free OR partly for free
            query = {"languages": [self.lang_german],
                     "payment_model": ["free", "partly free"],
                     "json": True
                     }

            response = c.get('/query',
                             query_string=query)
            res = [entry['_unique_name'] for entry in response.json['result']]
            self.assertCountEqual(res, 
                                  ["www.derstandard.at", "globalvoices_org_website"])

            # English that is free OR partly for free
            query = {"languages": [self.lang_english],
                     "payment_model": ["free", "partly free"],
                     "json": True
                     }

            response = c.get('/query',
                             query_string=query)
            self.assertEqual(
                response.json['result'][0]['_unique_name'], "globalvoices_org_website")

            # Free or partly for free IN Germany, but in English
            query = {"languages": [self.lang_english],
                     "payment_model": ["free", "partly free"],
                     "countries": self.germany_uid,
                     "json": True
                     }

            response = c.get('/query',
                             query_string=query)
            self.assertEqual(len(response.json['result']), 0)

            # twitter OR instagram IN austria
            query = {"channel": [self.channel_twitter, self.channel_instagram],
                     "country": self.austria_uid,
                     "json": True
                     }

            response = c.get('/query',
                             query_string=query)
            self.assertEqual(len(response.json['result']), 2)

    def test_same_list_predicates(self):
        # same List predicates are combined with AND operators
        # e.g., languages == "en" AND languages == "de"

        query = {'languages': [self.lang_english, self.lang_german],
                 "payment_model": ["free", "partly free"],
                 }

        query_string = build_query_string(query)
        res = dgraph.query(query_string)

        with self.client as c:
            # Spanish AND German speaking that is either free or partly free
            query = {"languages": [self.lang_spanish, self.lang_german],
                     "payment_model": ["free", "partly free"],
                     "json": True
                     }

            response = c.get('/query',
                             query_string=query)
            self.assertEqual(len(response.json['result']), 0)

            # English AND Hungarian speaking that is either free or partly free
            query = {"languages": [self.lang_english, self.lang_hungarian],
                     "payment_model": ["free", "partly free"],
                     "json": True
                     }

            response = c.get('/query',
                             query_string=query)
            self.assertEqual(
                response.json['result'][0]['_unique_name'], "globalvoices_org_website")

    def test_date_predicates(self):

        with self.client as c:
            # Founded by exact year
            query = {"date_founded": ["1995"],
                     "json": True}

            response = c.get('/query',
                             query_string=query)
            self.assertEqual(len(response.json['result']), 2)

            # Founded in range
            query = {"date_founded": ["1990", "2000"],
                     "json": True}

            response = c.get('/query',
                             query_string=query)
            self.assertEqual(len(response.json['result']), 4)

            # Founded before year
            query = {"date_founded": ["2000"],
                     "date_founded*operator": 'lt',
                     "json": True}

            response = c.get('/query',
                             query_string=query)
            self.assertEqual(len(response.json['result']), 6)

            # Founded after year
            query = {"date_founded": ["2000"],
                     "date_founded*operator": 'gt',
                     "json": True}

            response = c.get('/query',
                             query_string=query)
            self.assertEqual(len(response.json['result']), 5)

            # self.assertEqual(len(response.json['result']), 0)

    def test_boolean_predicates(self):
        with self.client as c:
            # verified social media account
            query = {"verified_account": True,
                     "json": True}

            response = c.get('/query',
                             query_string=query)
            self.assertEqual(len(response.json['result']), 3)

            query = {"verified_account": 'true',
                     "json": True}

            response = c.get('/query',
                             query_string=query)
            self.assertEqual(len(response.json['result']), 3)

    def test_integer_predicates(self):
        pass
        # No queryable integer predicate in current data model
        # with self.client as c:
        #     query = {"publication_cycle_weekday": 3}

        #     response = c.get('/query', query_string=query)
        #     self.assertEqual(response.json['result'][0]['_unique_name'], 'falter_print')

    def test_facet_filters(self):
        with self.client as c:
            query = {"audience_size|unit": "copies sold",
                     "audience_size|count": 52000,
                     "audience_size|count*operator": 'gt',
                     "json": True}

            response = c.get('/query',
                             query_string=query)
            self.assertEqual(
                response.json['result'][0]['_unique_name'], 'derstandard_print')

    def test_type_filters(self):

        with self.client as c:
            query = {"dgraph.type": "NewsSource",
                     "countries": self.germany_uid,
                     "json": True}

            response = c.get('/query',
                             query_string=query)
            self.assertEqual(len(response.json['result']), 1)

            query = {"dgraph.type": ["NewsSource", "Organization"],
                     "countries": self.austria_uid,
                     "json": True}

            response = c.get('/query',
                             query_string=query)
            self.assertEqual(len(response.json['result']), 11)

    def test_count(self):

        countries = Country.name.count()
        res = dgraph.query(countries)
        self.assertEqual(res['q'][0]['count'], 252)

        opted_countries = Country.opted_scope.count()
        res = dgraph.query(opted_countries)
        self.assertEqual(res['q'][0]['count'], 32)


if __name__ == "__main__":
    unittest.main(verbosity=2)
