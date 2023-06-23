import pydgraph
import json

countries_language_mapping = {"Q40": ["Q188"],
                              "Q31": ["Q150", "Q7411", "Q188"],
                              "Q219": ["Q7918"],
                              "Q229": ["Q36510"],
                              "Q213": ["Q9056"],
                              "Q183": ["Q188"],
                              "Q35": ["Q9035"],
                              "Q191": ["Q9072"],
                              "Q29": ["Q1321"],
                              "Q33": ["Q1412"],
                              "Q142": ["Q150"],
                              "Q41": ["Q36510"],
                              "Q224": ["Q6654"],
                              "Q28": ["Q9067"],
                              "Q27": ["Q9142", "Q1860"],
                              "Q38": ["Q652"],
                              "Q37": ["Q9083"],
                              "Q32": ["Q9051", "Q188", "Q150"],
                              "Q211": ["Q9078"],
                              "Q233": ["Q9166"],
                              "Q55": ["Q7411"],
                              "Q36": ["Q809"],
                              "Q45": ["Q5146"],
                              "Q218": ["Q7913"],
                              "Q34": ["Q9027"],
                              "Q215": ["Q9063"],
                              "Q214": ["Q9058"],
                              "Q145": ["Q1860"],
                              "Q801": ["Q9288"],
                              "Q20": ["Q9043"],
                              "Q39": ["Q188", "Q150", "Q652"],
                              "Q407199": ["Q13955"],
                              "Q458": ["Q7918", "Q188", "Q6654", "Q9056", "Q9035", "Q1860", "Q9072", "Q1412", "Q150",
                                       "Q36510", "Q9067", "Q9142", "Q9166", "Q809",
                                       "Q5146", "Q7913", "Q9058", "Q9063", "Q1321", "Q9027"]}


def get_country_language_mapping() -> dict:
  client_stub = pydgraph.DgraphClientStub('localhost:9080')
  client = pydgraph.DgraphClient(client_stub)

  query_string = """query lookup ($wikidata_id: string)
  {
    q(func: eq(wikidata_id, $wikidata_id)) {
      uid _unique_name name
    }
      
  }"""

  countries_language_mapping_dgraph = {}

  for country, language_list in countries_language_mapping.items():
      res = client.txn().query(query_string, variables={"$wikidata_id": country})
      j = json.loads(res.json)
      country_uid = j['q'][0]['uid']
      countries_language_mapping_dgraph[country_uid] = []
      for language in language_list:
          res = client.txn().query(query_string, variables={"$wikidata_id": language})
          j = json.loads(res.json)
          language_uid = j['q'][0]['uid']
          countries_language_mapping_dgraph[country_uid].append({'uid': language_uid})

  return countries_language_mapping_dgraph


def get_country_wikidata_mapping() -> dict:
  client_stub = pydgraph.DgraphClientStub('localhost:9080')
  client = pydgraph.DgraphClient(client_stub)
  query_string = """query lookup ($wikidata_id: string)
  {
    q(func: eq(wikidata_id, $wikidata_id)) {
      uid _unique_name name
    }
      
  }"""
  country_wikidata_mapping = {}
  for country in countries_language_mapping.keys():
      res = client.txn().query(query_string, variables={"$wikidata_id": country})
      j = json.loads(res.json)
      country_uid = j['q'][0]['uid']
      country_wikidata_mapping[country] = country_uid
  return country_wikidata_mapping
