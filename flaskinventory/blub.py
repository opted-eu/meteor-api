from sys import path
from os.path import dirname
import pydgraph

path.append(dirname(path[0]))
from flaskinventory.main.model import Source

client_stub = pydgraph.DgraphClientStub()

client = pydgraph.DgraphClient(client_stub)

query = Source.name == "Der Standard"

print(query)
print(query.render())
print(query.get_graphql_variables())

res = client.txn(read_only=True).query(query.render(), variables=query.get_graphql_variables())

print(res)