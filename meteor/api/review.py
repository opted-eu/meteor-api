"""
    Contains Queries and Utility functions
    for Review Routes
"""

import typing

from flask import current_app

from meteor import dgraph
from meteor.flaskdgraph import Schema
from meteor.flaskdgraph import dql
from meteor.flaskdgraph.dgraph_types import UID, dict_to_nquad, Variable, make_nquad, Scalar
from meteor.main.model import User
import datetime

def get_overview(dgraph_type: str = None, 
                 country: str = None, 
                 user: str = None, 
                 text_type: str = None) -> list:


    query_vars = []

    query_func = f'''{{ q(func: has(dgraph.type)) '''

    filt_string = '@filter( eq(entry_review_status, "pending") '

    if dgraph_type:
        filt_string += 'AND type($dgraphtype) '
        query_vars.append(dql.GraphQLVariable(dgraphtype=dgraph_type))
    
    if country:
        if country != 'all':
            filt_string += f''' AND ( uid_in(country, $country) OR uid_in(countries, $country) ) '''
            query_vars.append(dql.GraphQLVariable(country=country))

    if text_type:
        if text_type != 'any':
            filt_string += f''' AND uid_in(text_types, $texttype) '''
            query_vars.append(dql.GraphQLVariable(texttype=text_type))

    if user:
        if user != 'any':
            filt_string += f''' AND uid_in(_added_by, $user) '''
            query_vars.append(dql.GraphQLVariable(user=user))

    filt_string += ')'

    query_fields = f''' uid name _unique_name dgraph.type entry_review_status
                        _added_by @facets(timestamp) {{ uid display_name }}
                        country {{ uid _unique_name name }} 
                        countries {{ uid _unique_name name }}
                        channel {{ uid _unique_name name }}
                        channels {{ uid _unique_name name }} '''

   
    query_head = ''
    if len(query_vars) > 0:
        query_vars_declaration = ", ".join([f'{v.name} : {v.dtype}' for v in query_vars])
        query_head += 'query getOverview( '
        query_head += query_vars_declaration
        query_head += ')'

    query = f'{query_head} {query_func} {filt_string} {{ {query_fields} }} }}'

    variables = None
    if len(query_vars) > 0:
        variables = {var.name: var.value for var in query_vars}

    data = dgraph.query(query, variables=variables)

    if len(data['q']) == 0:
        return []

    data = data['q']
    for item in data:
        if 'Entry' in item['dgraph.type']:
            item['dgraph.type'].remove('Entry')
        if 'Resource' in item['dgraph.type']:
            item['dgraph.type'].remove('Resource')
    return data


def accept_entry(uid: str, reviewer: User) -> None:
    accepted = {'uid': uid, 
              'entry_review_status': 'accepted',
              "_reviewed_by":  {"uid": reviewer.uid, 
                                "_reviewed_by|timestamp": datetime.datetime.now().isoformat()}
              }
    dgraph.mutation(accepted)


def mark_revise(uid: str, reviewer: User) -> None:
    revise = {'uid': uid, 
              'entry_review_status': 'revise',
              "_reviewed_by":  {"uid": reviewer.uid, 
                                "_reviewed_by|timestamp": datetime.datetime.now().isoformat()}
              }
    dgraph.mutation(revise)
    
from string import ascii_letters

def reject_entry(uid: str, reviewer: User) -> None:

    current_app.logger.debug(f'Rejecting entry: UID {uid}')

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

    rejected = {'uid': uid, 'entry_review_status': 'rejected', 'dgraph.type': 'Rejected',
                "_reviewed_by": UID(reviewer.id, facets={'timestamp': datetime.datetime.now()})}
    set_nquads = " \n ".join(dict_to_nquad(rejected))

    dgraph.upsert(query, del_nquads=del_nquads)
    dgraph.upsert(None, set_nquads=set_nquads)
