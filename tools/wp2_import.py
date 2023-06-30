"""
    Script to import WP2 data (research publications investigating citizen texts) into Meteor
    Requires master spreadsheet "OPTED Taxonomy.xlsx" as input.
"""
import sys
sys.path.append('.')
import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import date, datetime
import pydgraph
from slugify import slugify
import requests
from dateutil import parser as dateparser
import secrets
import re

ENTRY_REVIEW_STATUS = 'accepted'

p = Path.cwd()

client_stub = pydgraph.DgraphClientStub('localhost:9080')
client = pydgraph.DgraphClient(client_stub)

""" Get UID of Admin User """

query_string = '{ q(func: eq(email, "wp3@opted.eu")) { uid } }'

res = client.txn().query(query_string)

j = json.loads(res.json)['q']

ADMIN_UID = j[0]['uid']

""" Cache files """


author_cache_file = p / "data" / "author_cache.json"
crossref_cache_file = p / "data" / "crossref_cache.json"
wikidata_cache_file = p / "data" / "wikidata_cache.json"

try:
    with open(author_cache_file) as f:
        author_cache = json.load(f)
except:
    author_cache = {}

try:
    with open(crossref_cache_file) as f:
        crossref_cache = json.load(f)
except:
    crossref_cache = {}


try:
    with open(wikidata_cache_file) as f:
        wikidata_cache = json.load(f)
except:
    wikidata_cache = {}

# Load Data from Excel sheet
xlsx = p / 'data' / 'OPTED Taxonomy.xlsx'

df = pd.read_excel(xlsx, sheet_name="WP2")
wp2datasets = pd.read_excel(xlsx, sheet_name="WP2_datasets")

# clean columns

df_strings = df.select_dtypes(['object'])
df[df_strings.columns] = df_strings.apply(lambda x: x.str.strip())

wp2datasets_strings = wp2datasets.select_dtypes(['object'])
wp2datasets[wp2datasets_strings.columns] = wp2datasets_strings.apply(lambda x: x.str.strip())



# Column mappings
# original_id -> _tmp_unique_name
# authors -> drop / fallback
# title -> drop / fallback
# date_published -> drop / fallback
# venue -> drop / fallback
# url -> url
# doi -> strip link -> doi
# temporal_coverage_start -> parse datetime -> temporal_coverage_start
# temporal_coverage_end -> parse datetime -> temporal_coverage_end
# countries -> split(';') -> country_uid_mapping -> countries
# geographic_scope -> lower -> geographic_scope
# languages -> split(';') -> language_uid_mapping
# text_units -> WP 2 mapping table -> text_units
# tools_used -> manually code (?)
# methodologies -> WP2 mapping table -> methodologies
# channels -> WP2 mapping table -> channels
# v16_sample_description -> append to description: description + "\nSample: " + v16_sample_description

""" Temporal coverage """

df.loc[df.temporal_coverage_start.isna(), 'temporal_coverage_start'] = ""
df.loc[df.temporal_coverage_end.isna(), 'temporal_coverage_end'] = ""

wp2datasets.loc[wp2datasets.temporal_coverage_start.isna(), 'temporal_coverage_start'] = ""
wp2datasets.loc[wp2datasets.temporal_coverage_end.isna(), 'temporal_coverage_end'] = ""


""" Countries """


query_string = '''query countries($country: string) {
    q(func: match(name, $country, 2)) @filter(type(Country) OR type(Multinational)) { uid _unique_name name iso_3166_1_2 } 
}'''

df.loc[df.countries.isna(), 'countries'] = ''
wp2datasets.countries = wp2datasets.countries.fillna("")

countries_term_mapping = {
    "Palestine": "Palestinian Territories",
    "United States": "United States of America",
    "Bosnia Herzegovina": "Bosnia and Herzegovina",
    "Czech Rep.": "Czech Republic",
    "Dominican Rep.": "Dominican Republic",
}

for k, v in countries_term_mapping.items():
    df.countries = df.countries.str.replace(k, v)

countries = list(set(df.countries.apply(lambda x: [y.strip() for y in x.split(';')]).explode().unique().tolist()))
countries.remove('')

country_uid_mapping = {}
country_unique_name_mapping = {}
country_code_mapping = {}

