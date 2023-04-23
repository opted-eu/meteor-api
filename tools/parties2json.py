"""
    Script for converting table (csv, xlsx) data about political parties
    to JSON files, ready for DGraph
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import date
import pydgraph
from slugify import slugify

p = Path.cwd()

xlsx = p / 'data' / 'OPTED Taxonomy.xlsx'

df = pd.read_excel(xlsx, sheet_name="politicalparty")

# Drop all without wikidata id (for now)
df = df.dropna(subset='wikidata_id').reset_index(drop=True)
# drop all duplicates wikidata ids
df = df.drop_duplicates(subset='wikidata_id')
df = df.replace(np.nan, "")

# clean string columns (remove whitespace)
df = df.apply(lambda x: x.str.strip())


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

countries = df.country.unique().tolist()

country_uid_mapping = {}
country_unique_name_mapping = {}

for country_name in countries:
    country = client.txn(read_only=True).query(query_string, variables={'$country': country_name})
    j = json.loads(country.json)
    country_uid_mapping[country_name] = j['q'][0]['uid']
    country_unique_name_mapping[country_name] = j['q'][0]['_unique_name']

df['country_unique_name'] = df.country.replace(country_unique_name_mapping)
df['country'] = df.country.replace(country_uid_mapping)

# Generate Unique Names for political parties

df['_unique_name'] = ''

# generate for parties without abbreviation
# filt = df.abbrev_name == ''
# df.loc[filt, '_unique_name'] = 'politicalparty_' + df.loc[filt, 'country_unique_name'].apply(slugify, separator="") + '_' + df.loc[filt, 'original.name'].apply(slugify, separator="")

# df.loc[~filt, '_unique_name'] = 'politicalparty_' + df.loc[~filt, 'country_unique_name'].apply(slugify, separator="") + '_' + df.loc[~filt, 'abbrev_name'].apply(slugify, separator="")

df['_unique_name'] = 'politicalparty_' + df['country_unique_name'].apply(slugify, separator="") + '_' + df['original.name'].apply(slugify, separator="")


# assert len(df) == len(df.drop_duplicates(subset="_unique_name")), 'Not all unique names are unique!'
df = df.drop_duplicates(subset="_unique_name")


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

filt = df.name == df.alternate_names
df.loc[filt, 'alternate_names'] = ""

df = df.rename(columns={'name_english': 'name@en', 
                   'party_colors': 'color_hex',
                   'official_website': 'url',
                   'facebook_id': 'facebook',
                   'instagram_username': 'instagram',
                   'twitter_username': 'twitter'})

df = df.drop(columns=['note', 'country_unique_name'])


# convert df to a dict

parties = df.to_dict(orient='records')

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