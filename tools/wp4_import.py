"""
    Script to import WP4 data (parties & datasets) into Meteor
    Requires master spreadsheet "OPTED Taxonomy.xlsx" as input.
"""


import sys
from os.path import dirname
sys.path.append(dirname(sys.path[0]))


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
import secrets

from tools.migration_helpers import (PUBLICATION_CACHE, WIKIDATA_CACHE, 
                                     client, ADMIN_UID, process_doi, 
                                     save_publication_cache, save_wikidata_cache,
                                     remove_none, safe_clean_doi,
                                     get_duplicated_authors, deduplicate_author)


ENTRY_REVIEW_STATUS = 'accepted'

p = Path.cwd()


""" Twitter Helper functions """

config_path = p / "meteor" / "config.json"

with open(config_path) as f:
    api_keys = json.load(f)

twitter_auth = tweepy.OAuthHandler(api_keys["TWITTER_CONSUMER_KEY"],
                                   api_keys["TWITTER_CONSUMER_SECRET"])
twitter_auth.set_access_token(api_keys["TWITTER_ACCESS_TOKEN"],
                              api_keys["TWITTER_ACCESS_SECRET"])

twitter_api = tweepy.API(twitter_auth)

try:
    with open(p / 'data' / 'twitter_cache.json') as f:
        TWITTER_CACHE = json.load(f)
except:
    TWITTER_CACHE = {}

def fetch_twitter(username: str) -> dict:
    if username in TWITTER_CACHE:
        return TWITTER_CACHE[username]
    user = twitter_api.get_user(screen_name=username)
    result = {'followers': user.followers_count,
            'fullname': user.screen_name,
            'joined': user.created_at.isoformat(),
            'verified': user.verified}
    TWITTER_CACHE[username] = result
    return result


""" Instagram Helper Functions """

