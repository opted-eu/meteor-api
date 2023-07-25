
#  Ugly hack to allow absolute import from the root folder
# whatever its name is. Please forgive the heresy.

if __name__ == "__main__":
    from sys import path
    from os.path import dirname

    path.append(dirname(path[0]))
    from test_setup import BasicTestSetup
    from flaskinventory import dgraph

    import unittest
    from unittest.mock import patch
    import copy
    import secrets
    import datetime
    from flaskinventory.flaskdgraph import Schema
    from flaskinventory.flaskdgraph.dgraph_types import UID, Scalar
    from flaskinventory.main.model import Entry, Organization, NewsSource, User, ScientificPublication
    from flaskinventory.main.sanitizer import Sanitizer
    from flaskinventory.errors import InventoryValidationError, InventoryPermissionError
    from flaskinventory import create_app, dgraph
    from flaskinventory.users.constants import USER_ROLES
    from flaskinventory import AnonymousUser
    from flask_login import current_user


def mock_wikidata(*args):
    return {'wikidata_id': "Q49653", 
            'alternate_names': [], 
            'date_founded': datetime.datetime(1950, 6, 5, 0, 0), 
            'address': 'Stuttgart'}

@patch('flaskinventory.main.sanitizer.get_wikidata', mock_wikidata) 
class TestSanitizers(BasicTestSetup):

    """
        Test Cases for Sanitizer classes
    """

    def setUp(self):

        self.anon_user = AnonymousUser()
        self.contributor = User(email="contributor@opted.eu")
        self.reviewer = User(email="reviewer@opted.eu")

        self.mock_data1 = {
            'name': 'Test',
            'alternate_names': 'Some, Other Name, ',
        }

        self.mock_data2 = {
            'name': 'Test Somethin',
            'alternate_names': ['Some', 'Other Name', ''],
        }

        self.mock1_solution_keys = ['dgraph.type', 'uid', '_added_by', 'entry_review_status',
                                    '_date_created', '_unique_name', 'name', 'alternate_names', 'wikidata_id']

        self.mock2_solution_keys = ['dgraph.type', 'uid', '_added_by', 'entry_review_status',
                                    '_date_created', '_unique_name', 'name', 'alternate_names', 'wikidata_id']

        self.mock_organization = {
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

    def tearDown(self):
        with self.client:
            self.client.get('/logout')

    def test_new_entry(self):

        with self.client:
            response = self.client.post(
                '/login', data={'email': 'contributor@opted.eu', 'password': 'contributor123'})
            self.assertEqual(current_user.display_name, 'Contributor')

            with self.app.app_context():
                sanitizer = Sanitizer(self.mock_data1)
                self.assertEqual(sanitizer.is_upsert, False)
                self.assertCountEqual(
                    list(sanitizer.entry.keys()), self.mock1_solution_keys)
                self.assertEqual(sanitizer.entry['_unique_name'], '_test')
                self.assertEqual(type(sanitizer.entry['alternate_names']), list)

                sanitizer = Sanitizer(self.mock_data2)
                self.assertEqual(sanitizer.is_upsert, False)
                self.assertCountEqual(
                    list(sanitizer.entry.keys()), self.mock2_solution_keys)
                self.assertEqual(sanitizer.entry['_unique_name'], '_testsomethin')
                self.assertEqual(type(sanitizer.entry['alternate_names']), list)
                self.assertEqual(len(sanitizer.entry['alternate_names']), 2)

                self.assertRaises(TypeError, Sanitizer, [1, 2, 3])

            self.client.get('/logout')
            self.assertRaises(InventoryPermissionError,
                              Sanitizer, self.mock_data2)
            

    def test_list_facets(self):
        mock_data = {
            'name': 'Test',
            'alternate_names': 'Jay Jay,Jules,JB',
            'Jay Jay@kind': 'first',
            'Jules@kind': 'official',
            'JB@kind': 'CS-GO'
        }

        with self.client:
            response = self.client.post(
                '/login', data={'email': 'contributor@opted.eu', 'password': 'contributor123'})
            self.assertEqual(current_user.display_name, 'Contributor')

            with self.app.app_context():
                sanitizer = Sanitizer(mock_data)
                # get rid of regular str entries
                sanitizer.entry['alternate_names'] = [
                    scalar for scalar in sanitizer.entry['alternate_names'] if not isinstance(scalar, str)]

                # assert we have all three as scalar with the correct attribute
                self.assertIsInstance(
                    sanitizer.entry['alternate_names'][0], Scalar)
                self.assertTrue(
                    hasattr(sanitizer.entry['alternate_names'][0], "facets"))
                self.assertEqual(sanitizer.entry['alternate_names'][0].facets, {
                                 'kind': 'first'})
                self.assertIn(
                    '<alternate_names> "Jay Jay" (kind="first")', sanitizer.set_nquads)

                self.assertIsInstance(
                    sanitizer.entry['alternate_names'][1], Scalar)
                self.assertTrue(
                    hasattr(sanitizer.entry['alternate_names'][1], "facets"))
                self.assertEqual(sanitizer.entry['alternate_names'][1].facets, {
                                 'kind': 'official'})
                self.assertIn(
                    '<alternate_names> "Jules" (kind="official")', sanitizer.set_nquads)

                self.assertIsInstance(
                    sanitizer.entry['alternate_names'][2], Scalar)
                self.assertTrue(
                    hasattr(sanitizer.entry['alternate_names'][2], "facets"))
                self.assertEqual(sanitizer.entry['alternate_names'][2].facets, {
                                 'kind': 'CS-GO'})
                self.assertIn('<alternate_names> "JB" (kind="CS-GO")',
                              sanitizer.set_nquads)

    def test_edit_entry(self):

        with self.client:
            response = self.client.post(
                '/login', data={'email': 'contributor@opted.eu', 'password': 'contributor123'})
            self.assertEqual(current_user.display_name, 'Contributor')

            with self.app.app_context():
                # no UID
                edit_entry = {
                    'entry_review_status': 'accepted', **self.mock_data1}
                self.assertRaises(InventoryValidationError,
                                  Sanitizer.edit, edit_entry)
                self.assertRaises(InventoryValidationError,
                                  Sanitizer.edit, self.mock_data2)

                wrong_uid = {'uid': '0xfffffffff', **edit_entry}
                # wrong uid
                self.assertRaises(InventoryValidationError,
                                  Sanitizer.edit, wrong_uid)

                wrong_user = {'uid': self.derstandard_mbh_uid, **edit_entry}
                # wrong permissions
                self.assertRaises(InventoryPermissionError,
                                  Sanitizer.edit, wrong_user)

            self.client.get('/logout')

        with self.client:
            response = self.client.post(
                '/login', data={'email': 'reviewer@opted.eu', 'password': 'reviewer123'})
            self.assertEqual(current_user.display_name, 'Reviewer')
            with self.app.app_context():
                correct = {'uid': self.derstandard_mbh_uid, **edit_entry}
                sanitizer = Sanitizer.edit(correct)
                self.assertEqual(sanitizer.is_upsert, True)
                self.assertNotIn('dgraph.type', sanitizer.entry.keys())
                self.assertIn('_edited_by', sanitizer.entry.keys())
                self.assertCountEqual(
                    sanitizer.overwrite[sanitizer.entry_uid], ['alternate_names'])

    def test_new_org(self):

        with self.client:
            response = self.client.post(
                '/login', data={'email': 'contributor@opted.eu', 'password': 'contributor123'})
            self.assertEqual(current_user.display_name, 'Contributor')

            with self.app.app_context():
                sanitizer = Sanitizer(
                    self.mock_organization, dgraph_type=Organization)
                self.assertEqual(sanitizer.is_upsert, False)
                self.assertCountEqual(sanitizer.entry['dgraph.type'], [
                                      'Entry', 'Organization'])
                self.assertEqual(
                    sanitizer.entry['entry_review_status'], 'pending')
                self.assertEqual(sanitizer.entry['_unique_name'], 'organization_de_deutschebank')
                self.assertIsNotNone(sanitizer.set_nquads)
                self.assertIsNone(sanitizer.delete_nquads)
                # WikiDataID for Deutsche Bank
                self.assertEqual(str(sanitizer.entry['wikidata_id']), 'Q66048')
                self.assertIn('employees', sanitizer.entry.keys())

                mock_org = copy.deepcopy(self.mock_organization)
                mock_org.pop('address')
                sanitizer = Sanitizer(
                    mock_org, dgraph_type=Organization)
                self.assertEqual(sanitizer.is_upsert, False)
                self.assertCountEqual(sanitizer.entry['dgraph.type'], [
                                      'Entry', 'Organization'])
                self.assertEqual(
                    sanitizer.entry['entry_review_status'], 'pending')
                self.assertEqual(sanitizer.entry['_unique_name'], 'organization_de_deutschebank')
                self.assertIsNotNone(sanitizer.set_nquads)
                self.assertIsNone(sanitizer.delete_nquads)

    def test_edit_org(self):
        overwrite_keys = ['country', 'publishes',
                          'date_founded', 'address']

        mock_org_edit = {
            "uid": self.derstandard_mbh_uid,
            "name": "STANDARD Verlagsgesellschaft m.b.H.",
            "country": self.austria_uid,
            "entry_review_status": "accepted",
            "date_founded": "1995-04-28T00:00:00Z",
            "_unique_name": "derstandard_mbh",
            "address": "Vordere Zollamtsstraße 13, 1030 Wien",
            "ownership_kind": "private ownership",
            "publishes": [self.derstandard_print,
                          self.derstandard_facebook,
                          self.derstandard_instagram,
                          self.derstandard_twitter,
                          self.www_derstandard_at]
        }
        with self.client:
            response = self.client.post(
                '/login', data={'email': 'reviewer@opted.eu', 'password': 'reviewer123'})
            self.assertEqual(current_user.display_name, 'Reviewer')

            with self.app.app_context():
                sanitizer = Sanitizer.edit(
                    mock_org_edit, dgraph_type=Organization)
                self.assertCountEqual(
                    sanitizer.overwrite[sanitizer.entry['uid']], overwrite_keys)
                self.assertEqual(len(sanitizer.entry['publishes']), 5)

                mock_org_edit['uid'] = self.derstandard_mbh_uid
                mock_org_edit['publishes'] = " ,".join(
                    [self.derstandard_print, self.derstandard_facebook, self.derstandard_instagram, self.derstandard_twitter])
                mock_org_edit['country'] = self.germany_uid
                mock_org_edit['date_founded'] = '2010'
                sanitizer = Sanitizer.edit(
                    mock_org_edit, dgraph_type=Organization)
                self.assertEqual(len(sanitizer.entry['publishes']), 4)
                # self.assertEqual(type(sanitizer.entry['date_founded']), datetime)

    def test_draft_source(self):

        # this is a raw dgraph mutation
        new_draft = {'uid': '_:newdraft',
                      'dgraph.type': 'NewsSource',
                      'channel': {'uid': self.channel_print},
                      'channel_unique_name': 'print',
                      'name': 'Schwäbische Post',
                      '_unqiue_name': 'newssource_germany_schwaebischepost_print',
                      'publication_kind': 'newspaper',
                      'geographic_scope': 'subnational',
                      'countries': {'uid': self.germany_uid},
                      'languages': {'uid': self.lang_german},
                      'entry_review_status': 'draft',
                      '_added_by': {'uid': self.reviewer.uid}}

        # create a mock draft entry
        with self.client:
            response = self.client.post(
                '/login', data={'email': 'reviewer@opted.eu', 'password': 'reviewer123'})
            self.assertEqual(current_user.display_name, 'Reviewer')

            with self.app.app_context():
                res = dgraph.mutation(new_draft)
                # get the UID of the mock draft
                uid = res.uids['newdraft']

            self.client.get('/logout')

        # this is a dict that needs to be sanitized
        edited_draft = {'uid': uid,
                      'channel': self.channel_print,
                      'channel_unique_name': 'print',
                      'name': 'Schwäbische Post',
                      'date_founded': '2000',
                      'publication_kind': 'newspaper',
                      'special_interest': 'no',
                      'publication_cycle': 'continuous',
                      'geographic_scope': 'subnational',
                      'countries': self.germany_uid,
                      'languages': [self.lang_german],
                      'payment_model': 'partly free',
                      'contains_ads': 'non subscribers',
                      'publishes_org': self.derstandard_mbh_uid,
                      'related_news_sources': [self.falter_print_uid],
                      'entry_review_status': 'pending'}
        
        # test if user
        with self.client:
            response = self.client.post(
                '/login', data={'email': 'contributor@opted.eu', 'password': 'contributor123'})
            self.assertEqual(current_user.display_name, 'Contributor')

            with self.app.app_context():
                with self.assertRaises(InventoryPermissionError):
                    sanitizer = Sanitizer.edit(edited_draft, dgraph_type=NewsSource)
                
            self.client.get('/logout')

        # test if owner can edit
        with self.client:
            response = self.client.post(
                '/login', data={'email': 'reviewer@opted.eu', 'password': 'reviewer123'})
            self.assertEqual(current_user.display_name, 'Reviewer')

            with self.app.app_context():

                sanitizer = Sanitizer.edit(edited_draft, dgraph_type=NewsSource)
                self.assertIn("<_edited_by>", sanitizer.set_nquads)
                self.assertIn(
                    '<_unique_name> "newssource_germany_schwabischepost_print"', sanitizer.set_nquads)

            self.client.get('/logout')

        # delete draft after test
        with self.client:
            response = self.client.post(
                '/login', data={'email': 'wp3@opted.eu', 'password': 'admin123'})
            self.assertEqual(current_user.display_name, 'Admin')

            with self.app.app_context():
                res = dgraph.delete({'uid': uid})

            self.client.get('/logout')

    @patch('flaskinventory.main.sanitizer.parse_meta') 
    @patch('flaskinventory.main.sanitizer.siterankdata') 
    @patch('flaskinventory.main.sanitizer.find_sitemaps') 
    @patch('flaskinventory.main.sanitizer.find_feeds') 
    def test_new_website(self, mock_find_feeds, mock_find_sitemaps, mock_siterankdata, mock_parse_meta):
        mock_parse_meta.return_value = {'names': ['Tagesthemen'], 
                                        'urls': ['https://www.tagesschau.de/']}
        mock_siterankdata.return_value = 3_000_000
        mock_find_sitemaps.return_value = ["https://www.tagesschau.de/xml/rss2/"]
        mock_find_feeds.return_value = ["https://www.tagesschau.de/rss"]

        new_website = {
            "channel_unique_name": "website",
            "channel": self.channel_website,
            "name": "https://www.tagesschau.de/",
            "alternate_names": "Tagesschau,Tagesthemen",
            "website_allows_comments": "no",
            "date_founded": "2000",
            "publication_kind": "tv show",
            "special_interest": "yes",
            "topical_focus": "politics",
            "publication_cycle": "multiple times per week",
            "publication_cycle_weekday": ["1", "2", "3", "4", "5"],
            "geographic_scope": "national",
            "countries": self.germany_uid,
            "languages": self.lang_german,
            "payment_model": "free",
            "contains_ads": "no",
                            "publishes_org": [
                                "ARD",
                                self.derstandard_mbh_uid
            ],
            "publishes_person": "Caren Miosga",
            "party_affiliated": "no",
            "related_news_sources": [
                                "https://twitter.com/tagesschau",
                                "https://instagram.com/tagesschau",
            ],
            "newsource_https://twitter.com/tagesschau": f"{self.channel_twitter}",
            "newsource_https://instagram.com/tagesschau": f"{self.channel_instagram}",
        }

        with self.client:
            response = self.client.post(
                '/login', data={'email': 'reviewer@opted.eu', 'password': 'reviewer123'})
            self.assertEqual(current_user.display_name, 'Reviewer')

            with self.app.app_context():
                sanitizer = Sanitizer(new_website, dgraph_type=NewsSource)
                self.assertEqual(type(sanitizer.set_nquads), str)
                self.assertIn(
                    '<_unique_name> "newssource_germany_wwwtagesschaude_website"', sanitizer.set_nquads)
                
            self.client.get('/logout')

    @patch('flaskinventory.main.sanitizer.twitter') 
    def test_new_twitter(self, mock_twitter):

        mock_twitter.return_value = {'followers': 3_000_000, 
                                        'fullname': 'tagesschau', 
                                        'joined': datetime.date(2007, 1, 1), 
                                        'verified': True}

        new_twitter = {
            "channel": self.channel_twitter,
            "name": "@tagesschau",
            "alternate_names": "Tagesschau,Tagesthemen",
            "publication_kind": "tv show",
            "special_interest": "yes",
            "topical_focus": "politics",
            "publication_cycle": "continuous",
            "geographic_scope": "national",
            "countries": self.germany_uid,
            "languages": self.lang_german,
            "payment_model": "free",
            "contains_ads": "no",
            "publishes_org": [
                            "ARD",
                            self.derstandard_mbh_uid
            ],
            "publishes_person": "Caren Miosga",
            "party_affiliated": "no",
        }

        with self.client:
            response = self.client.post(
                '/login', data={'email': 'reviewer@opted.eu', 'password': 'reviewer123'})
            self.assertEqual(current_user.display_name, 'Reviewer')

            with self.app.app_context():
                sanitizer = Sanitizer(new_twitter, dgraph_type=NewsSource)
                self.assertEqual(type(sanitizer.set_nquads), str)
                self.assertIn(
                    '<_unique_name> "newssource_germany_tagesschau_twitter"', sanitizer.set_nquads)

                mock_twitter.assert_called_with('tagesschau')

            self.client.get('/logout')

    @patch('flaskinventory.main.sanitizer.instagram') 
    def test_new_instagram(self, mock_instagram):

        mock_instagram.return_value = {'followers': 3_000_000, 
                                       'fullname': "tagesschau", 
                                       'verified': True}

        new_instagram = {
            "channel": self.channel_instagram,
            "name": "tagesschau",
            "alternate_names": "Tagesschau,Tagesthemen",
            "publication_kind": "tv show",
            "special_interest": "yes",
            "topical_focus": "politics",
            "publication_cycle": "continuous",
            "geographic_scope": "national",
            "countries": self.germany_uid,
            "languages": self.lang_german,
            "payment_model": "free",
            "contains_ads": "no",
            "publishes_org": [
                            "ARD",
                            self.derstandard_mbh_uid
            ],
            "publishes_person": "Caren Miosga",
            "party_affiliated": "no",
            "related_sources": [
                "https://twitter.com/tagesschau",
            ]
        }

        with self.client:
            response = self.client.post(
                '/login', data={'email': 'reviewer@opted.eu', 'password': 'reviewer123'})
            self.assertEqual(current_user.display_name, 'Reviewer')

            with self.app.app_context():
                sanitizer = Sanitizer(new_instagram, dgraph_type=NewsSource)
                self.assertEqual(type(sanitizer.set_nquads), str)
                self.assertIn(
                    '<_unique_name> "newssource_germany_tagesschau_instagram"', sanitizer.set_nquads)

            self.client.get('/logout')

    @patch('flaskinventory.main.sanitizer.telegram') 
    def test_new_telegram(self, mock_telegram):

        mock_telegram.return_value = {'followers': 1_000_000, 
                                      'fullname': "ARD_tagesschau_bot", 
                                      'joined': datetime.date(2012, 1, 1), 
                                      'verified': True, 
                                      'telegram_id': 12345678}

        new_telegram = {
            "channel": self.channel_telegram,
            "name": "ARD_tagesschau_bot",
            "alternate_names": "Tagesschau,Tagesthemen",
            "publication_kind": "tv show",
            "special_interest": "yes",
            "topical_focus": "politics",
            "publication_cycle": "continuous",
            "geographic_scope": "national",
            "countries": self.germany_uid,
            "languages": self.lang_german,
            "payment_model": "free",
            "contains_ads": "no",
            "publishes_org": [
                            "ARD",
                            self.derstandard_mbh_uid
            ],
            "publishes_person": "Caren Miosga",
            "party_affiliated": "no",
            "related_sources": [
                "https://twitter.com/tagesschau",
            ]
        }

        with self.client:
            response = self.client.post(
                '/login', data={'email': 'reviewer@opted.eu', 'password': 'reviewer123'})
            self.assertEqual(current_user.display_name, 'Reviewer')

            with self.app.app_context():
                sanitizer = Sanitizer(new_telegram, dgraph_type=NewsSource)
                self.assertEqual(type(sanitizer.set_nquads), str)
                self.assertIn(
                    '<_unique_name> "newssource_germany_ardtagesschaubot_telegram"', sanitizer.set_nquads)

            self.client.get('/logout')

    @patch('flaskinventory.main.sanitizer.vkontakte') 
    def test_new_vk(self, mock_vk):

        mock_vk.return_value = {'followers': 100_000, 
                                'fullname': "anonymousnews_org", 
                                'verified': False,
                                'description': 'Description text'}

        new_vk = {
            "channel": self.channel_vkontakte,
            "name": "anonymousnews_org",
            "publication_kind": "alternative media",
            "publication_cycle": "continuous",
            "geographic_scope": "multinational",
            "countries": [self.germany_uid, self.austria_uid],
            "languages": self.lang_german,
            "payment_model": "free",
            "contains_ads": "no",
        }

        with self.client:
            response = self.client.post(
                '/login', data={'email': 'reviewer@opted.eu', 'password': 'reviewer123'})
            self.assertEqual(current_user.display_name, 'Reviewer')

            with self.app.app_context():
                sanitizer = Sanitizer(new_vk, dgraph_type=NewsSource)
                self.assertEqual(type(sanitizer.set_nquads), str)

                possible_unique_names = ('<_unique_name> "newssource_austria_anonymousnewsorg_vkontakte"',
                                         '<_unique_name> "newssource_germany_anonymousnewsorg_vkontakte"')
                self.assertTrue(any([x in sanitizer.set_nquads for x in possible_unique_names]))

            self.client.get('/logout')

    def test_new_facebook(self):

        mock_facebook = {'channel': self.channel_facebook,
                         'name': 'some_source',
                         'alternate_names': 'other names',
                         'date_founded': '2000',
                         'publication_kind': 'news agency',
                         'special_interest': 'yes',
                         'topical_focus': 'society',
                         'publication_cycle': 'multiple times per week',
                         'publication_cycle_weekday': ['1', '2', '3'],
                         'geographic_scope': 'national',
                         'countries': self.germany_uid,
                         'languages': self.lang_german,
                         'contains_ads': 'yes',
                         'publishes_org': ['New Media'],
                         'audience_size|count': '1234444',
                         'audience_size|unit': 'likes',
                         'party_affiliated': 'no'}
        
        with self.client:
            response = self.client.post(
                '/login', data={'email': 'reviewer@opted.eu', 'password': 'reviewer123'})
            self.assertEqual(current_user.display_name, 'Reviewer')

            with self.app.app_context():
                sanitizer = Sanitizer(mock_facebook, dgraph_type=NewsSource)
                self.assertEqual(type(sanitizer.set_nquads), str)
                self.assertIn('<_unique_name> "newssource_germany_somesource_facebook"', sanitizer.set_nquads)
                mock_facebook['geographic_scope'] = 'NA'
                self.assertRaises(InventoryValidationError, Sanitizer, mock_facebook, dgraph_type=NewsSource)

            self.client.get('/logout')

    def test_newscientificpublication(self):
        sample_data =  {
                        "authors": ["A4356501006", "A261564576", "A4356539172"],
                        "conditions_of_access": "free",
                        "countries": [self.spain_uid],
                        "date_published": "2015",
                        "description": "Data set analysing the sentiment of 2,704,523 tweets referring to Spanish politicians and parties between December 3rd, 2014 and January 12th, 2005.",
                        "dgraph.type": ["Entry", "Dataset"],
                        "doi": "10.1177/0165551515598926",
                        "url": "https://doi.org/10.1177/0165551515598926",
                        "file_formats": [self.fileformat_csv],
                        "fulltext_available": True,
                        "geographic_scope": "national",
                        "languages": [self.lang_spanish],
                        "title": "The megaphone of the people? Spanish SentiStrength for real-time analysis of political tweets",
                        "temporal_coverage_end": "2015-01-12",
                        "temporal_coverage_start": "2014-12-03",
                    }
        
        with self.client:
            response = self.client.post(
                '/login', data={'email': 'reviewer@opted.eu', 'password': 'reviewer123'})
            self.assertEqual(current_user.display_name, 'Reviewer')

            with self.app.app_context():
                sanitizer = Sanitizer(sample_data, dgraph_type=ScientificPublication)
                self.assertEqual(type(sanitizer.set_nquads), str)
                self.assertEqual(sanitizer.entry['_unique_name'], "mike_thelwall_et_al_2015_the_megaphone_of_the_people")

            self.client.get('/logout')


if __name__ == "__main__":
    unittest.main(verbosity=2)
