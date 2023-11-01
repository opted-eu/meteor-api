
import pydgraph
from multiprocessing import Pool
import json

def do_thing(i):
    client_stub = pydgraph.DgraphClientStub('localhost:9080')
    client = pydgraph.DgraphClient(client_stub)
    client.check_version()
    for _ in range(10):
        txn = client.txn()
        res = txn.query('query myQuery($var: string) { q(func: eq(name, $var)) { uid } }', variables={'$var': 'somestring'})
        txn.discard()
        j = json.loads(res.json)
    client_stub.close()
    return j


with Pool(processes=6, maxtasksperchild=1) as pool:
    result = pool.map(do_thing, range(1000))

print(result)