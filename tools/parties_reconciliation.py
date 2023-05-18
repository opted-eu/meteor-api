"""
    Script for converting table (csv, xlsx) data about political parties
    to JSON files, ready for DGraph
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import date, datetime
import pydgraph
from slugify import slugify
import difflib
from wikibase_reconcile import Client

p = Path.cwd()

# Load Data from Excel sheet
xlsx = p / 'data' / 'OPTED Taxonomy.xlsx'

# generate this feather file with `partyfacts_wikidata.py`
pfacts_feather = p / 'data' / 'partyfacts.feather'

df = pd.read_excel(xlsx, sheet_name="political_party")

# clean columns

df.name = df.name.str.strip()
df.abbrev_name = df.abbrev_name.str.strip()
df.alternate_names = df.alternate_names.str.strip()
df.name_english = df.name_english.str.strip()


# Join with Party facts data

partyfacts = pd.read_feather(pfacts_feather)
partyfacts.partyfacts_id = partyfacts.partyfacts_id.astype(int)

partyfacts.name = partyfacts.name.str.strip()
partyfacts.name_short = partyfacts.name_short.str.strip()
partyfacts.name_english = partyfacts.name_english.str.strip()

# manually fix some entries
partyfacts.loc[partyfacts.partyfacts_id == 1816, "wikidata_id"] = "Q49766"

opted_countries = df.dropna(subset="country").country.unique().tolist()
# partyfacts = partyfacts.loc[partyfacts.country.isin(opted_countries), :]

# join by wikidata first
party_ids_by_wikidata = {wikidata_id: party_id for wikidata_id, party_id in zip(
    partyfacts.wikidata_id.to_list(), partyfacts.partyfacts_id.to_list())}

df['partyfacts_id'] = df.wikidata_id.map(party_ids_by_wikidata)

# join country-wise by abbreviation

def fuzzy_match(x: str, possibilities: list, lookup: dict) -> str:
    # small helper function that tries to fuzzy match party names
    # returns the partyfacts_id from lookup dictionary
    possibilities = [p for p in possibilities if p is not None]
    try:
        result = difflib.get_close_matches(x, possibilities)[0]
        return lookup[result]
    except:
        return np.NaN


for country in df.dropna(subset="country").country.unique():
    partyfacts_filt = partyfacts.country == country
    party_ids_by_abbrev = {name: party_id for name, party_id in zip(
        partyfacts[partyfacts_filt].name_short.to_list(), 
        partyfacts[partyfacts_filt].partyfacts_id.to_list()
        ) if name is not None}
    party_ids_by_name = {name: party_id for name, party_id in zip(
        partyfacts[partyfacts_filt].name.to_list(), 
        partyfacts[partyfacts_filt].partyfacts_id.to_list()
        ) if name is not None}
    lookup = {**party_ids_by_abbrev, **party_ids_by_name}
    possibilities = [p for p in partyfacts[partyfacts_filt].name.to_list() if p is not None]
    filt = (df.country == country) & (df.partyfacts_id.isna())
    # df.loc[filt, 'partyfacts_id'] = df[filt].abbrev_name.map(party_ids_by_abbrev).fillna(df.loc[filt, 'partyfacts_id'])
    df.loc[filt, 'partyfacts_id'] = df[filt].name.apply(lambda x: fuzzy_match(x, possibilities, lookup))

# find row without wikidata id or partyfacts_id

filt = df.partyfacts_id.isna() & df.wikidata_id.isna()

# Drop all without any id (for now)

df_parties = df[~filt].reset_index(drop=True)

df_parties.partyfacts_id = df_parties.partyfacts_id.astype(np.float64)

parties_lookup = {unique_name: wikidata_id for unique_name, wikidata_id in zip(df_parties.unique_name.to_list(), df_parties.wikidata_id.to_list())}

# Load the WP4 data and get the parties from there

wp4 = pd.read_excel(xlsx, sheet_name="Resources")

# clean
wp4_strings = wp4.select_dtypes(['object'])
wp4[wp4_strings.columns] = wp4_strings.apply(lambda x: x.str.strip())

# split list cells

wp4["political_party_list"] = wp4.political_party.str.split(";")
wp4.political_party_list = wp4.political_party_list.apply(lambda l: [x.strip() for x in l])

# fix manifesto separately
manifesto_wp4 = wp4[wp4.name == "Manifesto Corpus"]
wp4 = wp4[wp4.name != "Manifesto Corpus"]

# Fix polidoc separately
polidoc_wp4 = wp4[wp4.name == "Political Documents Archive"]
wp4 = wp4[wp4.name != "Political Documents Archive"]

# Fix FES Data (collapse to one)
filt = wp4.url.str.contains("https://library.fes.de/pressemitteilungen")
wp4.loc[filt, "url"] = "https://library.fes.de/pressemitteilungen"

# get a unique list of datasets by urls
wp4_datasets_unique = wp4.url.unique().tolist()
# create a dict of dicts
# each dict represents one dataset 
wp4_datasets = {d: {'parties': []} for d in wp4_datasets_unique}

# get parties for each dataset

parties_not_found = []

for dataset in wp4_datasets_unique:
    tmp_parties = wp4.loc[wp4.url == dataset, "political_party_list"].explode().to_list()
    tmp_parties = list(set(tmp_parties))
    # reconcile against df_parties
    for p in tmp_parties:
        try:
            wp4_datasets[dataset]['sources_included'].append(parties_lookup[p])
        except KeyError:
            parties_not_found.append(p)

# try to reconcile with wikidata
df_not_found = df[df.unique_name.isin(parties_not_found)]
df_not_found['query'] = df_not_found['original.name'].str.replace(r' \(.*\)', "", regex=True)
df_not_found['type'] = "Q7278"
client = Client()

results = client.reconcile(df_not_found)
df_reconciled = client.results_to_pandas(results)
df_reconciled = df_reconciled.loc[:, ['search_string', 'name', 'id', 'description']]

df_not_found = df_not_found.join(df_reconciled.set_index('search_string'), on = "query", rsuffix="_wikidata")

# export parties for manual reconciliation
wp4['parties_not_found'] = wp4.political_party_list.apply(lambda x: set(x) & set(parties_not_found))
wp4_manual_reconciliation = wp4[wp4.parties_not_found.apply(len) > 0]
wp4_manual_reconciliation.parties_not_found = wp4_manual_reconciliation.parties_not_found.apply(lambda x: ", ".join(x))

with pd.ExcelWriter('manual_reconciliation.xlsx') as f:
    df_not_found.to_excel(f, sheet_name="Parties")
    wp4_manual_reconciliation.to_excel(f, sheet_name="WP4")



# take care of manifesto data
manifesto = partyfacts[partyfacts.dataset_key == "manifesto"]

# We want output like this
sample_json = {
    'dgraph.type': ['Entry', 'PoliticalParty'],
    'name': 'Sozialdemokratische Partei Deutschlands',
    'name@en': 'Social Democratic Party of Germany',
    'alternate_names': ['SPD'],
    'description': '',
    'wikidata_id': 'Q49768',
    'name_abbrev': 'SPD',
    'parlgov_id': "558",
    'party_facts_id': "383",
    'country': '<germany>'
    }


# This is a template dict that we copy below for each social media handle
newssource_template = {
    'dgraph.type': ['Entry', 'NewsSource'],
    'uid': '_:newsource',
    'channel': {'uid': ''},
    'name': 'Name',
    'identifier': 'handle',
    'publication_kind': 'organizational communication',
    'special_interest': False,
    'publication_cycle': 'continuous',
    'geographic_scope': 'national',
    'countries': [],
    'languages': [],
    'payment_model': 'free',
    'contains_ads': 'no',
    'party_affiliated': 'yes',
    'related_news_sources': []
}

# Step 1: resolve country names

client_stub = pydgraph.DgraphClientStub('localhost:9080')
client = pydgraph.DgraphClient(client_stub)

query_string = '''query countries($country: string) {
    q(func: type(Country)) @filter(eq(name, $country)) { uid _unique_name } 
}'''

countries = df_parties.country.unique().tolist()

country_uid_mapping = {}
country_unique_name_mapping = {}

for country_name in countries:
    country = client.txn(read_only=True).query(query_string, variables={'$country': country_name})
    j = json.loads(country.json)
    country_uid_mapping[country_name] = j['q'][0]['uid']
    country_unique_name_mapping[country_name] = j['q'][0]['_unique_name']

df_parties['country_unique_name'] = df_parties.country.replace(country_unique_name_mapping)
df_parties['country'] = df_parties.country.replace(country_uid_mapping)


# Generate Unique Names for political parties

df_parties['_unique_name'] = ''

# generate for parties without abbreviation
# filt = df_parties.abbrev_name == ''
# df_parties.loc[filt, '_unique_name'] = 'politicalparty_' + df_parties.loc[filt, 'country_unique_name'].apply(slugify, separator="") + '_' + df_parties.loc[filt, 'original.name'].apply(slugify, separator="")

# df_parties.loc[~filt, '_unique_name'] = 'politicalparty_' + df_parties.loc[~filt, 'country_unique_name'].apply(slugify, separator="") + '_' + df_parties.loc[~filt, 'abbrev_name'].apply(slugify, separator="")

df_parties['_unique_name'] = 'politicalparty_' + df_parties['country_unique_name'].apply(slugify, separator="") + '_' + df_parties['name'].apply(slugify, separator="")


# assert len(df_parties) == len(df_parties.drop_duplicates(subset="_unique_name")), 'Not all unique names are unique!'
# df_parties = df_parties.drop_duplicates(subset="_unique_name")


# Step 1.5: Resolve channel uids

query_string = '''{
    q(func: type(Channel)) { uid _unique_name } 
}'''

res = client.txn(read_only=True).query(query_string)
j = json.loads(res.json)

channels_mapping = {c['_unique_name']: c['uid'] for c in j['q']}

# Step 2: rename existing columns

# name -> name
# abbrev_name -> abbrev_name
# alternate_names -> [drop if identical with `name`]
# name_english -> name@en
# wikidata_id -> wikidata_id
# country -> country
# original.name -> add to alternate_names
# note -> [drop]
# party_colors -> color_hex
# official_website -> url
# facebook_id -> facebook
# instagram_username -> instagram
# twitter_username -> twitter

filt = df_parties.name == df_parties.alternate_names
df_parties.loc[filt, 'alternate_names'] = ""

df_parties = df_parties.rename(columns={'name_english': 'name@en', 
                   'party_colors': 'color_hex',
                   'official_website': 'url',
                   'facebook_id': 'facebook',
                   'instagram_username': 'instagram',
                   'twitter_username': 'twitter'})

df_parties = df_parties.drop(columns=['country_unique_name'])

# go through the dataframe by unique partyfact_ids to generate a dict

parties = {}

for party_id in df_parties.partyfacts_id.dropna().unique().tolist():
    pass

# convert df_parties to a dict

parties = df_parties.to_dict(orient='records')

# Reformatting

for party in parties:
    # Add dgraph.type
    party['dgraph.type'] = ['Entry', 'PoliticalParty']
    # reformat `alternate_names` to lists, drop `original.name`
    if party['original.name'] != party['alternate_names']:
        party['alternate_names'] = list(set([party['original.name'], party['alternate_names']]))
        try:
            party['alternate_names'].remove('')
        except:
            pass
    del party['original.name']
    # Step 5: reformat `country` to dicts
    party['country'] = {'uid': party['country']}
    # Step 6: Reformat social media channels to news sources
    party['publishes'] = []
    if party['twitter'] != '':
        handle = party['twitter']
        twitter = {**newssource_template}
        twitter['uid'] = f'_:{handle}_twitter'
        twitter['channel']['uid'] = channels_mapping['twitter']
        twitter['name'] = handle
        twitter['identifier'] = handle
        party['publishes'].append(twitter)
        # TODO: grab data from Twitter API
    _ = party.pop('twitter')
    if party['facebook'] != '':
        handle = party['facebook']
        facebook = {**newssource_template}
        facebook['uid'] = f'_:{handle}_facebook'
        facebook['channel']['uid'] = channels_mapping['facebook']
        facebook['name'] = handle
        facebook['identifier'] = handle
        party['publishes'].append(facebook)
    _ = party.pop('facebook')
    if party['instagram'] != '':
        handle = party['instagram']
        instagram = {**newssource_template}
        instagram['uid'] = f'_:{handle}_instagram'
        instagram['channel']['uid'] = channels_mapping['instagram']
        instagram['name'] = handle
        instagram['identifier'] = handle
        party['publishes'].append(instagram)
    _ = party.pop('instagram')

# Add related news sources to each other

for party in parties:
    if len(party['publishes']) > 1:
        new_ids = [{'uid': s['uid']} for s in party['publishes']]
        for newssource in party['publishes']:
            newssource['related_news_sources'] = new_ids



# Export JSON

output_file = p / 'data' / 'parties.json'

with open(output_file, 'w') as f:
    json.dump(parties, f)