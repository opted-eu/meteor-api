
#  Ugly hack to allow absolute import from the root folder
# whatever its name is. Please forgive the heresy.

from meteor.users.dgraph import AnonymousUser
from meteor.errors import InventoryValidationError, InventoryPermissionError
from meteor.api.sanitizer import Sanitizer
from meteor.main.model import Organization, NewsSource, User, ScientificPublication, LearningMaterial
from meteor.flaskdgraph.dgraph_types import Scalar
import datetime
import copy
from unittest.mock import patch
import unittest
from meteor import dgraph
from test_setup import BasicTestSetup
from sys import path
from os.path import dirname

path.append(dirname(path[0]))


def mock_wikidata(*args):
    return {'wikidata_id': "Q49653",
            'alternate_names': [],
            'date_founded': datetime.datetime(1950, 6, 5, 0, 0),
            'address': 'Stuttgart'}


@patch('meteor.main.sanitizer.get_wikidata', mock_wikidata)
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
                                    '_date_created', '_unique_name', 'name', 'alternate_names']

        self.mock2_solution_keys = ['dgraph.type', 'uid', '_added_by', 'entry_review_status',
                                    '_date_created', '_unique_name', 'name', 'alternate_names']

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

        with self.app.app_context():
            sanitizer = Sanitizer(self.mock_data1, self.contributor)
            self.assertEqual(sanitizer.is_upsert, False)
            self.assertCountEqual(
                list(sanitizer.entry.keys()), self.mock1_solution_keys)
            self.assertEqual(sanitizer.entry['_unique_name'], '_test')
            self.assertEqual(type(sanitizer.entry['alternate_names']), list)

            sanitizer = Sanitizer(self.mock_data2, self.contributor)
            self.assertEqual(sanitizer.is_upsert, False)
            self.assertCountEqual(
                list(sanitizer.entry.keys()), self.mock2_solution_keys)
            self.assertEqual(sanitizer.entry['_unique_name'], '_testsomethin')
            self.assertEqual(type(sanitizer.entry['alternate_names']), list)
            self.assertEqual(len(sanitizer.entry['alternate_names']), 2)

            self.assertRaises(TypeError, Sanitizer, [1, 2, 3])

            with self.assertRaises(InventoryPermissionError):
                Sanitizer(self.mock_data2, AnonymousUser())

    def test_list_facets(self):
        mock_data = {
            'name': 'Test',
            'alternate_names': 'Jay Jay,Jules,JB',
            'Jay Jay@kind': 'first',
            'Jules@kind': 'official',
            'JB@kind': 'CS-GO'
        }

        with self.app.app_context():
            sanitizer = Sanitizer(mock_data, self.contributor)
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

        with self.app.app_context():
            # no UID
            edit_entry = {
                'entry_review_status': 'accepted', **self.mock_data1}
            with self.assertRaises(InventoryValidationError):
                Sanitizer.edit(edit_entry, self.contributor)
            with self.assertRaises(InventoryValidationError):
                Sanitizer.edit(self.mock_data2, self.contributor)

            wrong_uid = {'uid': '0xfffffffff', **edit_entry}
            # wrong uid
            with self.assertRaises(InventoryValidationError):
                Sanitizer.edit(wrong_uid, self.contributor)

            wrong_user = {'uid': self.derstandard_mbh_uid, **edit_entry}
            # wrong permissions
            with self.assertRaises(InventoryPermissionError):
                Sanitizer.edit(wrong_user, self.contributor)

            correct = {'uid': self.derstandard_mbh_uid, **edit_entry}
            sanitizer = Sanitizer.edit(correct, self.reviewer)
            self.assertEqual(sanitizer.is_upsert, True)
            self.assertNotIn('dgraph.type', sanitizer.entry.keys())
            self.assertIn('_edited_by', sanitizer.entry.keys())
            self.assertCountEqual(
                sanitizer.overwrite[sanitizer.entry_uid], ['alternate_names'])

    def test_new_org(self):

        with self.app.app_context():
            sanitizer = Sanitizer(
                self.mock_organization,
                self.contributor,
                dgraph_type=Organization)
            self.assertEqual(sanitizer.is_upsert, False)
            self.assertCountEqual(sanitizer.entry['dgraph.type'], [
                'Entry', 'Organization'])
            self.assertEqual(
                sanitizer.entry['entry_review_status'], 'pending')
            self.assertEqual(
                sanitizer.entry['_unique_name'], 'organization_de_deutschebank')
            self.assertIsNotNone(sanitizer.set_nquads)
            self.assertIsNone(sanitizer.delete_nquads)
            # WikiDataID for Deutsche Bank
            self.assertEqual(str(sanitizer.entry['wikidata_id']), 'Q66048')
            self.assertIn('employees', sanitizer.entry.keys())

            mock_org = copy.deepcopy(self.mock_organization)
            mock_org.pop('address')
            sanitizer = Sanitizer(
                mock_org,
                self.contributor,
                dgraph_type=Organization)
            self.assertEqual(sanitizer.is_upsert, False)
            self.assertCountEqual(sanitizer.entry['dgraph.type'], [
                'Entry', 'Organization'])
            self.assertEqual(
                sanitizer.entry['entry_review_status'], 'pending')
            self.assertEqual(
                sanitizer.entry['_unique_name'], 'organization_de_deutschebank')
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

        with self.app.app_context():
            sanitizer = Sanitizer.edit(
                mock_org_edit,
                self.reviewer,
                dgraph_type=Organization)
            self.assertCountEqual(
                sanitizer.overwrite[sanitizer.entry['uid']], overwrite_keys)
            self.assertEqual(len(sanitizer.entry['publishes']), 5)

            mock_org_edit['uid'] = self.derstandard_mbh_uid
            mock_org_edit['publishes'] = " ,".join(
                [self.derstandard_print, self.derstandard_facebook, self.derstandard_instagram, self.derstandard_twitter])
            mock_org_edit['country'] = self.germany_uid
            mock_org_edit['date_founded'] = '2010'
            sanitizer = Sanitizer.edit(
                mock_org_edit,
                self.reviewer,
                dgraph_type=Organization)
            self.assertEqual(len(sanitizer.entry['publishes']), 4)
            # self.assertEqual(type(sanitizer.entry['date_founded']), datetime)

    def test_draft_source(self):

        # this is a raw dgraph mutation
        new_draft = {'uid': '_:newdraft',
                     'dgraph.type': 'NewsSource',
                     'channel': {'uid': self.channel_print},
                     'channel_unique_name': 'print',
                     'name': 'Schwäbische Post',
                     '_unique_name': 'newssource_germany_schwaebischepost_print',
                     'publication_kind': 'newspaper',
                     'geographic_scope': 'subnational',
                     'countries': {'uid': self.germany_uid},
                     'languages': {'uid': self.lang_german},
                     'entry_review_status': 'draft',
                     '_added_by': {'uid': self.reviewer.uid}}

        # create a mock draft entry

        with self.app.app_context():
            res = dgraph.mutation(new_draft)
            # get the UID of the mock draft
            uid = res.uids['newdraft']

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

        with self.app.app_context():
            # test if random user can edit
            with self.assertRaises(InventoryPermissionError):
                sanitizer = Sanitizer.edit(edited_draft,
                                           self.contributor,
                                           dgraph_type=NewsSource)

            # test if owner can edit
            sanitizer = Sanitizer.edit(edited_draft,
                                       self.reviewer,
                                       dgraph_type=NewsSource)
            self.assertIn("<_edited_by>", sanitizer.set_nquads)
            self.assertIn(
                '<_unique_name> "newssource_germany_schwabischepost_print"', sanitizer.set_nquads)

            # delete draft after test
            res = dgraph.delete({'uid': uid})

    def test_newscientificpublication(self):
        sample_data = {
            "authors": ["A5039380414", "A5034823602", "A5055204791"],
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

        with self.app.app_context():
            sanitizer = Sanitizer(sample_data,
                                  self.reviewer,
                                  dgraph_type=ScientificPublication)
            self.assertEqual(type(sanitizer.set_nquads), str)
            self.assertEqual(
                sanitizer.entry['_unique_name'], "david_vilares_et_al_2015_the_megaphone_of_the_people")

            # test empty orderedlistrelationship
            # authors are required, so empty list should raise an error
            sample_data['authors'] = []
            with self.assertRaises(InventoryValidationError):
                Sanitizer(sample_data,
                          self.reviewer,
                          dgraph_type=ScientificPublication)

    def test_editlearningmaterial(self):
        with self.app.app_context():
            uid = dgraph.get_uid(
                "_unique_name", "learningmaterial_statisticalrethinking")

        sample_data = {
            "uid": uid,
            "authors": ["A5066935756", "A5084520588"],
            "programming_languages": [self.programming_rust]
        }

        with self.app.app_context():
            sanitizer = Sanitizer.edit(sample_data,
                                       self.reviewer,
                                       dgraph_type=LearningMaterial)
            self.assertEqual(type(sanitizer.set_nquads), str)
            self.assertCountEqual(sanitizer.overwrite[sanitizer.entry_uid], [
                                  "authors", "programming_languages"])
            self.assertCountEqual(sanitizer.entry.keys(), [
                                  "uid", "authors", "programming_languages", "_edited_by"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