Loader = instaloader.Instaloader(
    user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")


def fetch_instagram(username: str, L=Loader) -> dict:
    # currently not working
    return False

    # try:
    #     profile = instaloader.Profile.from_username(
    #         L.context, username.lower())
    # except:
    #     return False

    # try:
    #     followers = profile.followers
    # except KeyError:
    #     followers = None

    # try:
    #     fullname = profile.full_name
    # except KeyError:
    #     fullname = None

    # try:
    #     verified = profile.is_verified
    # except:
    #     verified = False

    # return {'followers': followers, 'fullname': fullname, 'verified': verified}

""" Wikidata Helpers """

def get_names(wikidata_id: str) -> dict:
    """ Gets canonical names from wikidata 
        name: native name
        name@en: english name
        name_abbrev: abbreviated name
    """
    if wikidata_id in WIKIDATA_CACHE:
        wikidata = WIKIDATA_CACHE[wikidata_id]
    else:
        api = 'https://www.wikidata.org/w/api.php'
        params = {'action': 'wbgetentities', #'languages': 'en',
                'format': 'json',
                'ids': wikidata_id}
        r = requests.get(api, params=params)
        wikidata = r.json()
        WIKIDATA_CACHE[wikidata_id] = wikidata
    result = {}
    try:
        result['name@en'] = wikidata['entities'][wikidata_id]['labels']['en']['value']
    except:
        print('Problem getting English name at', wikidata_id)
    try:        
        result["name"] = wikidata['entities'][wikidata_id]['claims']['P1705'][0]['mainsnak']['datavalue']['value']['text']
    except:
        print('Problem getting native name at', wikidata_id)
    try:
        result['name_abbrev'] = wikidata['entities'][wikidata_id]['claims']['P1813'][0]['mainsnak']['datavalue']['value']['text']
    except:
        print('Problem getting short name at', wikidata_id)
    return result

client_stub = pydgraph.DgraphClientStub('localhost:9080')
client = pydgraph.DgraphClient(client_stub)

# Load Data from Excel sheet
xlsx = p / 'data' / 'OPTED Taxonomy.xlsx'

df = pd.read_excel(xlsx, sheet_name="political_party")

# clean columns

df_strings = df.select_dtypes(['object'])
df[df_strings.columns] = df_strings.apply(lambda x: x.str.strip())


# Load manually reconciled parties

parties_manual = pd.read_excel(
    xlsx, sheet_name="Parties Manual Reconciliation")

# get final wikidata ID

parties_manual.wikidata_id = parties_manual.wikidata_id.fillna(parties_manual.wp4_wikidata_id)
parties_manual.wp4_wikidata_id = parties_manual.wp4_wikidata_id.fillna(parties_manual.wikidata_id)
parties_manual.wikidata_final = parties_manual.wikidata_final.fillna(parties_manual.wikidata_id)

parties_manual.wikidata_id = parties_manual.wikidata_final

# drop missing wikidata ids
parties_manual = parties_manual[~parties_manual.wikidata_id.isna()].reset_index(drop=True)

# drop manually reconciled from df (xlsx sheet "political_party")
filt = df.unique_name.isin(parties_manual.unique_name.to_list())

df = df[~filt].reset_index(drop=True)

# add manually reconciled
df = pd.concat([df, parties_manual], ignore_index=True).reset_index(drop=True)

# Join with Party facts data

# generate this feather file with `partyfacts_wikidata.py`
pfacts_feather = p / 'data' / 'partyfacts.feather'

partyfacts = pd.read_feather(pfacts_feather)
partyfacts.partyfacts_id = partyfacts.partyfacts_id.astype(int)

manifesto_parties = partyfacts[partyfacts.dataset_key == 'manifesto']
manifesto_parties = manifesto_parties[~manifesto_parties.wikidata_id.isna()].reset_index(drop=True)
manifesto_parties = manifesto_parties.drop_duplicates(subset="wikidata_id").reset_index(drop=True)
manifesto_parties['cmp_code'] = manifesto_parties.dataset_party_id.astype(int)
manifesto_parties_uids = []

polidoc_file = p / 'data' / 'polidoc_parties.csv'

polidoc_parties = pd.read_csv(polidoc_file)
polidoc_parties = polidoc_parties.rename(columns={'CMP code': 'cmp_code'})
polidoc_parties = polidoc_parties.merge(manifesto_parties, on="cmp_code")

# Fix MLPD
polidoc_parties.loc[polidoc_parties.cmp_code == 41220, 'wikidata_id'] = "Q499632"

polidoc_parties_uids = []

partyfacts_strings = partyfacts.select_dtypes(['object'])
partyfacts[partyfacts_strings.columns] = partyfacts_strings.apply(
    lambda x: x.str.strip())

partyfacts = partyfacts.drop_duplicates(
    subset="partyfacts_id").reset_index(drop=True)

opted_countries = df.dropna(subset="country").country.unique().tolist()
# partyfacts = partyfacts.loc[partyfacts.country.isin(opted_countries), :]

# join by wikidata
party_ids_by_wikidata = {wikidata_id: party_id for wikidata_id, party_id in zip(
    partyfacts.wikidata_id.to_list(), partyfacts.partyfacts_id.to_list())}

df['partyfacts_id'] = df.wikidata_id.map(party_ids_by_wikidata)

# find row without wikidata id
filt = df.wikidata_id.isna()

# Drop all without id

df_parties = df[~filt].reset_index(drop=True)

party_template = {
    'dgraph.type': ['Entry', 'PoliticalParty'],
    '_date_created': datetime.now().isoformat(),
    'entry_review_status': ENTRY_REVIEW_STATUS,
    '_added_by': {
        'uid': ADMIN_UID,
        '_added_by|timestamp': datetime.now().isoformat()},
}

# This is a template dict that we copy below for each social media handle
newssource_template = {
    'dgraph.type': ['Entry', 'NewsSource'],
    '_date_created': datetime.now().isoformat(),
    'entry_review_status': ENTRY_REVIEW_STATUS,
    '_added_by': {
        'uid': ADMIN_UID,
        '_added_by|timestamp': datetime.now().isoformat()},
    'uid': '_:newsource',
    'name': 'Name',
    'identifier': 'handle',
    'publication_kind': 'organizational communication',
    'special_interest': False,
    'publication_cycle': 'continuous',
    'geographic_scope': 'national',
    'payment_model': 'free',
    'contains_ads': 'no',
    'party_affiliated': 'yes',
}

# Step 1: resolve country names

query_string = '''query countries($country: string) {
    q(func: match(name, $country, 2)) @filter(type(Country) OR type(Multinational)) { uid _unique_name iso_3166_1_2 } 
}'''

countries = df_parties.country.unique().tolist()

country_uid_mapping = {}
country_unique_name_mapping = {}
country_code_mapping = {}

for country_name in countries:
    country = client.txn(read_only=True).query(
        query_string, variables={'$country': country_name})
    j = json.loads(country.json)
    country_uid_mapping[country_name] = j['q'][0]['uid']
    country_unique_name_mapping[country_name] = j['q'][0]['_unique_name']
    country_code_mapping[country_name] = j['q'][0]['iso_3166_1_2']

df_parties['country_unique_name'] = df_parties.country.replace(
    country_unique_name_mapping)
df_parties['country_code'] = df_parties.country.replace(country_code_mapping)
df_parties['country'] = df_parties.country.replace(country_uid_mapping)


# Generate Unique Names for political parties

df_parties['_unique_name'] = ''

# generate for parties without abbreviation
# filt = df_parties.abbrev_name == ''
# df_parties.loc[filt, '_unique_name'] = 'politicalparty_' + df_parties.loc[filt, 'country_unique_name'].apply(slugify, separator="") + '_' + df_parties.loc[filt, 'original.name'].apply(slugify, separator="")

# df_parties.loc[~filt, '_unique_name'] = 'politicalparty_' + df_parties.loc[~filt, 'country_unique_name'].apply(slugify, separator="") + '_' + df_parties.loc[~filt, 'abbrev_name'].apply(slugify, separator="")

# df_parties['_unique_name'] = 'politicalparty_' + df_parties['country_code'] + '_' + df_parties['name'].apply(slugify, separator="")


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

# df_parties = df_parties.drop(columns=['country_unique_name'])

# Query to find entries that have the same Wikidata ID (already added by WP3)

query_string_wikidata = """query wiki($wikidata: string) {
    q(func: eq(wikidata_id, $wikidata)) {
        uid
    }
}"""

# clean original.name

df_parties['original.name'] = df_parties['original.name'].str.replace(r"\([A-Z]+\)", "", regex=True).str.strip()

# deal first with duplicated parties

parties_duplicated = df_parties[df_parties.wikidata_id.duplicated(keep=False)].fillna(
    '').groupby("wikidata_id").agg(lambda x: list(set(x))).to_dict(orient='index')

canonical_parties = []
parties_unique_name_lookup = {}


for wikidata_id, party in parties_duplicated.items():
    for v in party.values():
        remove_none(v)
    new_party = {**party_template}
    new_party['wikidata_id'] = wikidata_id
    wikidata_names = get_names(wikidata_id)
    # reformat `alternate_names` to lists, drop `original.name`
    if 'name' in wikidata_names:
        new_party['name'] = wikidata_names['name']
    else:
        if len(party['name']) > 0:
            new_party['name'] = party['name'][0]
        else:
            new_party['name'] = party['original.name'][0]
    names = party['name'] + party['original.name'] + party['alternate_names']
    try:
        names.remove(new_party['name'])
    except:
        pass
    try:
        names.remove(party['abbrev_name'][0])
    except:
        pass
    new_party['alternate_names'] = list(set(names))
    new_party['_unique_name'] = 'politicalparty_' + \
        party['country_code'][0] + '_' + \
        slugify(new_party['name'], separator="")
    res = client.txn(read_only=True).query(query_string_wikidata, variables={'$wikidata': new_party['wikidata_id']})
    res = json.loads(res.json)
    if len(res['q']) > 0:
        uid = res['q'][0]['uid']
    else:
        uid = '_:' + new_party['_unique_name']
    new_party['uid'] = uid
    if wikidata_id in manifesto_parties.wikidata_id.tolist():
        manifesto_parties_uids.append(new_party['uid'])
    if wikidata_id in polidoc_parties.wikidata_id.tolist():
        polidoc_parties_uids.append(new_party['uid'])
    new_party['_tmp_unique_name'] = party['unique_name']
    for un in party['unique_name']:
        parties_unique_name_lookup[un] = new_party['uid']
    # Step 5: reformat `country` to dicts
    new_party['country'] = {'uid': party['country'][0]}
    new_party['country']['_tmp_country_code'] = party['country_code'][0]
    if 'name_abbrev' in wikidata_names:
        new_party['name_abbrev'] = wikidata_names['name_abbrev']
    else:
        if len(party['abbrev_name']) > 0:
            new_party['name_abbrev'] = party['abbrev_name'][0]
    if 'name@en' in wikidata_names:
        new_party['name@en'] = wikidata_names['name@en']
    else:
        if len(party['name@en']) > 0:
            new_party['name@en'] = party['name@en'][0]
    if len(party['description']) > 0:
        new_party['description'] = party['description'][0]
    if len(party['partyfacts_id']) > 0:
        try:
            new_party['partyfacts_id'] = int(party['partyfacts_id'][0])
        except:
            pass
    if len(party['color_hex']) > 0:
        new_party['color_hex'] = party['color_hex'][0]
    if len(party['url']) > 0:
        new_party['url'] = party['url'][0]
    # Step 6: Reformat social media channels to news sources
    new_party['publishes'] = []
    if len(party['twitter']) > 0:
        handle = party['twitter'][0]
        twitter = {**newssource_template}
        twitter['uid'] = f'_:{handle}_twitter'
        twitter['channel'] = {'uid': channels_mapping['twitter']}
        twitter['name'] = handle
        twitter['identifier'] = handle
        twitter['countries'] = [{'uid': party['country'][0]}]
        twitter['_unique_name'] = "newssource_" + party['country_code'][0] + \
            '_' + slugify(handle, separator="") + '_twitter'
        try:
            api_data = fetch_twitter(handle)
            if api_data['followers']:
                twitter['audience_size'] = datetime.now().isoformat()
                twitter['audience_size|count'] = api_data['followers']
                twitter['audience_size|unit'] = 'followers'
            if api_data['verified']:
                twitter['verified_account'] = api_data['verified']
            if api_data['fullname']:
                twitter['alternate_names'] = api_data['fullname']
            if api_data['joined']:
                twitter['date_founded'] = api_data['joined']
        except Exception as e:
            print('could not fetch twitter data', handle, e)
        new_party['publishes'].append(twitter)
    if len(party['facebook']) > 0:
        handle = party['facebook'][0]
        facebook = {**newssource_template}
        facebook['uid'] = f'_:{handle}_facebook'
        facebook['channel'] = {'uid': channels_mapping['facebook']}
        facebook['name'] = handle
        facebook['identifier'] = handle
        facebook['countries'] = [{'uid': party['country'][0]}]
        facebook['_unique_name'] = "newssource_" + party['country_code'][0] + \
            '_' + slugify(handle, separator="") + '_facebook'
        new_party['publishes'].append(facebook)
    if len(party['instagram']) > 0:
        handle = party['instagram'][0]
        instagram = {**newssource_template}
        instagram['uid'] = f'_:{handle}_instagram'
        instagram['channel'] = {'uid': channels_mapping['instagram']}
        instagram['name'] = handle
        instagram['identifier'] = handle
        instagram['countries'] = [{'uid': party['country'][0]}]
        instagram['_unique_name'] = "newssource_" + party['country_code'][0] + \
            '_' + slugify(handle, separator="") + '_instagram'
        # try:
        #     api_data = fetch_instagram(handle)
        #     if api_data['followers']:
        #         instagram['audience_size'] = datetime.now().isoformat()
        #         instagram['audience_size|count'] = api_data['followers']
        #         instagram['audience_size|unit'] = 'followers'
        #     if api_data['verified']:
        #         instagram['verified_account'] = api_data['verified']
        #     if api_data['fullname']:
        #         instagram['alternate_names'] = api_data['fullname']
        # except Exception as e:
        #     print('could not fetch instagram data', handle, e)
        new_party['publishes'].append(instagram)
    canonical_parties.append(new_party)

# convert df_parties to a dict

parties = df_parties[~df_parties.wikidata_id.duplicated(keep=False)].fillna(
    '').to_dict(orient='records')

# Reformatting

for party in parties:
    new_party = {**party_template}
    new_party['wikidata_id'] = party['wikidata_id']
    wikidata_names = get_names(new_party['wikidata_id'])
    if 'name' in wikidata_names:
        new_party['name'] = wikidata_names['name']
    else:
        new_party['name'] = party['name'] if party['name'] != '' else party['original.name']
    names = list(
        set([party['name'], party['original.name'], party['alternate_names']]))
    try:
        names.remove(new_party['name'])
    except:
        pass
    remove_none(names)
    if len(names) > 0:
        new_party['alternate_names'] = names
    new_party['_unique_name'] = 'politicalparty_' + \
        party['country_code'] + '_' + slugify(new_party['name'], separator="")
    res = client.txn(read_only=True).query(query_string_wikidata, variables={'$wikidata': new_party['wikidata_id']})
    res = json.loads(res.json)
    if len(res['q']) > 0:
        uid = res['q'][0]['uid']
    else:
        uid = '_:' + new_party['_unique_name']
    new_party['uid'] = uid
    if new_party['wikidata_id'] in manifesto_parties.wikidata_id.tolist():
        manifesto_parties_uids.append(new_party['uid'])
    if new_party['wikidata_id'] in polidoc_parties.wikidata_id.tolist():
        polidoc_parties_uids.append(new_party['uid'])
    new_party['_tmp_unique_name'] = party['unique_name']
    parties_unique_name_lookup[party['unique_name']] = new_party['uid']
    # Step 5: reformat `country` to dicts
    new_party['country'] = {'uid': party['country']}
    new_party['country']['country_code'] = party['country_code']
    if 'name_abbrev' in wikidata_names:
        new_party['name_abbrev'] = wikidata_names['name_abbrev']
    else:
        if party['abbrev_name'] != '':
            new_party['name_abbrev'] = party['abbrev_name']
    if 'name@en' in wikidata_names:
        new_party['name@en'] = wikidata_names['name@en']
    else:
        if party['name@en'] != '':
            new_party['name@en'] = party['name@en']
    if party['description'] != '':
        new_party['description'] = party['description']
    if party['url'] != '':
        new_party['url'] = party['url']
    if party['color_hex'] != '':
        new_party['color_hex'] = party['color_hex']
    if party['partyfacts_id'] != '':
        new_party['partyfacts_id'] = int(party['partyfacts_id'])
    # Step 6: Reformat social media channels to news sources
    new_party['publishes'] = []
    if party['twitter'] != '':
        handle = party['twitter']
        twitter = {**newssource_template}
        twitter['uid'] = f'_:{handle}_twitter'
        twitter['channel'] = {'uid': channels_mapping['twitter']}
        twitter['name'] = handle
        twitter['identifier'] = handle
        twitter['countries'] = [{'uid': party['country']}]
        twitter['_unique_name'] = "newssource_" + party['country_code'] + \
            '_' + slugify(handle, separator="") + '_twitter'
        try:
            api_data = fetch_twitter(handle)
            if api_data['followers']:
                twitter['audience_size'] = datetime.now().isoformat()
                twitter['audience_size|count'] = api_data['followers']
                twitter['audience_size|unit'] = 'followers'
            if api_data['verified']:
                twitter['verified_account'] = api_data['verified']
            if api_data['fullname']:
                twitter['alternate_names'] = api_data['fullname']
            if api_data['joined']:
                twitter['date_founded'] = api_data['joined']
        except Exception as e:
            print('could not fetch twitter data', handle, e)
        new_party['publishes'].append(twitter)
    if party['facebook'] != '':
        handle = party['facebook']
        facebook = {**newssource_template}
        facebook['uid'] = f'_:{handle}_facebook'
        facebook['channel'] = {'uid': channels_mapping['facebook']}
        facebook['name'] = handle
        facebook['identifier'] = handle
        facebook['countries'] = [{'uid': party['country']}]
        facebook['_unique_name'] = "newssource_" + party['country_code'] + \
            '_' + slugify(handle, separator="") + '_facebook'
        new_party['publishes'].append(facebook)
    if party['instagram'] != '':
        handle = party['instagram']
        instagram = {**newssource_template}
        instagram['uid'] = f'_:{handle}_instagram'
        instagram['channel'] = {'uid': channels_mapping['instagram']}
        instagram['name'] = handle
        instagram['identifier'] = handle
        instagram['countries'] = [{'uid': party['country']}]
        instagram['_unique_name'] = "newssource_" + party['country_code'] + \
            '_' + slugify(handle, separator="") + '_instagram'
        # try:
        #     api_data = fetch_instagram(handle)
        #     if api_data['followers']:
        #         instagram['audience_size'] = datetime.now().isoformat()
        #         instagram['audience_size|count'] = api_data['followers']
        #         instagram['audience_size|unit'] = 'followers'
        #     if api_data['verified']:
        #         instagram['verified_account'] = api_data['verified']
        #     if api_data['fullname']:
        #         instagram['alternate_names'] = api_data['fullname']
        # except Exception as e:
        #     print('could not fetch instagram data', handle, e)
        new_party['publishes'].append(instagram)
    canonical_parties.append(new_party)

# Process Manifesto Parties

manifesto_parties['country_code'] = manifesto_parties.country.replace(country_code_mapping)
manifesto_parties['country_uid'] = manifesto_parties.country.replace(country_uid_mapping)

filt = manifesto_parties.wikidata_id.isin(df_parties.wikidata_id.tolist())

missing_manifesto_parties = manifesto_parties[~filt].to_dict(orient="records")

# Reformatting

for party in missing_manifesto_parties:
    new_party = {**party_template}
    new_party['wikidata_id'] = party['wikidata_id']
    wikidata_names = get_names(new_party['wikidata_id'])
    if 'name' in wikidata_names:
        new_party['name'] = wikidata_names['name']
    else:
        new_party['name'] = party['name']
    new_party['alternate_names'] = party.get('name_other')
    new_party['_unique_name'] = 'politicalparty_' + \
        party['country_code'] + '_' + slugify(new_party['name'], separator="")
    res = client.txn(read_only=True).query(query_string_wikidata, variables={'$wikidata': new_party['wikidata_id']})
    res = json.loads(res.json)
    if len(res['q']) > 0:
        uid = res['q'][0]['uid']
    else:
        uid = '_:' + new_party['_unique_name']
    new_party['uid'] = uid
    new_party['country'] = {'uid': country_uid_mapping[party['country']]}
    new_party['country']['country_code'] = party['country_code']
    manifesto_parties_uids.append(new_party['uid'])
    if new_party['wikidata_id'] in polidoc_parties.wikidata_id.tolist():
        polidoc_parties_uids.append(new_party['uid'])
    if 'abbrev_name' in wikidata_names:
        new_party['name_abbrev'] = wikidata_names['name_abbrev']
    else:
        if party['name_short'] != '':
            new_party['name_abbrev'] = party['name_short']
    if 'name@en' in wikidata_names:
        new_party['name@en'] = wikidata_names['name@en']
    else:
        if party['name_english'] != '':
            new_party['name@en'] = party['name_english']
    if party['partyfacts_id'] != '':
        new_party['partyfacts_id'] = int(party['partyfacts_id'])
    canonical_parties.append(new_party)


# Add related news sources to each other

for party in canonical_parties:
    if 'publishes' in party and len(party['publishes']) > 1:
        new_ids = [{'uid': s['uid']} for s in party['publishes']]
        for newssource in party['publishes']:
            newssource['related_news_sources'] = new_ids


# Export JSON

output_file = p / 'data' / 'parties.json'

with open(output_file, 'w') as f:
    json.dump(canonical_parties, f, indent=1)

with open(p / 'data' / 'twitter_cache.json', "w") as f:
    json.dump(TWITTER_CACHE, f, default=str)

save_wikidata_cache()

# txn = client.txn()

# txn.mutate(set_obj=canonical_parties, commit_now=True)
# txn.discard()

# WP4 column mappings

# 'country' -> 'countries' (get from political parties)
# 'political_party' -> 'sources_included'
# 'text_units' -> "text_type" (done)
# 'name' -> 'name'
# 'url' -> 'url'
# 'start_date' -> 'temporal_coverage_start' (facets for countries)
# 'end_date' -> 'temporal_coverage_end' (facets for countries)
# 'start.date' -> 'temporal_coverage_start' (facets for countries)
# 'end.date' -> 'temporal_coverage_end' (facets for countries)
# 'file_format' -> file_formats (done)
# 'authors' -> '_authors_fallback'
# 'meta_vars' -> 'meta_variables' (done)
# 'contains_full_text' -> fulltext_available
# 'entity' -> dgraph.type
# 'description' -> description
# 'regio_subnat_labels' -> fix manually later
# 'languages' -> languages (done)
# 'last_updated' -> date_modified
# 'doi' -> doi (use for openalex lookup)
# 'concept_vars' -> concept_variables 
# conditions_of_access -> conditions_of_access

wp4 = pd.read_excel(xlsx, sheet_name="Resources")

# clean
wp4_strings = wp4.select_dtypes(['object'])
wp4[wp4_strings.columns] = wp4_strings.apply(lambda x: x.str.strip())

# split list cells

wp4["political_party_list"] = wp4.sources_included.str.split(";")
wp4.political_party_list = wp4.political_party_list.apply(
    lambda l: [x.strip() for x in l])


""" Text Types """

wp4_texttypes_json = p / 'data' / 'wp4texttypes.json'

with open(wp4_texttypes_json) as f:
    wp4_texttypes = json.load(f)


for entry in wp4_texttypes:
    entry['_date_created'] = datetime.now().isoformat()
    entry['entry_review_status'] = ENTRY_REVIEW_STATUS
    entry['_added_by'] = {'uid': ADMIN_UID,
                         '_added_by|timestamp': datetime.now().isoformat()}

text_types_lookup = {'Press Release': {'uid': '_:texttype_pressrelease'},
                     'Social Media': {'uid': '_:texttype_socialmedia'},
                     'Manifesto':  {'uid': '_:texttype_manifesto'},
                     'Party Programme': {'uid': '_:texttype_manifesto'},
                     'Party Websites': {'uid': '_:texttype_partywebsite'},
                     'Statutes':  {'uid': '_:texttype_statutes'},
                     'Speech': {'uid': '_:texttype_speech'},
                     'Statement':  {'uid': '_:texttype_statement'}
                     }


wp4["text_type"] = wp4.text_type.str.split(",")
wp4["text_type"] = wp4.text_type.apply(lambda l: [text_types_lookup[x.strip()] for x in l])

""" Temporal Coverage """


wp4['temporal_coverage_start'] = pd.to_datetime(
    wp4['start.date'], format="%d.%m.%Y")
wp4['temporal_coverage_end'] = pd.to_datetime(
    wp4['end.date'], format="%d.%m.%Y")

wp4['temporal_coverage_start'] = wp4.temporal_coverage_start.dt.strftime('%Y-%m-%d')
wp4['temporal_coverage_end'] = wp4.temporal_coverage_end.dt.strftime('%Y-%m-%d')

wp4.loc[wp4.temporal_coverage_start.isna(), 'temporal_coverage_start'] = wp4[wp4.temporal_coverage_start.isna()].start_date.str.strip()
wp4.loc[wp4.temporal_coverage_end.isna(), 'temporal_coverage_end'] = wp4[wp4.temporal_coverage_end.isna()].end_date.str.strip()

""" File Formats """

query_string = '''{
    q(func: type(FileFormat)) { uid _unique_name name alternate_names } 
}'''

res = client.txn(read_only=True).query(query_string)
j = json.loads(res.json)

fileformat_mapping = {c['_unique_name']: {'uid': c['uid']} for c in j['q']}

wp4["file_formats"] = wp4.file_formats.str.split(";")
wp4.loc[~wp4.file_formats.isna(), "file_formats"] = wp4.loc[~wp4.file_formats.isna(), "file_formats"].apply(lambda l: [fileformat_mapping[x.strip()] for x in l])


""" Meta Variables """

query_string = """{
    metavariable_date(func: eq(_unique_name, "metavariable_date")) { uid }
    metavariable_headline(func: eq(_unique_name, "metavariable_headline")) { uid }
    metavariable_newssource(func: eq(_unique_name, "metavariable_newssource")) { uid }
    metavariable_pagenumber(func: eq(_unique_name, "metavariable_pagenumber")) { uid }
}"""

res = client.txn().query(query_string)

j = json.loads(res.json)

wp4.loc[wp4.meta_vars.isna(), 'meta_vars'] = ""

wp4_metavars_json = p / "data" / "wp4metavars.json"

with open(wp4_metavars_json) as f:
    wp4_metavars = json.load(f)


for entry in wp4_metavars:
    entry['_date_created'] = datetime.now().isoformat()
    entry['entry_review_status'] = ENTRY_REVIEW_STATUS
    entry['_added_by'] = {'uid': ADMIN_UID,
                         '_added_by|timestamp': datetime.now().isoformat()}


metavars_lookup = {'date': {'uid': j['metavariable_date'][0]['uid']},
                   'newspaper': {'uid': j['metavariable_newssource'][0]['uid']},
                   'page': {'uid': j['metavariable_pagenumber'][0]['uid']},
                   'author': {'uid': '_:metavariable_author'},
                   'country': {'uid': '_:metavariable_country'},
                   'country country name': {'uid': '_:metavariable_country'},
                   'ctryid country code': {'uid': '_:metavariable_country'},
                   'election year':  {'uid': '_:metavariable_electionyear'},
                   'election_year': {'uid': '_:metavariable_electionyear'},
                   'keywords.': {'uid': '_:metavariable_keywords'},
                   'language': {'uid': '_:metavariable_language'},
                   'title': {'uid': "_:metavariable_documenttitle"},
                   'title(s)': {'uid': "_:metavariable_documenttitle"},
                   'manifesto_title': {'uid': '_:metavariable_documenttitle'},
                   'manifesto_year': {'uid': '_:metavariable_year'},
                   'mp name': {'uid': '_:metavariable_politicianname'},
                   "party": {'uid': '_:metavariable_partyname'},
                   "party name": {'uid': '_:metavariable_partyname'},
                   "party name (short or long)": {'uid': '_:metavariable_partyname'},
                   "party name (short)": {'uid': '_:metavariable_partyname'},
                   "party_id": {'uid': '_:metavariable_partyname'},
                   "party_name": {'uid': '_:metavariable_partyname'},
                   "partycode": {'uid': '_:metavariable_partyname'},
                   "partyname": {'uid': '_:metavariable_partyname'},
                   "political party": {'uid': '_:metavariable_partyname'},
                   "source": {"uid": "_:metavariable_datasource"},
                   "speaker": {"uid": "_:metavariable_speakername"},
                   "speaker name": {"uid": "_:metavariable_speakername"},
                   "speechyear": {'uid': '_:metavariable_year'},
                   "time": {"uid": "_:metavariable_time"},
                   "twitter_id": {"uid": "_:metavariable_twitterid"},
                   "url": {"uid": "_:metavariable_url"},
                   "url_original": {"uid": "_:metavariable_url"},
                   "year": {'uid': '_:metavariable_year'}
                   }

wp4["meta_variables"] = wp4.meta_vars.str.split(",")
wp4.loc[~wp4.meta_variables.isna(), "meta_variables"] = wp4.loc[~wp4.meta_variables.isna(), "meta_variables"].apply(lambda l: [metavars_lookup[x.strip().lower()] for x in l if x.strip().lower() in metavars_lookup])

""" Languages """

query_string = '''{
    q(func: type(Language)) { uid _unique_name name alternate_names iso_639_2 icu_code } 
}'''

res = client.txn(read_only=True).query(query_string)
j = json.loads(res.json)

language_mapping = {c['icu_code']: c['uid'] for c in j['q'] if 'icu_code' in c}

wp4.loc[wp4.languages.isna(), 'languages'] = ""

wp4.languages = wp4.languages.str.split(',').apply(
    lambda l: [{'uid': language_mapping[x.strip().lower()]} for x in l if x in language_mapping])

""" Resolve Authors and DOIs """


import secrets

# get all entries with DOI



wp4.doi = wp4.doi.apply(safe_clean_doi)

dois = wp4[~wp4.doi.isna()].doi.unique()

authors = {}
publication_info = {}
failed = []

print('Retrieving Authors and DOI Metadata ...')

for doi in dois:
    try:
        print(doi)
        publication_info[doi] = process_doi(doi, PUBLICATION_CACHE, entry_review_status=ENTRY_REVIEW_STATUS)
        authors[doi] = publication_info[doi]['authors']
    except Exception as e:
        print('Problem at:', doi, e)
        failed.append(doi)

save_publication_cache()

""" Concept Variables """

query_string = """{
sentiment(func: eq(_unique_name, "conceptvariable_sentiment")) { uid }
position(func: eq(_unique_name, "conceptvariable_ideologicalposition")) { uid }
}"""

res = client.txn().query(query_string)

j = json.loads(res.json)

wp4.loc[wp4.concept_vars.isna(), 'concept_vars'] = ""

conceptvars_lookup = {
    'party communication': {'uid': '_:conceptvariable_partycommunication'},
    'issue salience': {'uid': '_:conceptvariable_issuesalience'},
    'ideological position': {'uid': j['position'][0]['uid']},
    'political sentiment': {'uid': j['sentiment'][0]['uid']}
}

wp4['concept_variables'] = wp4.concept_vars.str.split(';').apply(
    lambda l: [conceptvars_lookup[x.strip().lower()] for x in l if x.strip().lower() in conceptvars_lookup])


# fix manifesto separately
manifesto_wp4 = wp4[wp4.name == "Manifesto Corpus"]
manifesto_wp4 = manifesto_wp4.reset_index(drop=True)
wp4 = wp4[wp4.name != "Manifesto Corpus"]

# Fix polidoc separately
polidoc_wp4 = wp4[wp4.name == "Political Documents Archive"]
polidoc_wp4 = polidoc_wp4.reset_index(drop=True)

wp4 = wp4[wp4.name != "Political Documents Archive"]

# Fix FES Data (collapse to one)
filt = wp4.url.str.contains("https://library.fes.de/pressemitteilungen")
wp4.loc[filt, "url"] = "https://library.fes.de/pressemitteilungen"

# remove wikidata query
filt = wp4.url.str.startswith("https://query.wikidata.org")
wp4 = wp4[~filt]


sample_dataset = {
    'dgraph.type': ['Entry', 'Dataset'], # or Archive -> entity
    'entry_review_status': ENTRY_REVIEW_STATUS,
    '_date_created': datetime.now().isoformat(), 
    '_added_by': {'uid': ADMIN_UID,
                  '_added_by|timestamp': datetime.now().isoformat()}, 
    'name': "AUTNES", # -> name
    # 'description': "Data set including a ...", # -> description
    # 'doi': '10.11587/6L3JKK', # -> doi
    # 'url': 'https://data.aussda.at/dataset.xhtml?persistentId=doi:10.11587/6L3JKK', # -> URL
    # "authors": "", # fetch from OpenAlex API
    # "_authors_fallback": "",
    # "date_published": "2021-05-28", # fetch from OpenAlex API
    # "date_modified": "2021", # -> last_updated
    "conditions_of_access": "registration", # -> access (to_lower!)
    "fulltext_available": False, # -> contains_full_text (as bool)
    "geographic_scope": "national", # -> region
    # "languages": "", # -> languages
    # "text_types": "", # -> text.type
    # "file_formats": "", # -> file_format
    # "meta_variables": "", # -> meta_vars
    # "concept_variables": "", # -> concept_vars
    # "sources_included": '', # -> political_party
    # # "countries": "<Austria>", # infer from political_party
    # "temporal_coverage_start": "2002", # -> start_date
    # "temporal_coverage_end": "2002", # -> end_date
}


wp4_datasets = wp4.fillna('').groupby("url").agg(list).to_dict(orient='index')

clean_wp4 = []

# keep track on unique names
_unique_names = []

for dataset_url, dataset in wp4_datasets.items():
    for v in dataset.values():
        remove_none(v)
    new_dataset = {**sample_dataset}
    new_dataset['name'] = dataset['name'][0]
    new_dataset['uid'] = '_:' + slugify(dataset_url, separator="_")
    new_dataset['dgraph.type'] = dataset['entity'] + ['Entry']
    try:
        doi = dataset['doi'][0] if dataset['doi'][0].strip() != '' else None
        new_dataset['doi'] = doi
        if doi in publication_info:
            new_dataset['date_published'] = publication_info[doi]['date_published']
            new_dataset['venue'] = publication_info[doi]['venue']
            new_dataset['paper_kind'] = publication_info[doi]['paper_kind']
    except:
        pass
    new_dataset['url'] = dataset_url
    new_dataset['description'] = dataset['description'][0]
    if 'doi' in new_dataset and new_dataset['doi'] is not None and new_dataset['doi'] in authors:
        new_dataset['authors'] = authors[new_dataset['doi']]
    else:
        try:
            new_dataset['_authors_fallback'] = [a.strip() for a in dataset['_authors_fallback'][0].split(";")]
            new_dataset['_authors_fallback|sequence'] = {str(i): i for i in range(len(new_dataset['_authors_fallback']))}
        except:
            pass
    new_dataset['conditions_of_access'] = dataset['conditions_of_access'][0]
    new_dataset['fulltext_available'] = bool(dataset['fulltext_available'][0])
    geographic_scope = []
    for region in dataset['region']:
        for r in region.split(','):
            geographic_scope.append(r.strip())
    new_dataset['geographic_scope'] = list(set(geographic_scope))
    new_dataset['languages'] = list(itertools.chain(*dataset['languages']))
    new_dataset['text_types'] = list(itertools.chain(*dataset['text_type']))
    new_dataset['file_formats'] = list(itertools.chain(*dataset['file_formats']))
    new_dataset['meta_variables'] = list(itertools.chain(*dataset['meta_variables']))
    new_dataset['concept_variables'] = list(itertools.chain(*dataset['concept_variables']))
    sources_included = []
    failed_parties = []
    for party_list in dataset['sources_included']:
        for p in party_list.split(';'):
            try:
                sources_included.append({'uid': parties_unique_name_lookup[p.strip()]})
            except:
                failed_parties.append(p.strip())
    new_dataset['sources_included'] = sources_included
    try:
        new_dataset['temporal_coverage_start'] = min(dataset['temporal_coverage_start'])
        if new_dataset['temporal_coverage_start'] in ['ongoing', '?']:
             new_dataset['temporal_coverage_start'] = None
    except:
        pass
    try:
        new_dataset['temporal_coverage_end'] = max(dataset['temporal_coverage_end'])
        if new_dataset['temporal_coverage_end'] in ['ongoing', '?']:
            new_dataset['temporal_coverage_end'] = None
    except:
        pass
    new_dataset_countries = []
    for i, dataset_country_list in enumerate(dataset['country']):
        dataset_country_list = [country_uid_mapping[c.strip()] for c in dataset_country_list.split(',')]
        for dataset_country in dataset_country_list:
            try:
                new_dataset_countries.append({'uid': dataset_country, 
                                'countries|temporal_coverage_start': dataset['temporal_coverage_start'][i],
                                'countries|temporal_coverage_end': dataset['temporal_coverage_end'][i]})
            except:
                pass
    new_dataset['countries'] = new_dataset_countries
    _unique_name = dataset['entity'][0].lower() + '_' + slugify(new_dataset['name'], separator="")
    if _unique_name not in _unique_names:
        new_dataset['_unique_name'] = _unique_name
        _unique_names.append(_unique_name)
    else:
        _unique_name += secrets.token_urlsafe(6)
        new_dataset['_unique_name'] = _unique_name
        _unique_names.append(_unique_name)

    clean_wp4.append(new_dataset)

""" Manifesto Corpus """

manifesto_corpus = {**sample_dataset}

manifesto_corpus['name'] = "Manifesto Corpus"
manifesto_corpus['alternate_names'] = ["CMP", "Comparative Manifestos Project", "MARPOR", "Manifesto Research on Political Representation"]
manifesto_corpus['url'] = manifesto_wp4.url[0]
manifesto_corpus['uid'] = '_:' + slugify(manifesto_corpus['url'], separator="_")
manifesto_corpus['dgraph.type'] = ['Entry', 'Dataset']
manifesto_corpus['_unique_name'] = 'dataset_' + slugify(manifesto_corpus['name'], separator="")
doi = "10.25522/manifesto.mpdssa.2020b".upper()
manifesto_corpus['doi'] = doi
try:
    manifesto_datacite = process_doi(doi, {})
    manifesto_corpus['date_published'] = manifesto_datacite['date_published']
    manifesto_corpus['venue'] = manifesto_datacite['venue']
    manifesto_corpus['paper_kind'] = manifesto_datacite['paper_kind']
    manifesto_corpus['authors'] = manifesto_datacite['authors']
except:
    pass
manifesto_corpus['description'] = manifesto_wp4.description[0]
manifesto_corpus['_authors_fallback'] = [a.strip() for a in manifesto_wp4['_authors_fallback'][0].split(";")]
manifesto_corpus['_authors_fallback|sequence'] = {str(i): i for i in range(len(manifesto_corpus['_authors_fallback']))}
manifesto_corpus['conditions_of_access'] = manifesto_wp4['conditions_of_access'][0]
manifesto_corpus['fulltext_available'] = bool(manifesto_wp4['fulltext_available'][0])
manifesto_corpus['geographic_scope'] = ['national', 'multinational']
manifesto_corpus['languages'] = list(itertools.chain(*manifesto_wp4['languages']))
manifesto_corpus['text_types'] = list(itertools.chain(*manifesto_wp4['text_type']))
manifesto_corpus['file_formats'] = list(itertools.chain(*manifesto_wp4['file_formats']))
manifesto_corpus['meta_variables'] = list(itertools.chain(*manifesto_wp4['meta_variables']))
manifesto_corpus['concept_variables'] = list(itertools.chain(*manifesto_wp4['concept_variables']))
manifesto_corpus['sources_included'] = [{'uid': uid} for uid in manifesto_parties_uids]
manifesto_corpus['temporal_coverage_start'] = min(manifesto_wp4['temporal_coverage_start'])
manifesto_corpus['temporal_coverage_end'] = max(manifesto_wp4['temporal_coverage_end'])
manifesto_corpus_countries = []
for i, manifesto_wp4_country_list in enumerate(manifesto_wp4.country.tolist()):
    manifesto_wp4_country_list = [country_uid_mapping[c.strip()] for c in manifesto_wp4_country_list.split(',')]
    for manifesto_wp4_country in manifesto_wp4_country_list:
        try:
            manifesto_corpus_countries.append({'uid': manifesto_wp4_country, 
                            'countries|temporal_coverage_start': manifesto_wp4['temporal_coverage_start'][i],
                            'countries|temporal_coverage_end': manifesto_wp4['temporal_coverage_end'][i]})
        except:
            pass
manifesto_corpus['countries'] = manifesto_corpus_countries


""" Polidoc """

polidoc_dataset = {**sample_dataset}

polidoc_dataset['name'] = "Political Documents Archive"
polidoc_dataset['alternate_names'] = ["Polidoc", "polidoc.net"]
polidoc_dataset['url'] = polidoc_wp4.url[0]
polidoc_dataset['uid'] = '_:' + slugify(polidoc_dataset['url'], separator="_")
polidoc_dataset['dgraph.type'] = ['Entry', 'Dataset']
polidoc_dataset['_unique_name'] = 'dataset_' + slugify(polidoc_dataset['name'], separator="")
doi = "10.1080/09644000903055856"
polidoc_dataset['doi'] = doi
try:
    polidoc_datacite = process_doi(doi, {})
    polidoc_dataset['date_published'] = polidoc_datacite['date_published']
    polidoc_dataset['venue'] = polidoc_datacite['venue']
    polidoc_dataset['paper_kind'] = polidoc_datacite['paper_kind']
    polidoc_dataset['authors'] = polidoc_datacite['authors']
except:
    pass
polidoc_dataset['description'] = polidoc_wp4.description[0]
# polidoc_dataset['authors'] = resolve_openalex("10.1080/09644000903055856", author_cache)
polidoc_dataset['conditions_of_access'] = polidoc_wp4['conditions_of_access'][0]
polidoc_dataset['fulltext_available'] = bool(polidoc_wp4['fulltext_available'][0])
polidoc_dataset['geographic_scope'] = ['subnational', 'national', 'multinational']
polidoc_dataset['languages'] = list(itertools.chain(*polidoc_wp4['languages']))
polidoc_dataset['text_types'] = list(itertools.chain(*polidoc_wp4['text_type']))
polidoc_dataset['file_formats'] = list(itertools.chain(*polidoc_wp4['file_formats']))
polidoc_dataset['meta_variables'] = list(itertools.chain(*polidoc_wp4['meta_variables']))
polidoc_dataset['concept_variables'] = list(itertools.chain(*polidoc_wp4['concept_variables']))
polidoc_dataset['sources_included'] = [{'uid': uid} for uid in polidoc_parties_uids]
polidoc_dataset['temporal_coverage_start'] = min(polidoc_wp4['temporal_coverage_start'])
polidoc_dataset['temporal_coverage_end'] = max(polidoc_wp4['temporal_coverage_end'])
polidoc_dataset_countries = []
for i, polidoc_wp4_country_list in enumerate(polidoc_wp4.country.tolist()):
    polidoc_wp4_country_list = [country_uid_mapping[c.strip()] for c in polidoc_wp4_country_list.split(',')]
    for polidoc_wp4_country in polidoc_wp4_country_list:
        try:
            polidoc_dataset_countries.append({'uid': polidoc_wp4_country, 
                            'countries|temporal_coverage_start': polidoc_wp4['temporal_coverage_start'][i],
                            'countries|temporal_coverage_end': polidoc_wp4['temporal_coverage_end'][i]})
        except:
            pass

polidoc_dataset['countries'] = polidoc_dataset_countries


mutation_obj = canonical_parties + clean_wp4 + wp4_metavars + wp4_texttypes
mutation_obj.append(manifesto_corpus)
mutation_obj.append(polidoc_dataset)

p = Path.cwd()

wp4_mutation_file = p / 'data' / 'wp4mutation.json'

with open(wp4_mutation_file, "w") as f:
    json.dump(mutation_obj, f, indent=1)

txn = client.txn()
res = txn.mutate(set_obj=mutation_obj, commit_now=True)



# Deduplicate authors by name

duplicated = get_duplicated_authors()
print('Got', len(duplicated), 'duplicated authors:')
for a in duplicated:
    print('Deduplicating:', a)
    deduplicate_author(a)
