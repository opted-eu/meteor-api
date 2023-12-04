"""
    Script to import learning materials into Meteor
"""
import sys
sys.path.append('.')
import json
from pathlib import Path
from datetime import datetime

from tools.migration_helpers import client, ADMIN_UID

ENTRY_REVIEW_STATUS = 'accepted'

p = Path.cwd()

with open(p / 'data' / 'learning_materials.json') as f:
    j = json.load(f)


query_string = """query getEntry($unique_name: string) {
    q(func: eq(_unique_name, $unique_name)) {
        uid
    }
}
"""


for material in j:
    material['entry_review_status'] = ENTRY_REVIEW_STATUS
    material['_added_by'] = {
        'uid': ADMIN_UID,
        '_added_by|timestamp': datetime.now().isoformat()
        }
    material['_reviewed_by'] = {
        'uid': ADMIN_UID,
        '_reviewed_by|timestamp': datetime.now().isoformat()
        }
    for value in material.values():
        if type(value) == list:
            for subval in value:
                if type(subval) == dict:
                    if 'uid' in subval:
                        subval['entry_review_status'] = ENTRY_REVIEW_STATUS
                        subval['_added_by'] = {
                            'uid': ADMIN_UID,
                            '_reviewed_by|timestamp': datetime.now().isoformat()
                            }
                        subval['_reviewed_by'] = {
                            'uid': ADMIN_UID,
                            '_reviewed_by|timestamp': datetime.now().isoformat()
                            }
                        continue
                    try:
                        unique_name = subval.pop('_unique_name')
                        res = client.txn(read_only=True).query(query_string, variables={'$unique_name': unique_name})
                        uid = json.loads(res.json)['q'][0]['uid']
                        subval['uid'] = uid
                    except IndexError:
                        print('Could not find', unique_name)
                    except Exception as e:
                        print('error when looking up', subval, value, e)


with open('data/learning_materials_mutation.json', 'w') as f:
    json.dump(j, f, indent=True)

txn = client.txn()
res = txn.mutate(set_obj=j, commit_now=True)

print(res)