"""
    Script to import WP5 data (governments, parliaments and datasets) into Meteor
    Requires master spreadsheet "OPTED Taxonomy.xlsx" as input.
"""

import itertools
import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import date, datetime
import pydgraph
from slugify import slugify
import tweepy
import instaloader
import requests
from dateutil import parser as dateparser

from tools.countries_language_mapping import get_country_language_mapping, get_country_wikidata_mapping

ENTRY_REVIEW_STATUS = 'accepted'

p = Path.cwd()

client_stub = pydgraph.DgraphClientStub('localhost:9080')
client = pydgraph.DgraphClient(client_stub)

""" Get UID of Admin User """

query_string = '{ q(func: eq(email, "wp3@opted.eu")) { uid } }'

res = client.txn().query(query_string)

j = json.loads(res.json)['q']

ADMIN_UID = j[0]['uid']

# Load Data from Excel sheet
xlsx = p / 'data' / 'OPTED Taxonomy.xlsx'

df = pd.read_excel(xlsx, sheet_name="WP5")

# clean columns

df_strings = df.select_dtypes(['object'])
df[df_strings.columns] = df_strings.apply(lambda x: x.str.strip())

""" Get some wikidata mappings for dgraph """

country_wikidata_mapping = get_country_wikidata_mapping()
countries_language_mapping_dgraph = get_country_language_mapping()

""" Get Parliaments and Governments from Wikidata """
df.loc[df.parliament.isna(), 'parliament'] = ""

df['parliament'] = df.parliament.apply(lambda x: [y.strip() for y in x.split(';')])

parliaments_wikidata_ids = df.parliament.explode().unique().tolist()
parliaments_wikidata_ids.remove('')

canonical_parliaments = {}

parliament_template = {
    'dgraph.type': ['Entry', 'Parliament'],
    '_date_created': datetime.now().isoformat(),
    'entry_review_status': ENTRY_REVIEW_STATUS,
    '_added_by': {
        'uid': ADMIN_UID,
        '_added_by|timestamp': datetime.now().isoformat()},
}

for wikidata_id in parliaments_wikidata_ids:
    api = 'https://www.wikidata.org/w/api.php'
    params = {'action': 'wbgetentities', #'languages': 'en',
            'format': 'json'}
    params['ids'] = wikidata_id 
    r = requests.get(api, params=params)
    wikidata = r.json()['entities'][wikidata_id]
    new_parliament = {**parliament_template, 'wikidata_id': wikidata_id}
    # try to get native label first
    try:
        new_parliament['name'] = wikidata['claims']['P1705'][0]['mainsnak']['datavalue']['value']['text']
    except:
        new_parliament['name'] = wikidata['labels']['en']['value']
    new_parliament['name@en'] = wikidata['labels']['en']['value']
    try:
        new_parliament['alternate_names'] = [n['value'] for n in wikidata['aliases']['en']]
    except:
        pass
    try:
        new_parliament['description'] = wikidata['descriptions']['en']['value']
    except:
        pass
    try:
        new_parliament['hdl'] = wikidata['claims']['P1184'][0]['mainsnak']['datavalue']['value']
    except:
        pass
    try:
        country_wikidata = wikidata['claims']['P17'][0]['mainsnak']['datavalue']['value']['id']
    except: # P1001: aplies to jurisdiction
        country_wikidata = wikidata['claims']['P1001'][0]['mainsnak']['datavalue']['value']['id']
    if country_wikidata == "Q131964": #Austrian Empire
        country_wikidata = "Q40"
    if country_wikidata == "Q29999": # Kingdom of the Netherlands
        country_wikidata = "Q55"
    country_uid = country_wikidata_mapping[country_wikidata]
    new_parliament['country'] = {'uid': country_uid}
    new_parliament['languages'] = countries_language_mapping_dgraph[country_uid]
    try:
        new_parliament['url'] = wikidata['claims']['P856'][0]['mainsnak']['datavalue']['value']
    except:
        pass
    # get country code
    query_string = 'query countryCode ($u: string) { q(func: uid($u)) { iso_3166_1_2 }}'
    res = client.txn().query(query_string, variables={'$u': country_uid})
    j = json.loads(res.json)
    country_code = j['q'][0]['iso_3166_1_2']
    new_parliament['_unique_name'] = 'parliament_' + country_code + '_' + slugify(new_parliament['name'], separator="")
    new_parliament['uid'] = '_:' + new_parliament['_unique_name']
    canonical_parliaments[wikidata_id] = new_parliament

# Manually fix Council of Europe
canonical_parliaments['Q8908']['_unique_name'] = "parliament_euruope_councilofeurope"
canonical_parliaments['Q8908']['uid'] = "_:parliament_europe_councilofeurope"
query_string = '{ europe(func: eq(wikidata_id, "Q46")) { uid } french(func: eq(wikidata_id, "Q150")) { uid } english(func: eq(wikidata_id, "Q1860")) { uid } }'
res = client.txn().query(query_string)
j = json.loads(res.json)
canonical_parliaments['Q8908']['country'] = {'uid': j['europe'][0]['uid']}
canonical_parliaments['Q8908']['languages'] = [{'uid': j['french'][0]['uid']},
                                               {'uid': j['english'][0]['uid']}]

mutation_obj = list(canonical_parliaments.values())

txn = client.txn()
res = txn.mutate(set_obj=mutation_obj, commit_now=True)
