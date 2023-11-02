# Ugly hack to allow absolute import from the root folder
# whatever its name is. Please forgive the heresy.

from sys import path
from os.path import dirname
from requests import HTTPError
import unittest

path.append(dirname(path[0]))
from test_setup import BasicTestSetup
from meteor.external.openalex import OpenAlex
from meteor.external.orcid import ORCID
from meteor.external.doi import *
from meteor.external.cran import *
import json
with open('meteor/config.json') as f:
    config = json.load(f)


class TestDOI(BasicTestSetup):

    manifesto_doi = '10.25522/manifesto.mpdssa.2020b'
    zenodo_doi = '10.5281/zenodo.3611246'
    zenodo_doi2 = '10.5281/ZENODO.8381573'
    arxiv_doi = '10.48550/arXiv.2001.08435'
    arxiv_link = "https://arxiv.org/abs/1103.2903"
    arxiv_versioned = "https://arxiv.org/abs/1103.2903v1"
    aussda_doi = 'https://doi.org/10.11587/XJZPCU'
    japanese_doi = "10.11218/ojjams.19.101"

    config_json = "config.json"

    def test_openalex(self):
        openalex = OpenAlex()
        self.assertRaises(HTTPError, openalex.resolve_doi, self.manifesto_doi)
        self.assertEqual(openalex.resolve_doi(
            '10.14361/9783839463321')['openalex'], 'W4286475882') # Die Ampelkoalition, Lehmann, 2022

    def test_crossref(self):
        self.assertRaises(HTTPError, crossref, self.manifesto_doi)

    def test_datacite(self):
        r = datacite(self.manifesto_doi)
        self.assertEqual(r['doi'].lower(), self.manifesto_doi.lower())

    def test_doi_org(self):
        self.assertEqual(doi_org(self.manifesto_doi)[
                         'doi'].lower(), self.manifesto_doi.lower())

    def test_orcid(self):
        orcid = ORCID(token=config['ORCID_ACCESS_TOKEN'])
        r = orcid.search_authors(given_name='Werner', family_name='Krause',
                                 affiliation='WZB Berlin Social Science Center')
        self.assertEqual(r['num-found'], 1)

        r = orcid.search_authors(
            given_name='Werner', family_name='Krause', doi="10.1080/17457289.2020.1866584")
        self.assertEqual(r['num-found'], 1)

        r = orcid.search_authors(given_name='Pola', family_name='Lehmann',
                                 affiliation='WZB Berlin Social Science Center')
        self.assertEqual(r['num-found'], 0)

        r = orcid.search_authors(given_name='Pola', family_name='Lehmann')
        self.assertEqual(r['num-found'], 1)

        r = orcid.resolve_author(given_name='Werner', family_name='Krause',
                                 affiliation='WZB Berlin Social Science Center')
        
        self.assertEqual(r['orcid-id'], '0000-0002-5069-7964')

        r = orcid.resolve_author(
            given_name="Chung-hong", family_name="Chan", affiliation="University of Mannheim")
        self.assertEqual(r['orcid-id'], '0000-0002-6232-7530')

        r = orcid.resolve_author(given_name='Pola', family_name='Lehmann',
                                 affiliation='WZB Berlin Social Science Center')
        self.assertEqual(r['orcid-id'], '0000-0001-5267-3299')

        r = orcid.get_author('0000-0002-0387-5377')
        self.assertEqual(r['name'], 'Richard McElreath')

    def test_zenodo(self):
        r = zenodo(self.zenodo_doi)
        r = zenodo(self.zenodo_doi2)

    def test_jalc(self):
        r = jalc(self.japanese_doi.upper())

    def test_resolve_doi(self):

        r = resolve_doi(self.manifesto_doi)
        self.assertEqual(r['doi'], self.manifesto_doi.upper())
        with self.app.app_context():
            resolved = resolve_authors(r['_authors_tmp'])
        self.assertEqual(resolved[0]['orcid'], '0000-0002-9348-706X')

        r = resolve_doi(self.zenodo_doi)
        with self.app.app_context():
            resolved = resolve_authors(r['_authors_tmp'])
        self.assertEqual(resolved[0]['orcid'], '0000-0002-8079-8694')

        r = resolve_doi(self.zenodo_doi2)

        r = resolve_doi(self.arxiv_doi)

        with self.app.app_context():
            resolved = resolve_authors(r['_authors_tmp'])

        r = resolve_doi(self.aussda_doi)
        with self.app.app_context():
            resolved = resolve_authors(r['_authors_tmp'])

        r = resolve_doi(self.japanese_doi)
        self.assertEqual(
            r['title'], "Quantitative Analysis of Textual Data : Differentiation and Coordination of Two Approaches")

    def test_arxiv(self):
        r = resolve_doi(self.arxiv_link)
        # ANEW Sentiment dict
        self.assertEqual(r['url'], 'https://arxiv.org/abs/1103.2903')
        r = resolve_doi(self.arxiv_versioned)
        self.assertEqual(r['url'], 'https://arxiv.org/abs/1103.2903')

        with self.app.app_context():
            authors = resolve_authors(r['_authors_tmp'])

        self.assertEqual(authors[0]['orcid'], '0000-0001-6128-3356')

    def test_dgraph(self):
        from meteor.external.dgraph import dgraph_resolve_doi
        with self.app.app_context():
            r = dgraph_resolve_doi("10.11587/IEGQ1B") # REMINDER dataset

    def test_cran(self):
        r = cran("grafzahl")
        self.assertEqual(r['_authors_tmp'][0]['orcid'], '0000-0002-6232-7530')

        r = cran("newsmap")
        with self.app.app_context():
            authors = resolve_authors(r['_authors_tmp'])

        self.assertIsNone(authors[0].get('orcid'))

    def test_affiliations(self):
        with self.app.app_context():
            r = get_author_affiliations({'orcid': '0000-0002-0866-064X'})
        self.assertEqual(len(r), 1)

        with self.app.app_context():
            r = get_author_affiliations({'orcid': '0000-0002-2968-2557'})

        self.assertEqual(len(r), 2)

        with self.app.app_context():
            r = get_author_affiliations({'orcid': '0000-0002-1485-4264'})

        self.assertEqual(len(r), 1)

        with self.app.app_context():
            r = get_author_affiliations({'orcid': '0000-0002-4559-2439'})

        self.assertEqual(len(r), 2)

        with self.app.app_context():
            r = get_author_affiliations({'openalex': 'A5054422803'})
        self.assertEqual(len(r), 1)

        with self.app.app_context():
            r = get_author_affiliations({'openalex': 'A5088108453'})
        self.assertEqual(len(r), 1)

        with self.app.app_context():
            r = get_author_affiliations({'openalex': 'A5004752671'})
        self.assertEqual(len(r), 1)

        with self.app.app_context():
            r = get_author_affiliations({'openalex': 'A5075267289'})
        self.assertEqual(len(r), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
