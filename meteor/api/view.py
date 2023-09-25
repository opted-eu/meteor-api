from meteor import dgraph
from meteor.flaskdgraph import Schema
from meteor.main.model import *

import typing as t
from meteor.flaskdgraph.utils import recursive_restore_sequence, validate_uid

import logging

logger = logging.getLogger(__name__)

"""
    Inventory Detail View Functions
"""

def get_entry(unique_name: str = None, uid: str = None, dgraph_type: t.Union[str, Schema] = None) -> t.Union[dict, None]:
    query_var = 'query get_entry($value: string) { '
    if unique_name:
        uid = dgraph.get_uid("_unique_name", unique_name)

    uid = validate_uid(uid)
    if not uid:
        return None

    var = uid

    if dgraph_type:
        try:
            dgraph_type = Schema.get_type(dgraph_type)
        except TypeError:
            dgraph_type = None

    if not dgraph_type:
        dgraph_type = dgraph.get_dgraphtype(uid)

    query_func = f'entry(func: uid($value)) @filter(type({dgraph_type}))'


    query_fields = '''{ uid dgraph.type 
                        expand(_all_) { 
                            uid _unique_name name title entry_review_status display_name 
                            authors @facets(orderasc: sequence) { uid _unique_name name } 
                            _authors_fallback @facets(orderasc: sequence) 
                            channel { uid name _unique_name }
                            }
                        }
                        '''

    
    query_string = query_var + query_func + query_fields + ' }'
    print(query_string)

    data = dgraph.query(query_string, variables={'$value': var})

    if len(data['entry']) == 0:
        return None

    recursive_restore_sequence(data['entry'])
    # data = data['entry'][0]
    
    # Get authors again, in right order
    if 'authors' in data['entry'][0]:
        authors_query = """query get_entry($value: string) { 
            q(func: uid($value)) { 
                uid dgraph.type
                authors @facets(orderasc: sequence) { uid _unique_name name  }
                } 
            }
        """
        authors = dgraph.query(authors_query, variables={'$value': var})
        try:
            data['entry'][0]['authors'] = authors['q'][0]['authors']
        except Exception as e:
            logger.debug(f'Could not append authors: {e}')

    if dgraph_type == 'Channel':
        num_sources = dgraph.query(NewsSource.channel.count(uid, _reverse=True, entry_review_status="accepted"))
        data['num_sources'] = num_sources['channel'][0]['count']

    elif dgraph_type == 'Archive':
        num_sources = dgraph.query(Archive.sources_included.count(uid, entry_review_status="accepted"))
        data['num_sources'] = num_sources['sources_included'][0]['count(sources_included)']

    elif dgraph_type == 'Dataset':
        num_sources = dgraph.query(Dataset.sources_included.count(uid, entry_review_status="accepted"))
        data['num_sources'] = num_sources['sources_included'][0]['count(sources_included)']

    elif dgraph_type == 'Country':
        num_sources = dgraph.query(NewsSource.countries.count(uid, _reverse=True, entry_review_status="accepted"))
        data['num_sources'] = num_sources['countries'][0]['count']
        num_orgs = dgraph.query(Organization.country.count(uid, _reverse=True, entry_review_status="accepted"))
        data['num_orgs'] = num_orgs['country'][0]['count']
    
    elif dgraph_type == 'Multinational':
        num_sources = dgraph.query(NewsSource.countries.count(uid, _reverse=True, entry_review_status="accepted"))
        data['num_sources'] = num_sources['countries'][0]['count']

    elif dgraph_type == 'Subnational':
        num_sources = dgraph.query(NewsSource.subnational_scope.count(uid, _reverse=True, entry_review_status="accepted"))
        data['num_sources'] = num_sources['subnational_scope'][0]['count']

    return data


def get_reverse_relationships(uid: str = None) -> dict:
    query_var = 'query get_entry($value: string) { '
    
    uid = validate_uid(uid)
    if not uid:
        raise ValueError

    dgraph_type = dgraph.get_dgraphtype(uid)

    reverse_relationships = Schema.get_reverse_relationships(dgraph_type)
    query_relationships = []
    for predicate, dtype in reverse_relationships:
        subquery = f"""{dtype.lower()}s(func: type({dtype}), orderasc: _unique_name) @filter(uid_in({predicate}, $value)) {{
                        uid name title date_published entry_review_status dgraph.type
                        channel {{ _unique_name name uid entry_review_status }}
                        authors @facets(orderasc: sequence) {{ _unique_name uid name entry_review_status }}
                        _authors_fallback @facets(orderasc: sequence)
                        }}"""
        
        query_relationships.append(subquery)

    
    query_string = query_var + "\n".join(query_relationships) + ' }'
    print(query_string)

    data = dgraph.query(query_string, variables={'$value': uid})

    for v in data.values():
        try:
            recursive_restore_sequence(v)
        except:
            continue

    return data

def get_rejected(uid):
    query_string = f'''{{ q(func: uid({uid})) @filter(type(Rejected)) 
                        {{ uid name _unique_name alternate_names 
                            _date_created _added_by {{ uid display_name }} 
                            entry_review_status _reviewed_by {{ uid display_name }}
                        }}
                        }}'''

    res = dgraph.query(query_string)

    if len(res['q']) > 0:
        return res['q'][0]
    else:
        return False
