from flask import current_app
from flaskinventory import dgraph



def get_overview(dgraphtype, country=None):
    
    query_head = f'''{{ q(func: type({dgraphtype})) @filter(eq(entry_review_status, "pending")) '''
    
    query_fields = f''' uid name unique_name dgraph.type entry_added @facets(timestamp) {{ uid user_displayname }}'''

    filt_string = f''''''

    if country:
        if country != 'all':
            filt_string = f''' @filter(uid({country})) '''
            query_head += '@cascade'

    if dgraphtype == 'Source':
        query_fields += f''' channel {{ uid unique_name name }} country: geographic_scope_countries {filt_string}  {{ uid unique_name name }}  '''
    else:
        query_fields += f''' country {filt_string}  {{ uid unique_name name }}  '''

    query = f'{query_head} {{ {query_fields} }} }}'

    data = dgraph.query(query)

    if len(data['q']) == 0:
        return False

    data = data['q']
    return data

def check_entry(uid):

    query = f'''{{ q(func: uid({uid})) {{ dgraph.type entry_review_status }} }}'''
    data = dgraph.query(query)

    if len(data['q']) == 0:
        return False
    
    return data['q'][0]

def accept_entry(uid):
    accepted = {'entry_review_status': 'accepted'}

    dgraph.update_entry(accepted, uid=uid)

def reject_entry(uid):
    del_nquads = f'''<{uid}> <dgraph.type> * .'''
    query = None
    dgraph.upsert(query, del_nquads=del_nquads)

    rejected = {'entry_review_status': 'rejected', 'dgraph.type': 'Rejected'}

    dgraph.update_entry(rejected, uid=uid)

