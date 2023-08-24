import requests
from thefuzz import fuzz

class OpenAlex:

    api = "https://api.openalex.org/"
    params = {'mailto': "info@opted.eu"}

    def __init__(self) -> None:
        pass

    def resolve_doi(self, doi: str) -> dict:
        r = requests.get(self.api + 'works/doi:' + doi, params=self.params)
        r.raise_for_status()
        j = r.json()

        result = {}

        try:
            result['url'] = j['primary_location']['landing_page_url']
        except:
            result['url'] = j['ids']['doi']

        result['doi'] = j['ids']['doi'].replace('https://doi.org/', '')
        result['openalex'] = j['ids']['openalex'].replace('https://openalex.org/', '')

        try:
            result['venue'] = j['primary_location']['source']['display_name'] 
        except:
            pass

        # result['name'] = j['title']
        result['title'] = j['title']
        result['paper_kind'] = j['type']
        result['date_published'] = str(j['publication_year'])
        result['_authors_tmp'] = []
        result['_authors_fallback'] = []
        result['_authors_fallback|sequence'] = {}

        for i, author in enumerate(j['authorships']):
            parsed_author = {'authors|sequence': i}
            parsed_author['openalex'] = author['author']['id'].replace('https://openalex.org/', '')
            parsed_author['name'] = author['author']['display_name']
            result['_authors_fallback'].append(author['author']['display_name'])
            result['_authors_fallback|sequence'][str(i)] = str(i)
            try:
                parsed_author['orcid'] = author['author']['orcid'].replace('https://orcid.org/', '')
            except:
                pass
            result['_authors_tmp'].append(parsed_author)

        try:
            result['description'] = j['abstract']
        except:
            try:
                result['description'] = ' '.join(list(j['abstract_inverted_index'].keys()))
            except:
                pass

        return result

    def get_author_name(self, author_id: str) -> dict:
        """ Retrieve the name of an author based on OpenAlex ID """
        r = requests.get(self.api + 'people/' + author_id, params=self.params)
        r.raise_for_status()
        j = r.json()
        result = {'openalex': author_id}
        if 'display_name' in j:
            result['name'] = j['display_name']
        if 'orcid' in j:
            result['orcid'] = j['orcid']
        if 'last_known_institution' in j:
            try:
                result['affiliations'] = j['last_known_institution']['display_name']
                result['affiliations|openalex'] = j['last_known_institution']['id']
            except:
                pass
        return result

    def get_author_ids(self, query: str) -> list:
        """ Search ID of an author based on their names """

        query = query.replace(",", " ")
        query = query.replace(";", " ")

        params = {"search": query
                  **self.params}

        r = requests.get(self.api + 'authors/', params=params)

        r.raise_for_status()

    def get_author_by_orcid(self, orcid: str) -> dict:
        """ Get OpenAlex Author information by providing an ORCID ID """

        r = requests.get(self.api + 'authors/orcid:' + orcid, params=self.params)
        r.raise_for_status()

        return r.json()