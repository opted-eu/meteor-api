# Ugly hack to allow absolute import from the root folder
# whatever its name is. Please forgive the heresy.

if __name__ == "__main__":
    from sys import path
    from os.path import dirname
    from flask import request, url_for
    from requests import HTTPError
    import unittest

    path.append(dirname(path[0]))
    from test_setup import BasicTestSetup
    from flaskinventory.external.openalex import OpenAlex
    from flaskinventory.external.orcid import ORCID
    from flaskinventory.external.doi import *
    import json
    with open('flaskinventory/config.json') as f:
        config = json.load(f)


class TestDOI(BasicTestSetup):

    manifesto_doi = '10.25522/manifesto.mpdssa.2020b'
    zenodo_doi = '10.5281/zenodo.3611246'
    arxiv_doi = '10.48550/arXiv.2001.08435'

    config_json = "config.json"

    def test_openalex(self):
        openalex = OpenAlex()
        self.assertRaises(HTTPError, openalex.resolve_doi, self.manifesto_doi)
        self.assertEqual(openalex.resolve_doi('10.14361/9783839463321')['openalex'], 'W4286475882')

    def test_crossref(self):
        self.assertRaises(HTTPError, crossref, self.manifesto_doi)

    def test_datacite(self):
        r = datacite(self.manifesto_doi)
        self.assertEqual(r['doi'].lower(), self.manifesto_doi.lower())

    def test_doi_org(self):
        self.assertEqual(doi_org(self.manifesto_doi)['doi'].lower(), self.manifesto_doi.lower())

    def test_orcid(self):
        orcid = ORCID(token=config['ORCID_ACCESS_TOKEN'])
        r = orcid.search_authors(given_name='Werner', family_name='Krause', affiliation='WZB Berlin Social Science Center')
        self.assertEqual(r['num-found'], 0)

        r = orcid.search_authors(given_name='Werner', family_name='Krause', doi="10.1080/17457289.2020.1866584")
        self.assertEqual(r['num-found'], 1)

        r = orcid.search_authors(given_name='Pola', family_name='Lehmann', affiliation='WZB Berlin Social Science Center')
        self.assertEqual(r['num-found'], 0)

        r = orcid.search_authors(given_name='Pola', family_name='Lehmann')
        self.assertEqual(r['num-found'], 1)

        r = orcid.resolve_author(given_name='Werner', family_name='Krause', affiliation='WZB Berlin Social Science Center')
        self.assertIsNone(r)
        r = orcid.resolve_author(given_name="Chung-hong", family_name="Chan", affiliation="University of Mannheim")
        self.assertEqual(r['orcid-id'], '0000-0002-6232-7530')

        r = orcid.resolve_author(given_name='Pola', family_name='Lehmann', affiliation='WZB Berlin Social Science Center')
        self.assertEqual(r['orcid-id'], '0000-0001-5267-3299')

    def test_zenodo(self):
        r = zenodo(self.zenodo_doi)

    def test_resolve_doi(self):
        r = resolve_doi(self.manifesto_doi)
        self.assertEqual(r['doi'], self.manifesto_doi)
        with self.app.app_context():
            resolved = resolve_authors(r['_authors_tmp'])
        self.assertEqual(resolved[0]['orcid'], '0000-0002-9348-706X')

        r = resolve_doi(self.zenodo_doi)
        with self.app.app_context():
            resolved = resolve_authors(r['_authors_tmp'])
        self.assertEqual(resolved[0]['orcid'], '0000-0002-8079-8694')

        r = resolve_doi(self.arxiv_doi)

        with self.app.app_context():
            resolved = resolve_authors(r['_authors_tmp'])

    def test_dgraph(self):
        from flaskinventory.external.dgraph import dgraph_resolve_doi
        with self.app.app_context():
            r = dgraph_resolve_doi("10.11587/IEGQ1B")


if __name__ == "__main__":
    unittest.main(verbosity=2)
