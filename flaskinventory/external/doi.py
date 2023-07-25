import requests
from typing import Union
from dateutil import parser as dateparser
from thefuzz import fuzz


def resolve(doi: str) -> Union[dict, bool]:
    # clean input string
    doi = doi.replace("https://doi.org/", "")
    doi = doi.replace("http://doi.org/", "")
    doi = doi.replace("doi.org/", "")


    api = 'https://api.crossref.org/works/'

    r = requests.get(api + doi)

    if r.status_code != 200:
        return False

    publication = r.json()

    if publication['status'] != 'ok':
        return False

    publication = publication['message']

    result = {'doi': doi}

    result['venue'] = publication.get('container-title')
    if isinstance(result['venue'], list):
        result['venue'] = result['venue'][0]
    result['title'] = publication.get('title')

    if isinstance(result['title'], list):
        result['title'] = result['title'][0]

    result['paper_kind'] = publication.get('type')

    if publication.get('created'):
        result['date_published'] = dateparser.parse(publication['created']['date-time'])

    if publication.get('link'):
        result['url'] = publication['link'][0]['URL']

    if publication.get('author'):
        authors = []
        for i, author in enumerate(publication['author']):
            author_name = f"{author.get('family', '')}, {author.get('given')}"
            # authors.append(Scalar(author_name, facets={'sequence': i}))

        result['authors'] = authors

    
    return result



def openalex_getauthorname(author_id: str) -> dict:
    api = "https://api.openalex.org/people/"
    r = requests.get(api + author_id, params={'mailto': "info@opted.eu"})
    j = r.json()
    result = {'openalex': author_id}
    if 'display_name' in j:
        result['name'] = j['display_name']
    if 'orcid' in j:
        result['orcid'] = j['orcid']
    if 'last_known_institution' in j:
        try:
            # prevent circular imports
            from flaskinventory.flaskdgraph.dgraph_types import Scalar
            institution = Scalar(j['last_known_institution']['display_name'],
                                facets={'openalex': j['last_known_institution']['id']})
            result['last_known_institution'] = institution
        except:
            pass
    return result

def openalex_getauthor_ids(query: str) -> list:
    api = "https://api.openalex.org/authors"

    query = query.replace(",", " ")
    query = query.replace(";", " ")

    params = {"search": query,
              'mailto': "info@opted.eu"}

    r = requests.get(api, params=params)

    r.raise_for_status()

    return r.json()['results']


def doi_org(doi: str) -> dict:
    api = "https://doi.org/"

    headers = {'Accept': "application/vnd.citationstyles.csl+json"}

    r = requests.get(api + doi, headers=headers)

    r.raise_for_status()

    j = r.json()

    result = {'doi': j['DOI'],
            'url': j['URL'],
            'title': j.get('title'),
            'description': j.get('abstract'),
            }

    try:
        result['date_published'] = j['issued']['date-parts'][0][0]
    except:
        pass

    result['_authors_fallback'] = []
    result['_authors_fallback|sequence'] = {}

    for i, author in enumerate(j['author']):
        try:
            name = author['family'] + ', ' + author['given']
            result['_authors_fallback'].append(name)
            result['_authors_fallback|sequence'][str(i)] = i 
        except KeyError:
            continue

    return result

def datacite(doi: str) -> dict:
    api = "https://api.datacite.org/dois/"

    r = requests.get(api + doi, params={'affiliation': 'true'})

    r.raise_for_status()

    j = r.json()['data']['attributes']

    result = {}

    for d in j['dates']:
        if d['dateType'] == 'Issued':
            result['date_published'] = d['date']

    for desc in j['descriptions']:
        if desc['descriptionType'] == 'Abstract':
            result['description'] = desc['description']
    
    result['doi'] = j['doi']
    result['date_published'] = dateparser.parse(j['published'])

    for t in j['titles']:
        if t['lang'] == 'en':
            result['title'] = t['title']

    result['url'] = j['url']

    for author in j['creators']:
        # print(author)
        pass

    return result

def orcid_search(name: str=None, family: str= None, given: str=None, affiliation: str = None) -> dict:
    """ Fallback to orcid as last ressort"""
    pass

if __name__ == '__main__':

    doi = '10.25522/manifesto.mpdssa.2020b'

    # result = datacite(doi)

    # print(result)

    affiliation = "WZB Berlin Social Science Center"

    author = "Zehnter, Lisa"

    candidates = openalex_getauthor_ids(author)

    print(candidates)
    
    for c in candidates:
        c['x_concepts'] = None
        score = 0
        if not 'relevance_score' in c:
            c['relevance_score'] = 1
        try:
            score = fuzz.partial_token_sort_ratio(c['last_known_institution']['display_name'], affiliation)
            c['institution_match'] = score
            c['overall_score'] = c['relevance_score'] * score
            if c['orcid']:
                c['overall_score'] = c['overall_score'] * 2
        except:
            c['overall_score'] = 0

    from pprint import pprint

    pprint(candidates)

    # print(sorted(candidates, key=lambda x: x['overall_score'], reverse=True)[0])