# Collection of helpers for migrating / importing data

import sys
from os.path import dirname
sys.path.append(dirname(sys.path[0]))

import typing

import json
from pathlib import Path
import requests
import pydgraph

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
        if isinstance(o, datetime):
            return o.isoformat()

        return json.JSONEncoder.default(self, o)


def save_publication_cache():
    with open(_publication_cache_file, "w") as f:
        json.dump(PUBLICATION_CACHE, f) 


from flaskinventory.external.doi import resolve_doi, resolve_authors, clean_doi
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

with open(p / 'flaskinventory' / 'config.json') as f:
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

    if isinstance(openalex, list):
        for o in openalex:
            res = client.txn(read_only=True).query(dgraph_author_query, variables={'$orcid': str(orcid), '$openalex': str(o)})
            j = json.loads(res.json)
            if len(j['q']) > 0:
                return j['q'][0]
        return None

def process_doi(doi, cache, entry_review_status='accepted'):
    doi = clean_doi(doi)
    if doi in cache:
        publication = deepcopy(cache[doi])
    else:
        publication = resolve_doi(doi)
        cache[doi] = deepcopy(publication)
    authors_tmp = publication.pop('_authors_tmp')
    authors = resolve_authors(authors_tmp, orcid_token=CONFIG['ORCID_ACCESS_TOKEN'])

    output = {**publication,
              '_date_modified': datetime.datetime.now().isoformat(),
              'entry_review_status': entry_review_status,
              'doi': doi}
    
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
        if 'family_name' in author:
            a_name = author['given_name'] + " " + author['family_name']
        else:
            a_name = author['name']
        # And whether we've seen the ORCID before
        if orcid and orcid in cache:
            author_details = cache[orcid]
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
        # If the ORCID is new, then we create a new author
        elif orcid:
            author_details = {**author,
                                'uid': '_:' + orcid.replace('-', ''),
                                '_unique_name': 'author_' + orcid.replace('-', ''),
                                'entry_review_status': entry_review_status,
                                **author_template
                             }
            author_details['name'] = a_name
            cache[orcid] = deepcopy(author_details)
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
    output['authors'] = authors_new
    return output
