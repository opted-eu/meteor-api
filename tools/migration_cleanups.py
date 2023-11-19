import sys
sys.path.append('.')

import json
from tools.migration_helpers import (client, ADMIN_UID)
from meteor.main.model import Schema

def get_uid(unique_name):
    query_string = "query getUID($unique_name: string) { q(func: eq(_unique_name, $unique_name)) { uid } }"
    res = client.txn(read_only=True).query(query_string, variables={'$unique_name': unique_name})
    j = json.loads(res.json)
    return j['q'][0]['uid']

with open('data/collections.json') as f:
    collections = json.load(f)

for entry in collections:
    for k, v in entry.items():
        if type(v) == dict:
            try:
                _unique_name = v.pop('_unique_name')
                v['uid'] = get_uid(_unique_name)
            except Exception as e:
                print('could not get uid for entry', k, v, e)
        if type(v) == list:
            for subval in v:
                if type(subval) == dict:
                    try:
                        _unique_name = subval.pop('_unique_name')
                        subval['uid'] = get_uid(_unique_name)
                    except Exception as e:
                        print('could not get uid for entry', k, subval, e)
    # add user info
    entry['_added_by'] = {'uid': ADMIN_UID}


# add to dgraph
txn = client.txn()
res = txn.mutate(set_obj=collections, commit_now=True)

query_string = """{ q(func: has(github)) { uid github } }"""

res = client.txn().query(query_string)

j = json.loads(res.json)

for entry in j['q']:
    if entry['github'].endswith('/'):
        print('Updating', entry['uid'], entry['github'])
        github = entry['github'][:-1]
        mut = {'uid': entry['uid'],
               'github': github}
        txn = client.txn()
        txn.mutate(set_obj=mut, commit_now=True)

query_string = '{'
for dtype in Schema.get_types():
    query_string += f'{dtype.lower()}(func: type({dtype})) {{ count(uid) }}\n'

query_string += '}'

res = client.txn(read_only=True).query(query_string)

j = json.loads(res.json)
print('='*40)
print('DATABASE SUMMARY')
print('='*40)

for k, v in j.items():
    print(k, v[0])