# Collection of helpers for migrating / importing data

import sys
from os.path import dirname
sys.path.append(dirname(sys.path[0]))

import re
import typing

import json
from pathlib import Path
import requests
import pydgraph
import numpy as np

client_stub = pydgraph.DgraphClientStub('localhost:9080')
client = pydgraph.DgraphClient(client_stub)

""" Get UID of Admin User """

query_string = '{ q(func: eq(email, "wp3@opted.eu")) { uid } }'


res = client.txn().query(query_string)

j = json.loads(res.json)['q']

ADMIN_UID = j[0]['uid']

""" Helpers for Retrieving DOI related stuff """

p = Path.cwd()


_publication_cache_file = p / "data" / "publication_cache.json"

try:
    with open(_publication_cache_file) as f:
        PUBLICATION_CACHE = json.load(f)
except:
    PUBLICATION_CACHE = {}


class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime.datetime):
            return o.isoformat()

        return json.JSONEncoder.default(self, o)


def save_publication_cache():
    with open(_publication_cache_file, "w") as f:
        json.dump(PUBLICATION_CACHE, f, cls=DateTimeEncoder) 


from meteor.external.doi import resolve_doi, resolve_authors, clean_doi
from meteor.external.cran import cran
import datetime
import secrets
from slugify import slugify
from copy import deepcopy

author_template = {'_date_created': datetime.datetime.now().isoformat(),
                    '_added_by': {
                        'uid': ADMIN_UID,
                        '_added_by|timestamp': datetime.datetime.now().isoformat()
                    },
                    'dgraph.type': ['Entry', 'Author']
                    }

with open(p / 'meteor' / 'config.json') as f:
    CONFIG = json.load(f)


def dgraph_check_author(orcid: str = None, openalex: typing.Union[str, list] = None) -> dict:
    dgraph_author_query = """query checkAuthor ( $orcid: string, $openalex: string ) {
        q(func: type(Author)) @filter(eq(orcid, $orcid) OR eq(openalex, $openalex)) {
            uid openalex orcid
            }
        }
    """
    if not isinstance(openalex, list):
        openalex = [openalex]

    for o in openalex:
        res = client.txn(read_only=True).query(dgraph_author_query, variables={'$orcid': str(orcid), '$openalex': str(o)})
        j = json.loads(res.json)
        if len(j['q']) > 0:
            return j['q'][0]
    return None

def process_authors(authors_tmp: list, cache, entry_review_status='accepted') -> list:
    authors = resolve_authors(authors_tmp, orcid_token=CONFIG['ORCID_ACCESS_TOKEN'])
    authors_new = []
    for author in authors:
        # First we check if we have an ORCID
        orcid = author.get('orcid')
        openalex = author.get('openalex')
        if openalex:
            if not isinstance(openalex, list):
                openalex = [openalex]
        # Then we check whether the author is already in DGraph
        uid = dgraph_check_author(orcid=orcid, openalex=openalex)
        if uid:
            author_details = {'uid': uid['uid'],
                              'authors|sequence': author['authors|sequence']}
            if orcid:
                author_details['orcid'] = orcid
            if openalex:
                author_details['openalex'] = openalex
            authors_new.append(author_details)
            continue
        # build author name
        if 'family_name' in author:
            a_name = author['given_name'] + " " + author['family_name']
        else:
            a_name = author['name']
        # And whether we've seen the ORCID before
        if orcid and orcid in cache:
            author_details = cache[orcid]
            author_details['authors|sequence'] = author['authors|sequence']
            # we want the openalex IDs to point to ORCIDs
            # openalex are less reliable and there are many duplicates
            if openalex and 'openalex' in author_details:
                try:
                    author_details['openalex'] += openalex
                    author_details['openalex'] = list(set(author_details['openalex']))
                except:
                    openalex.append(author_details['openalex'])
                    author_details['openalex'] = list(set(openalex))
                for o in openalex:
                    cache[o] = orcid
            elif openalex and 'openalex' not in author_details:
                for o in openalex:
                    cache[o] = orcid
            author_details.update(author_template)
            # update caache
            _copied_author = deepcopy(author_details)
            _ = _copied_author.pop('authors|sequence')
            cache[orcid] = _copied_author
        # If the ORCID is new, then we create a new author
        elif orcid:
            author_details = {**author,
                                'uid': '_:' + orcid.replace('-', ''),
                                '_unique_name': 'author_' + orcid.replace('-', ''),
                                'entry_review_status': entry_review_status,
                                **author_template
                             }
            author_details['name'] = a_name
            _copied_author = deepcopy(author_details)
            _ = _copied_author.pop('authors|sequence')
            cache[orcid] = _copied_author
        # If we only have an OpenAlex ID, we use this instead
        elif openalex and len(set(openalex) & set(cache.keys())) > 1:
            # get the orcid via the openalex
            author_details = cache[cache[openalex[0]]]
            author_details = {**author, **author_template}
        elif openalex:
            openalex = openalex[0]
            author_details = {**author,
                                'uid': '_:' + openalex.replace('-', '').lower(),
                                '_unique_name': 'author_' + openalex.replace('-', '').lower(),
                                'entry_review_status': entry_review_status,
                                **author_template
                             }        
        # if there is no other way, we just generate the author as new entry
        else:
            author_details = {**author,
                              'name': a_name,
                                'uid': '_:' + slugify(secrets.token_urlsafe(16), separator="_"),
                                '_unique_name': 'author_' + slugify(a_name, separator="_") + slugify(secrets.token_urlsafe(6), separator="_"),
                                'entry_review_status': entry_review_status,
                                **author_template
                             }
        authors_new.append(author_details)
    return authors_new