for country_name in countries:
    country = client.txn(read_only=True).query(
        query_string, variables={'$country': country_name})
    j = json.loads(country.json)
    try:
        country_uid_mapping[country_name] = j['q'][0]['uid']
        country_unique_name_mapping[country_name] = j['q'][0]['_unique_name']
        try:
            country_code_mapping[country_name] = j['q'][0]['iso_3166_1_2']
        except:
            country_code_mapping[country_name] = j['q'][0]['name'].lower()
    except Exception:
        print('country not found:', country_name)



""" Languages """

df.loc[df.languages.isna(), 'languages'] = ""
wp2datasets.languages = wp2datasets.languages.fillna("")

languages_term_mapping = {
    "Cyprus": "Modern Greek",
    "Hungary": "Hungarian", 
    "Roman Urdu": "Urdu",
    "Luxembourg": "Luxembourgish",
    "Chinese": "Simplified Chinese",
    "Czech Republic": "Czech",
    "Belgium": "French; Dutch",
    "Denmark": "Danish",
    "Swede": "Swedish",
    "Finland": "Finnish",
    "Netherlands": "Dutch",
    "Portugal": "Portuguese",
    "Arabic (Levantine)": "Arabic",
    "Austria": "German",
    "Greece": "Modern Greek"
    }


for k, v in languages_term_mapping.items():
    df.languages = df.languages.str.replace(k, v)

query_string = '''query language($language: string) {
    q(func: match(name, $language, 2)) @filter(type(Language)) { uid _unique_name name } 
}'''

languages = list(set(df.languages.apply(lambda x: [y.strip() for y in x.split(';')]).explode().unique().tolist()))
languages.remove('')

language_uid_mapping = {}

for language_name in languages:
    language = client.txn(read_only=True).query(
        query_string, variables={'$language': language_name})
    try:
        j = json.loads(language.json)
        language_uid_mapping[language_name] = j['q'][0]['uid']
    except:
        print('Could not find language:', language_name)

""" Channels """

df.channels = df.channels.fillna("")
wp2datasets.channels = wp2datasets.channels.fillna("")

df.channels = df.channels.str.replace('Weibo', 'Sina Weibo', regex=True)
df.channels = df.channels.str.replace('VKontakte', 'VK (VKontakte)', regex=True)

wp2datasets.channels = wp2datasets.channels.str.replace('Weibo', 'Sina Weibo', regex=True)
wp2datasets.channels = wp2datasets.channels.str.replace('VKontakte', 'VK (VKontakte)', regex=True)


channels = df.channels.apply(lambda x: [y.strip() for y in x.split(';')]).explode().unique().tolist()
channels.remove('')

query_string = '''query channel($channel: string) {
    q(func: match(name, $channel, 2)) @filter(type(Channel)) { uid _unique_name name } 
}'''

channel_uid_mapping = {}

for channel_name in channels:
    channel = client.txn(read_only=True).query(
        query_string, variables={'$channel': channel_name})
    try:
        j = json.loads(channel.json)
        channel_uid_mapping[channel_name] = j['q'][0]['uid']
    except:
        print('Could not find channel:', channel_name)


""" Resolve DOIs """


""" Authors: Check OpenAlex """

""" Unfortunately this does not work well at the moment
    because OpenAlex does not include DOIs registered by
    datacite.org
"""

