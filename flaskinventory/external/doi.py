import requests
import typing
from dateutil import parser as dateparser
import datetime
import lxml
from flaskinventory.external.openalex import OpenAlex
from flaskinventory.external.orcid import ORCID
import logging

logger = logging.getLogger(__name__)

ARXIV_PREFIX = "10.48550/arxiv."

def clean_doi(doi: str) -> str:
    """ strips unwanted stuff from DOI strings """
    doi = doi.replace("https://doi.org/", "")
    doi = doi.replace("http://doi.org/", "")
    doi = doi.replace("doi.org/", "")
    return doi


def clean_orcid(orcid: str) -> str:
    """ strips unwanted stuff from ORCID strings """
    orcid = orcid.replace("https://orcid.org/", "")
    orcid = orcid.replace("http://orcid.org/", "")
    orcid = orcid.replace("orcid.org/", "")
    return orcid


def crossref(doi: str) -> dict:

    api = 'https://api.crossref.org/works/'

    r = requests.get(api + doi)
    r.raise_for_status()

    publication = r.json()

    if publication['status'] != 'ok':
        raise requests.exceptions.HTTPError(f'Publication with DOI <{doi}> was not found! {publication["status"]}')

    publication = publication['message']
    result = {'doi': doi}

    result['venue'] = publication.get('container-title')
    if isinstance(result['venue'], list):
        result['venue'] = result['venue'][0]

    result['title'] = publication.get('title')

    if isinstance(result['title'], list):
        result['title'] = result['title'][0]

    result['paper_kind'] = publication.get('type')

    try:
        result['date_published'] = dateparser.parse(publication['created']['date-time'])
    except:
        pass

    try:
        result['url'] = publication['link'][0]['URL']
    except:
        pass

    try:
        result['description'] = publication['abstract']
    except:
        pass

    result['_authors_fallback'] = []
    result['_authors_fallback|sequence'] = {}
    result['_authors_tmp'] = [] 
    try:
        authors = []
        for i, author in enumerate(publication['author']):
            author_name = f"{author.get('family', '')}, {author.get('given')}"
            result['_authors_fallback'].append(author_name)
            result['_authors_fallback|sequence'][str(i)] = i
            parsed_author = {'authors|sequence': i}
            try:
                parsed_author['given_name'] = author['given']
            except:
                pass
            try:
                parsed_author['family_name'] = author['family']
            except:
                pass
            try:
                parsed_author['orcid'] = author['ORCID']
            except:
                pass
            try:
                parsed_author['affiliation'] = author['affiliation']['name']
            except:
                pass
            result['_authors_tmp'].append(parsed_author)

        result['authors'] = authors
    except:
        pass

    
    return result


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

    try:
        for t in j['titles']:
            if t['lang'] == 'en':
                result['title'] = t['title']
    except KeyError:
        result['title'] = j['titles'][0]['title']

    result['url'] = j['url']

    result['_authors_fallback'] = []
    result['_authors_fallback|sequence'] = {}
    result['_authors_tmp'] = []

    for i, author in enumerate(j['creators']):
        result['_authors_fallback'].append(author['name'])
        result['_authors_fallback|sequence'][str(i)] = i
        if author['nameType'].lower() == 'organizational':
            continue
        parsed_author = {'authors|sequence': i}
        try:
            parsed_author['given_name'] = author['givenName']
            parsed_author['family_name'] = author['familyName']
        except:
            parsed_author['name'] = author['name']
        try:
            for identifier in author['nameIdentifiers']:
                if identifier['nameIdentifierScheme'].lower() == 'orcid':
                    parsed_author['orcid'] = identifier['nameIdentifier']
        except:
            pass
        try:
            parsed_author['affiliation'] = author['affiliation']['name']
        except:
            pass
        result['_authors_tmp'].append(parsed_author)


    return result

def zenodo(doi: str) -> dict:
    """ 
        Get DOI meta data from Zenodo.org 
        Returns Authors as fallback (list of strings)
            and also as _authors_tmp (list of dicts)    
    """
    api = "https://zenodo.org/api/records"

    params = f'q=doi:"{doi}"'
    r = requests.get(api, params=params)

    r.raise_for_status()

    j = r.json()['hits']
    if j['total'] == 0:
        raise requests.HTTPError(f'No records found with doi <{doi}>')
    
    hit = j['hits'][0]

    result = {'doi': hit['doi'],
              'url': hit['links']['html']}

    result['_authors_fallback'] = []
    result['_authors_fallback|sequence'] = {}
    result['_authors_tmp'] = []
    for i, author in enumerate(hit['metadata']['creators']):
        result['_authors_fallback'].append(author['name'])
        result['_authors_fallback|sequence'][str(i)] = i
        author['authors|sequence'] = i
        result['_authors_tmp'].append(author)

    try:
        description = lxml.html.fromstring(hit['metadata']['description']).text_content().strip()
        result['description'] = description
    except:
        pass

    # One could here parse the language tag and get the corresponding data entry from DGraph...

    try:
        result['license'] = hit['metadata']['license']['id']
    except:
        pass

    try:
        result['date_publised'] = hit['metadata']['publication_date']
    except:
        pass

    try:
        result['date_modified'] = datetime.datetime.fromisoformat(hit['updated'])
    except:
        pass

    try:
        result['title'] = hit['metadata']['title']
    except:
        pass

    return result


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
        4. DOI.org (has least useful metainfo)

        - Zenodo DOIs are handled by zenodo directly
    """
    doi = clean_doi(doi)
    logger.debug(f'Got DOI <{doi}>')

    if 'zenodo' in doi.lower():
        logger.debug('Using Zenodo')
        return zenodo(doi)

    try:
        openalex = OpenAlex()
        return openalex.resolve_doi(doi)
    except requests.HTTPError:
        logger.debug(f'Could not resolve <{doi}> at openalex')
        pass

    try:
        return crossref(doi)
    except requests.HTTPError:
        logger.debug(f'Could not resolve <{doi}> at crossref')
        pass

    try:
        return datacite(doi)
    except requests.HTTPError:
        logger.debug(f'Could not resolve <{doi}> at datacite')
        pass

def resolve_authors(authors_tmp: typing.List[dict]) -> typing.List[dict]:
    """ 
        Try to get canonical IDs for authors 
        1. Check if there is an ORCID ID provided and try to get OpenAlex ID
        2. Try to query ORCID API to find author candidates
            Only adds ORCID ID to cases that are very sure
    """
    openalex = OpenAlex()
    orcid = ORCID()
    for author in authors_tmp:
        if 'openalex' in author:
            continue

        if 'orcid' in author:
            orcid_id = clean_orcid(author['orcid'])
            author['orcid'] = orcid_id
            try:
                openalex_id = openalex.get_author_by_orcid(orcid_id)['id'].replace('https://openalex.org/', '')
                author['openalex'] = openalex_id
            except requests.HTTPError:
                pass
        else:
            try:
                orcid_details = orcid.resolve_author(name=author.get('name'),
                                                    family_name=author.get('family_name'),
                                                    given_name=author.get('given_name'),
                                                    affiliation=author.get('affiliation'))
                if orcid_details:
                    author['orcid'] = orcid_details['orcid-id']
                    try:
                        openalex_id = openalex.get_author_by_orcid(orcid_details['orcid-id'])['id'].replace('https://openalex.org/', '')
                        author['openalex'] = openalex_id
                    except requests.HTTPError:
                        pass
            except requests.HTTPError:
                pass
    return authors_tmp