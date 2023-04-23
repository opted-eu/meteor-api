"""
    Script for loading political parties into DGraph
    make sure to select the right user who owns the entries
"""

import json
from pathlib import Path
from datetime import datetime
import pydgraph

p = Path.cwd()

parties_file = p / 'data' / 'parties.json'

with open(parties_file) as f:
    parties = json.load(f)


client_stub = pydgraph.DgraphClientStub('localhost:9080')
client = pydgraph.DgraphClient(client_stub)

USER_EMAIL = 'wp3@opted.eu'

user = client.txn().query(f'{{ q(func: eq(email, "{USER_EMAIL}")) {{ uid }} }}')

user_uid = json.loads(user.json)['q'][0]['uid']

for party in parties:
    party['_date_created'] = datetime.now().isoformat()
    party['_added_by'] = {'uid': user_uid}
    party['entry_review_status'] = 'accepted'


txn = client.txn()

try:
    txn.mutate(set_obj=parties)
    txn.commit()
finally:
    txn.discard()
