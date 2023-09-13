from string import ascii_letters

from meteor import dgraph
from flask import current_app
from meteor.flaskdgraph import Schema
from meteor.flaskdgraph.dgraph_types import UID, Variable, Scalar, make_nquad, dict_to_nquad
from meteor.flaskdgraph.utils import recursive_restore_sequence

import logging

logger = logging.getLogger(__name__)

def get_entry(unique_name=None, uid=None):
    query_string = 'query get_entry($query: string) {'
    if unique_name:
        query_string += 'q(func: eq(_unique_name, $query))'
        variables = {'$query': unique_name}
    elif uid:
        query_string += 'q(func: uid($query))'
        variables = {'$query': uid}
    else:
        return False
    query_string += '{ uid expand(_all_) { name _unique_name uid display_name } } }'

    result = dgraph.query(query_string, variables=variables)
    if 'authors' in result['q'][0]:
        authors_query = """query get_entry($query: string) { 
            q(func: uid($query)) { 
                uid dgraph.type
                authors @facets(orderasc: sequence) { uid _unique_name name  }
                } 
            }
        """
        authors = dgraph.query(authors_query, variables=variables)
        try:
            result['q'][0]['authors'] = authors['q'][0]['authors']
        except Exception as e:
            logger.debug(f'Could not append authors: {e}')

    recursive_restore_sequence(result['q'])

    return result

def get_audience(uid):
    query_string = '''
    query get_audience($query: string) {
        q(func: uid($query)) { 
            uid _unique_name audience_size @facets 
            channel { _unique_name } 
            } 
        }'''
    
    result = dgraph.query(query_string, variables={"$query": uid})

    data = result['q'][0]

    rows = []
    # convert to list of dicts
    if 'audience_size' not in data.keys():
        cols = ['date', 'unit', 'count']
    else:
        keys = [key for key in data.keys() if key.startswith('audience_size|')]
        for i, item in enumerate(data['audience_size']):
            d = {'date': item}
            for key in keys:
                d[key.replace('audience_size|', '')] = data[key][str(i)]
            rows.append(d)

        cols = ['date'] + [key.replace('audience_size|', '') for key in keys]

    if data['channel']['_unique_name'] == 'print':
        if 'data_from' not in cols:
            cols.append('data_from')
    
    output = {'cols': cols, 'rows': rows}

    return output



def draft_delete(uid):

    current_app.logger.debug(f'Deleting draft: UID {uid}')

    uid = UID(uid)
    relationships = list(Schema.relationship_predicates().keys())
    query = []
    vars = {}

    for i, r in enumerate(relationships):
        var = Variable(ascii_letters[i], 'uid')
        query.append(f'{r}(func: has(dgraph.type)) @filter(uid_in({r}, {uid.query})) {{ {var.query} }}')
        vars[r] = var

    query = "\n".join(query)

    delete_predicates = ['dgraph.type', '_unique_name'] + relationships

    del_nquads = [make_nquad(uid, item, Scalar('*'))
                  for item in delete_predicates]
    for k, v in vars.items():
        del_nquads.append(make_nquad(v, k, uid))

    del_nquads = " \n ".join(del_nquads)

    deleted = {'uid': uid, 'entry_review_status': 'deleted'}
    set_nquads = " \n ".join(dict_to_nquad(deleted))

    dgraph.upsert(query, del_nquads=del_nquads)
    dgraph.upsert(None, set_nquads=set_nquads)

    final_delete = f'{uid.nquad} * * .'

    dgraph.upsert(None, del_nquads=final_delete)
