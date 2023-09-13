import sys
sys.path.append('.')

import json
from tools.migration_helpers import (client, ADMIN_UID)


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
