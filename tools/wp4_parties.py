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
import tweepy
import instaloader
import requests

p = Path.cwd()


""" Twitter Helper functions """

config_path = p / "flaskinventory" / "config.json"

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
            'joined': user.created_at,
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


client_stub = pydgraph.DgraphClientStub('localhost:9080')
client = pydgraph.DgraphClient(client_stub)

""" Get UID of Admin User """

query_string = '{ q(func: eq(email, "wp3@opted.eu")) { uid } }'

res = client.txn().query(query_string)

j = json.loads(res.json)['q']

ADMIN_UID = j[0]['uid']

# Load Data from Excel sheet
xlsx = p / 'data' / 'OPTED Taxonomy.xlsx'

df = pd.read_excel(xlsx, sheet_name="political_party")

# clean columns

df_strings = df.select_dtypes(['object'])
df[df_strings.columns] = df_strings.apply(lambda x: x.str.strip())


# Load manually reconciled parties

parties_manual = pd.read_excel(
    xlsx, sheet_name="Parties Manual Reconciliation")

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

polidoc_file = p / 'data' / 'polidoc_parties.csv'

polidoc_parties = pd.read_csv(polidoc_file)
polidoc_parties = polidoc_parties.rename(columns={'CMP code': 'cmp_code'})
polidoc_parties = polidoc_parties.merge(manifesto_parties, on="cmp_code")

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
    'entry_review_status': "pending",
    '_added_by': {
        'uid': ADMIN_UID,
        '_added_by|timestamp': datetime.now().isoformat()},
}

