import requests
from typing import Union
from dateutil import parser as dateparser
from thefuzz import fuzz

def clean_doi(doi: str) -> str:
    """ strips unwanted stuff from DOI strings """
    doi = doi.replace("https://doi.org/", "")
    doi = doi.replace("http://doi.org/", "")
    doi = doi.replace("doi.org/", "")
    return doi


def crossref(doi: str) -> Union[dict, bool]:

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

def zenodo(doi: str) -> dict:
    pass

def orcid_search(name: str=None, family: str= None, given: str=None, affiliation: str = None) -> dict:
    """ Fallback to orcid as last ressort"""
    pass

def resolve_doi(doi: str) -> dict:
    """ 
        query a series of APIs and return clean data 
        Tries in this order
        1. OpenAlex (most convenient)
        2. Crossref
        3. Datacite
        4. DOI.org

        - Zenodo DOIs are handled by zenodo directly
        - Tries to get canonical Author IDs
    """
    doi = clean_doi(doi)

    if 'zenodo' in doi.lower():
        result = zenodo(doi)

if __name__ == '__main__':

    doi = '10.25522/manifesto.mpdssa.2020b'
    import json
    with open('flaskinventory/config.json') as f:
        config = json.load(f)

    headers = {}

    api = "https://pub.orcid.org/"

    author = "Krause, Werner"

    headers = {
            "Authorization type": "Bearer",
            "Access token": config['ORCID_ACCESS_TOKEN'],
            "Content-type": "application/json",
            "scope": "/read-public"
            }

    r = requests.get(api + 'v3.0/expanded-search/', params={'q': 'given-and-family-names:' + author}, headers=headers)
    # r = requests.get(api + 'v3.0/expanded-search/', params={'q': 'digital-object-ids:"' + doi + '"'}, headers=headers)

    print(r.json())
    print(r.json()['expanded-result'][:5])

    # take top 10 results
    candidates = r.json()['expanded-result'][:10]
    for c in candidates:
        name = c['given-names'] + ' ' + c['family-names']
        score = fuzz.partial_token_sort_ratio(name, author)
        c['name'] = name
        c['score'] = score
        # print(name, c['orcid-id'], score)

    highest_score = max(candidates, key=lambda x: x['score'])
    print('highest', highest_score)

    # check if there are other candidates with same score
    other_candidates = [c for c in candidates if c['score'] == highest_score]
    if len(other_candidates) > 0:
        print(other_candidates) 

    # result = datacite(doi)

    # print(result)

    # affiliation = "WZB Berlin Social Science Center"


    # candidates = openalex_getauthor_ids(author)

    # # print(candidates)
    
    # for c in candidates:
    #     c['x_concepts'] = None
    #     score = 0
    #     if not 'relevance_score' in c:
    #         c['relevance_score'] = 1
    #     try:
    #         score = fuzz.partial_token_sort_ratio(c['last_known_institution']['display_name'], affiliation)
    #         c['institution_match'] = score
    #         c['overall_score'] = c['relevance_score'] * score
    #         if c['orcid']:
    #             c['overall_score'] = c['overall_score'] * 2
    #     except:
    #         c['overall_score'] = 0

    # from pprint import pprint

    # pprint(candidates)

    # print(sorted(candidates, key=lambda x: x['overall_score'], reverse=True)[0])