def resolve_openalex(doi, cache):
    if doi in cache:
        j = cache[doi]
    else:
        api = "https://api.openalex.org/works/doi:"
        r = requests.get(api + doi, params={'mailto': "info@opted.eu"})
        j = r.json()
        cache[doi] = j
    publication = {
        'title': j['title'],
        'date_published': str(j['publication_year']),
        'paper_kind': j['type'],
        'openalex': j['id'].replace("https://openalex.org/", "")
        }
    try:
        publication['description'] = " ".join(j['abstract_inverted_index'])
    except:
        pass
    try:
        publication['venue'] = j['primary_location']['source']['display_name']
    except:
        pass
    authors = []
    for i, author in enumerate(j['authorships']):
        a_name = author['author']['display_name']
        open_alex = author['author']['id'].replace('https://openalex.org/', "")
        query_string = """query lookupAuthor ($openalex: string) 
        {
            q(func: eq(openalex, $openalex)) {
                    uid
            }
        }"""
        res = client.txn(read_only=True).query(query_string, variables={'$openalex': open_alex})
        j = json.loads(res.json)
        if len(j['q']) == 0:
            if open_alex in cache:
                author_details = cache[open_alex]
            else:
                api = "https://api.openalex.org/people/"
                r = requests.get(api + open_alex, params={'mailto': "info@opted.eu"})
                author_details = r.json()
                cache[open_alex] = author_details
            author_entry = {'uid': '_:' + slugify(open_alex, separator="_"),
                            '_unique_name': 'author_' + slugify(open_alex, separator=""),
                            'entry_review_status': ENTRY_REVIEW_STATUS,
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
                author_entry['orcid'] = author['author']['orcid'].replace('https://orcid.org/', '')
            try:
                author_entry['last_known_institution'] = author_details['last_known_institution']['display_name']
                author_entry['last_known_institution|openalex'] = author_details['last_known_institution']['id']
            except:
                pass
        else:
            author_entry = {'uid': j['q'][0]['uid']}
        authors.append(author_entry)
        publication['authors'] = authors
    return publication


df.doi = df.doi.fillna('')
df.doi = df.doi.str.replace('https://doi.org/', '', regex=False)

wp2datasets.doi = wp2datasets.doi.fillna('')
wp2datasets.doi = wp2datasets.doi.str.replace('https://doi.org/', '', regex=False)

""" Datasets """

dataset_template = {
    '_date_created': datetime.now().isoformat(),
    'entry_review_status': ENTRY_REVIEW_STATUS,
    '_added_by': {
        'uid': ADMIN_UID,
        '_added_by|timestamp': datetime.now().isoformat()},
}

wp2_datasets_canonical = {}

wp2datasets.github = wp2datasets.github.fillna('')
wp2datasets._authors_fallback = wp2datasets._authors_fallback.fillna('')


filt = wp2datasets.dgraph_type == 'Tool'

for index, row in wp2datasets[~filt].iterrows():
    doi = row['doi']
    new_entry = {**dataset_template, 
                 '_tmp_unique_name': row['wp2_paper_id'] + '_dataset',
                 'url': row['url'],
                 'doi': doi,
                 'description': '',
                'dgraph.type': ['Entry']}
    new_entry['dgraph.type'].append(row['dgraph_type'])
    if row['github'] != '':
        new_entry['github'] = row['github']
    try:
        publication = resolve_openalex(doi, author_cache)
        new_entry.update(publication)
        new_entry['title'] = None
    except Exception as e:
        print('could not resolve DOI:', doi, e)
        # new_entry['date_published'] = row['date_published']
        # new_entry['venue'] = row['venue']
        new_entry['_authors_fallback'] = row['_authors_fallback']
    try:
        new_entry['temporal_coverage_start'] = row['temporal_coverage_start'].isoformat()
        if new_entry['temporal_coverage_start'] == 'NaT':
            _ = new_entry.pop('temporal_coverage_start')
    except:
        pass
    try:
        new_entry['temporal_coverage_end'] = row['temporal_coverage_end'].isoformat()
        if new_entry['temporal_coverage_end'] == 'NaT':
            _ = new_entry.pop('temporal_coverage_end')
    except:
        pass
    try:
        _countries = [country_uid_mapping[c.strip()] for c in row['countries'].split(';') if c.strip() in country_uid_mapping]
        new_entry['countries'] = [{'uid': c} for c in _countries]
    except:
        print('could not resolve countries:', doi)
    try:
        _languages = [language_uid_mapping[l.strip()] for l in row['languages'].split(';') if l.strip() in language_uid_mapping]
        new_entry['languages'] = [{'uid': l} for l in _languages]
    except:
        print('could not resolve countries:', doi)
    try:
        new_entry['geographic_scope'] = row['geographic_scope'].lower()
    except:
        pass
    try:
        new_entry['fulltext_available'] = bool(row['fulltext_available'])
    except:
        new_entry['fulltext_available'] = False
    if row['defunct'] == 1:
        new_entry['defunct'] = True
    new_entry['conditions_of_access'] = row['conditions_of_access'].lower()
    # text_units
    # tools_used
    # methodologies
    # channels
    try:
        new_entry['description'] = 'Sample: ' + row['v16_sample_description']
    except:
        pass
    new_entry['name'] = row['name']
    if type(doi) == float:
        new_entry['_unique_name'] = 'dataset_' + slugify(new_entry['url'], separator="")
    else:
        new_entry['_unique_name'] = 'dataset_' + slugify(doi, separator="")
    new_entry['uid'] = '_:' + new_entry['_unique_name']
    new_entry['text_types'] = [{"uid": "_:texttype_citizen"}]
    wp2_datasets_canonical[row['wp2_paper_id']] = new_entry


print('Retrieving Article information from OpenAlex ...')

wp2_template = {
    'dgraph.type': ['Entry', 'ScientificPublication'],
    '_date_created': datetime.now().isoformat(),
    'entry_review_status': ENTRY_REVIEW_STATUS,
    '_added_by': {
        'uid': ADMIN_UID,
        '_added_by|timestamp': datetime.now().isoformat()},
}

wp2_texttypes = [{
        "uid": "_:texttype_citizen",
        "_unique_name": "texttype_citizen",
        "name": "Citizen-Produced Political Text",
        "alternate_names": ["CPPT"],
        "dgraph.type": [
            "Entry",
            "TextType"
        ],
        '_date_created': datetime.now().isoformat(),
        'entry_review_status': ENTRY_REVIEW_STATUS,
        '_added_by': {
            'uid': ADMIN_UID,
            '_added_by|timestamp': datetime.now().isoformat()},}
    ]

wp2_canonical = {}


for index, row in df.iterrows():
    doi = row['doi']
    new_entry = {**wp2_template, 
                 '_tmp_unique_name': row['original_id'],
                 'url': row['url'],
                 'doi': doi,
                 'description': ''}
    try:
        publication = resolve_openalex(doi, author_cache)
        new_entry.update(publication)
    except Exception as e:
        print('could not resolve DOI:', doi, e)
        new_entry['title'] = row['title']
        new_entry['date_published'] = row['date_published']
        new_entry['venue'] = row['venue']
        new_entry['_authors_fallback'] = row['authors']
    try:
        new_entry['temporal_coverage_start'] = row['temporal_coverage_start'].isoformat()
        if new_entry['temporal_coverage_start'] == 'NaT':
            _ = new_entry.pop('temporal_coverage_start')
    except:
        pass
    try:
        new_entry['temporal_coverage_end'] = row['temporal_coverage_end'].isoformat()
        if new_entry['temporal_coverage_end'] == 'NaT':
            _ = new_entry.pop('temporal_coverage_end')
    except:
        pass
    try:
        _countries = [country_uid_mapping[c.strip()] for c in row['countries'].split(';') if c.strip() in country_uid_mapping]
        new_entry['countries'] = [{'uid': c} for c in _countries]
    except:
        print('could not resolve countries:', doi)
    try:
        _languages = [language_uid_mapping[l.strip()] for l in row['languages'].split(';') if l.strip() in language_uid_mapping]
        new_entry['languages'] = [{'uid': l} for l in _languages]
    except:
        print('could not resolve countries:', doi)
    new_entry['geographic_scope'] = row['geographic_scope'].lower()
    # text_units
    # tools_used
    # methodologies
    # channels
    try:
        new_entry['description'] += '\nSample: ' + row['v16_sample_description']
    except:
        pass
    try:
        author_name = new_entry['authors'][0]['name']
        try:
            title = re.match(r".*?[\?:\.!]", str(new_entry['title']))[0]
        except:
            title = str(new_entry['title'])
        title = title.replace(':', '')
        year = str(new_entry['date_published'])
        name = f'{author_name} ({year}): {title}'
    except:
        name = new_entry['title']
    new_entry['name'] = name
    if type(doi) == float:
        new_entry['_unique_name'] = 'scientificpublication_' + slugify(new_entry['url'], separator="")
    else:
        new_entry['_unique_name'] = 'scientificpublication_' + slugify(doi, separator="")
    new_entry['uid'] = '_:' + new_entry['_unique_name']
    new_entry['text_types'] = [{"uid": "_:texttype_citizen"}]
    try:
        new_entry['datasets_used'] = [{'uid': wp2_datasets_canonical[row['original_id']]['uid']}]
    except:
        pass
    wp2_canonical[row['original_id']] = new_entry


mutation_obj = wp2_texttypes + list(wp2_datasets_canonical.values()) + list(wp2_canonical.values())

p = Path.cwd()

wp2_mutation_json = p / 'data' / 'wp2_mutation.json'

with open(wp2_mutation_json, 'w') as f:
    json.dump(mutation_obj, f, indent=1)


with open(author_cache_file, "w") as f:
    json.dump(author_cache, f)


with open(crossref_cache_file, "w") as f:
    json.dump(crossref_cache, f)


with open(wikidata_cache_file, "w") as f:
    json.dump(wikidata_cache, f)


txn = client.txn()
res = txn.mutate(set_obj=mutation_obj, commit_now=True)