# This is a template dict that we copy below for each social media handle
newssource_template = {
    'dgraph.type': ['Entry', 'NewsSource'],
    '_date_created': datetime.now().isoformat(),
    'entry_review_status': "pending",
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

# deal first with duplicated parties

parties_duplicated = df_parties[df_parties.wikidata_id.duplicated()].fillna(
    '').groupby("wikidata_id").agg(lambda x: list(set(x))).to_dict(orient='index')

canonical_parties = []
parties_unique_name_lookup = {}

def remove_none(l: list):
    # helper to remove None and NA values from lists
    try:
        l.remove(None)
    except:
        pass
    try:
        l.remove(np.nan)
    except:
        pass
    try:
        l.remove('')
    except:
        pass


for wikidata_id, party in parties_duplicated.items():
    for v in party.values():
        remove_none(v)
    new_party = {**party_template}
    new_party['wikidata_id'] = wikidata_id
    # reformat `alternate_names` to lists, drop `original.name`
    if len(party['name']) > 0:
        new_party['name'] = party['name'][0]
    else:
        new_party['name'] = party['original.name'][0]
    names = party['name'] + party['original.name'] + party['alternate_names']
    names.remove(new_party['name'])
    new_party['alternate_names'] = list(set(names))
    new_party['_unique_name'] = 'politicalparty_' + \
        party['country_code'][0] + '_' + \
        slugify(new_party['name'], separator="")
    new_party['uid'] = '_:' + new_party['_unique_name']
    new_party['_tmp_unique_name'] = party['unique_name']
    for un in party['unique_name']:
        parties_unique_name_lookup[un] = new_party['uid']
    # Step 5: reformat `country` to dicts
    new_party['country'] = {'uid': party['country'][0]}
    new_party['country']['_tmp_country_code'] = party['country_code'][0]
    if len(party['abbrev_name']) > 0:
        new_party['name_abbrev'] = party['abbrev_name'][0]
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
                twitter['date_founded'] = api_data['joined'].isoformat()
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

parties = df_parties[~df_parties.wikidata_id.duplicated()].fillna(
    '').to_dict(orient='records')

# Reformatting

for party in parties:
    new_party = {**party_template}
    new_party['wikidata_id'] = party['wikidata_id']
    new_party['name'] = party['name'] if party['name'] != '' else party['original.name']
    names = list(
        set([party['name'], party['original.name'], party['alternate_names']]))
    names.remove(new_party['name'])
    remove_none(names)
    if len(names) > 0:
        new_party['alternate_names'] = names
    new_party['_unique_name'] = 'politicalparty_' + \
        party['country_code'] + '_' + slugify(new_party['name'], separator="")
    new_party['uid'] = '_:' + new_party['_unique_name']
    new_party['_tmp_unique_name'] = party['unique_name']
    parties_unique_name_lookup[party['unique_name']] = new_party['uid']
    # Step 5: reformat `country` to dicts
    new_party['country'] = {'uid': party['country']}
    new_party['country']['country_code'] = party['country_code']
    if party['abbrev_name'] != '':
        new_party['name_abbrev'] = party['abbrev_name']
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
                twitter['date_founded'] = api_data['joined'].isoformat()
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

# Add related news sources to each other

for party in canonical_parties:
    if len(party['publishes']) > 1:
        new_ids = [{'uid': s['uid']} for s in party['publishes']]
        for newssource in party['publishes']:
            newssource['related_news_sources'] = new_ids


# Export JSON

output_file = p / 'data' / 'parties.json'

with open(output_file, 'w') as f:
    json.dump(canonical_parties, f, indent=1)

with open(p / 'data' / 'twitter_cache.json', "w") as f:
    json.dump(TWITTER_CACHE, f, default=str)


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
wp4["file_formats"] = wp4.file_formats.apply(lambda l: [fileformat_mapping[x.strip()] for x in l])


""" Meta Variables """

wp4.loc[wp4.meta_vars.isna(), 'meta_vars'] = ""

wp4_metavars_json = p / "data" / "wp4metavars.json"

with open(wp4_metavars_json) as f:
    wp4_metavars = json.load(f)

metavars_lookup = {'date': {'uid': 'metavariable_date'},
                   'title': {'uid': 'metavariable_headline'},
                   'title(s)': {'uid': 'metavariable_headline'},
                   'newspaper': {'uid': 'metavariable_newssource'},
                   'page': {'uid': 'metavariable_pagenumber'},
                   'author': {'uid': '_:metavariable_author'},
                   'country': {'uid': '_:metavariable_country'},
                   'country country name': {'uid': '_:metavariable_country'},
                   'ctryid country code': {'uid': '_:metavariable_country'},
                   'election year':  {'uid': '_:metavariable_electionyear'},
                   'election_year': {'uid': '_:metavariable_electionyear'},
                   'keywords.': {'uid': '_:metavariable_keywords'},
                   'language': {'uid': '_:metavariable_language'},
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
wp4["meta_variables"] = wp4.meta_variables.apply(lambda l: [metavars_lookup[x.strip().lower()] for x in l if x.strip().lower() in metavars_lookup])

""" Languages """

query_string = '''{
    q(func: type(Language)) { uid _unique_name name alternate_names iso_639_2 icu_code } 
}'''

res = client.txn(read_only=True).query(query_string)
j = json.loads(res.json)

language_mapping = {c['icu_code']: c['uid'] for c in j['q']}



wp4.loc[wp4.languages.isna(), 'languages'] = ""

wp4.languages = wp4.languages.str.split(',').apply(
    lambda l: [{'uid': language_mapping[x.strip().lower()]} for x in l if x in language_mapping])

""" Authors: Check OpenAlex """

""" Unfortunately this does not work well at the moment
    because OpenAlex does not include DOIs registered by
    datacite.org
"""

author_cache_file = p / "data" / "author_cache.json"

try:
    with open(author_cache_file) as f:
        author_cache = json.load(f)
except:
    author_cache = {}


def resolve_openalex(doi, cache):
    if doi in cache:
        j = cache[doi]
    else:
        api = "https://api.openalex.org/works/doi:"
        r = requests.get(api + doi, params={'mailto': "info@opted.eu"})
        j = r.json()
        cache[doi] = j
    authors = []
    for i, author in enumerate(j['authorships']):
        a_name = author['author']['display_name']
        open_alex = author['author']['id'].replace('https://openalex.org/', "")
        author_entry = {'uid': '_:' + slugify(open_alex, separator="_"),
                        '_unique_name': 'author_' + slugify(open_alex, separator=""),
                        'entry_review_status': "pending",
                        'openalex': open_alex,
                        'name': a_name,
                        '_date_created': datetime.now().isoformat(),
                        'authors|sequence': i,
                        '_added_by': {
                            'uid': ADMIN_UID,
                            '_added_by|timestamp': datetime.now().isoformat()},
                        'dgraph.type': ['Entry', 'Author']
                        }
        if author['author'].get("orcid"):
            author_entry['orcid'] = author['author']['orcid']
        authors.append(author_entry)
    return authors

# get all entries with DOI

wp4.doi = wp4.doi.str.replace('https://doi.org/', '', regex=False)

dois = wp4[~wp4.doi.isna()].doi.unique()

authors = {}
failed = []

print('Retrieving Authors from OpenAlex ...')

for doi in dois:
    try:
        authors[doi] = resolve_openalex(doi, author_cache)
    except Exception as e:
        print(doi, e)
        failed.append(doi)


with open(author_cache_file, "w") as f:
    json.dump(author_cache, f)


""" Concept Variables """

wp4.loc[wp4.concept_vars.isna(), 'concept_vars'] = ""

conceptvars_lookup = {
    'party communication': {'uid': '_:conceptvariable_partycommunication'},
    'issue salience': {'uid': '_:conceptvariable_issuesalience'},
    'ideological position': {'uid': 'conceptvariable_ideologicalposition'},
    'political sentiment': {'uid': 'conceptvariable_sentiment'}
}

wp4['concept_variables'] = wp4.concept_vars.str.split(';').apply(
    lambda l: [conceptvars_lookup[x.strip().lower()] for x in l if x.strip().lower() in conceptvars_lookup])


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