DOI_PATTERN = re.compile(r"10.\d{4,9}/[-._;()/:A-Z0-9]+")

def process_doi(doi, cache, entry_review_status='accepted'):
    doi = clean_doi(doi)
    try:
        doi = DOI_PATTERN.search(doi)[0]
    except:
        raise ValueError
    if doi in cache:
        publication = deepcopy(cache[doi])
    else:
        publication = resolve_doi(doi)
        cache[doi] = deepcopy(publication)
    authors_tmp = publication.pop('_authors_tmp')
    authors = process_authors(authors_tmp, cache, entry_review_status=entry_review_status)

    output = {**publication,
              '_date_modified': datetime.datetime.now().isoformat(),
              'entry_review_status': entry_review_status,
              'doi': doi}
    
    output['authors'] = authors
    return output

def process_cran(pkg: str, cache, entry_review_status='accepted') -> list:
    package_meta = cran(pkg)
    authors_tmp = package_meta.pop('_authors_tmp')
    authors = process_authors(authors_tmp, cache, entry_review_status=entry_review_status)
    return authors


""" Wikidata Helpers """


wikidata_cache_file = p / "data" / "wikidata_cache.json"
WIKIDATA_CACHE = {}
try:
    with open(wikidata_cache_file) as f:
        WIKIDATA_CACHE = json.load(f)
except:
    WIKIDATA_CACHE = {}


def save_wikidata_cache():
    with open(wikidata_cache_file, "w") as f:
        json.dump(WIKIDATA_CACHE, f) 


""" Misc """


def remove_none(l: list):
    # helper to remove None and NA values from lists
    try:
        l.remove(None)
    except:
        pass
    try:
        l.remove(np.nan)
    except:
        pass
    try:
        l.remove('')
    except:
        pass


def safe_clean_doi(x):
    try:
        return clean_doi(x)
    except:
        return x
    










""" Author deduplication """

def get_duplicated_authors() -> list():
    duplicate_check_query = """{
        q(func: type(Author)) @groupby(name) {
            number: count(uid)
            }
        }
    """

    res = client.txn(read_only=True).query(duplicate_check_query)

    check = json.loads(res.json)['q'][0]['@groupby']

    duplicated_names = list(filter(lambda x: x['number'] > 1, check))
    return [n['name'] for n in duplicated_names]

def deduplicate_author(name: str) -> None:
    query_string = """query duplicated($name: string) {
    q(func: type(Author)) @filter(eq(name, $name)) {
        uid expand(_all_) 
        ~authors @facets { uid }
        }
    }"""

    res = client.txn(read_only=True).query(query_string, variables={'$name': name})
    authors = json.loads(res.json)['q']

    try:
        orcid = list(filter(lambda x: 'orcid' in x, authors))[0]['orcid']
    except:
        orcid = None

    # find entry with richest information
    richest = max([len(d.keys()) for d in authors])
    main_author = list(filter(lambda x: len(x.keys()) == richest, authors))[0]
    authors.remove(main_author)

    affiliations = []
    openalex = []
    for author in authors:
        try:
            a = author.pop('openalex')
            affiliations += a
        except:
            pass
        try:
            o = author.pop('affiliations')
            openalex += o
        except:
            pass
        # transfer relationships to main author
        for authorship in author['~authors']:
            del_obj = [
                {
                    "uid": authorship['uid'],
                    "authors": {"uid": author['uid']}
                }
            ]
            client.txn().mutate(del_obj=del_obj, commit_now=True)
            set_obj = {
                "set": [
                    {
                        "uid": authorship['uid'],
                        "authors": {
                            "uid": main_author['uid'],
                            'authors|sequence': authorship['~authors|sequence']
                        }
                    }
                ]
            }
            client.txn().mutate(set_obj=set_obj, commit_now=True)

        client.txn().mutate(del_obj=[{'uid': author['uid']}], commit_now=True)

    # merge them into one
    merged_author = authors[0]
    for author in authors:
        merged_author.update(author)

    _ = merged_author.pop('~authors')
    _ = main_author.pop('~authors')
    merged_author.update(main_author)
    merged_author['affilations'] = affiliations
    merged_author['openalex'] = openalex
    if orcid:
        merged_author['orcid'] = orcid

    # update main author
    client.txn().mutate(set_obj={'set': [merged_author]}, commit_now=True)

