"""
    Script to import WP2 data (research publications investigating citizen texts) into Meteor
    Requires master spreadsheet "OPTED Taxonomy.xlsx" as input.
"""
import sys
sys.path.append('.')
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from slugify import slugify
import re

from tools.migration_helpers import (PUBLICATION_CACHE, 
                                     client, ADMIN_UID, process_doi, DOI_PATTERN,
                                     save_publication_cache,
                                     get_duplicated_authors, deduplicate_author)

ENTRY_REVIEW_STATUS = 'accepted'

p = Path.cwd()

# Load Data from Excel sheet
xlsx = p / 'data' / 'OPTED Taxonomy.xlsx'
wp2_full_xlsx = p / 'data' / 'CPPT_encoding_check_amanda2.xlsx'

df = pd.read_excel(xlsx, sheet_name="WP2")
wp2datasets = pd.read_excel(xlsx, sheet_name="WP2_datasets")

wp2_full = pd.read_excel(wp2_full_xlsx, sheet_name="finished")

wp2_mappings = pd.read_excel(xlsx, sheet_name="WP2 Mapping Table")

with open(p / 'data' / 'wp2texttypes.json') as f:
    wp2_texttypes = json.load(f)

# clean columns

df_strings = df.select_dtypes(['object'])
df[df_strings.columns] = df_strings.apply(lambda x: x.str.strip())

wp2datasets_strings = wp2datasets.select_dtypes(['object'])
wp2datasets[wp2datasets_strings.columns] = wp2datasets_strings.apply(lambda x: x.str.strip())

wp2_full_strings = wp2_full.select_dtypes(['object'])
wp2_full[wp2_full_strings.columns] = wp2_full_strings.apply(lambda x: x.str.strip())

# WP2 Column Mappings

col_mapping = {'v1_id': 'original_id',
               'v3_author': 'authors',
               'v4_title': 'title',
               'v5_year': 'date_published',
               'v6_source': 'venue',
               'v8_URL': 'url',
               'v11_DOI': 'doi',
               "v14_data_period_start": "temporal_coverage_start",
               "v14_data_period_end": "temporal_coverage_end",
               "v19_country": "countries",
               "v22_data_owner": "text_units",
               "v21_language": "languages"}

wp2_full = wp2_full.rename(columns=col_mapping)

wp2_full.v27_qual_method = wp2_full.v27_qual_method.fillna('')
wp2_full.v26_quant_method = wp2_full.v26_quant_method.fillna('')

wp2_full['methodologies'] = wp2_full.v26_quant_method + ", " +  wp2_full.v27_qual_method

""" Temporal coverage """

df.temporal_coverage_start = df.temporal_coverage_start.fillna('')
df.temporal_coverage_end = df.temporal_coverage_end.fillna('')

wp2_full.temporal_coverage_start = pd.to_datetime(wp2_full.temporal_coverage_start, unit="D", origin='1899-12-30')
wp2_full.temporal_coverage_end = pd.to_datetime(wp2_full.temporal_coverage_end, unit="D", origin='1899-12-30')

wp2datasets.temporal_coverage_start = wp2datasets.temporal_coverage_start.fillna('')
wp2datasets.temporal_coverage_end = wp2datasets.temporal_coverage_end.fillna('')

""" Append Full Dataset to excerpt """

filt = wp2_full.original_id.isin(df.original_id.to_list())

df = pd.concat([df, wp2_full[~filt]]).reset_index(drop=True)

""" Clean some strings """

weird_chars = {'√±': '–',
               '√õ': 'ó',
               '√à': 'é',
               '√ã': 'è',
               '√å': 'í',
               '√ï': 'Í',
               '√í': 'ñ',
               '‚Ä°‚Ä†': 'à',
               '‚Ä°√Ö': 'Á',
               '¬∑': 'á',
               '‚ÅÑ': 'Ê',
               '√Ç': 'å',
               '√ì': 'î'}

for old, new in weird_chars.items():
    df.title = df.title.str.replace(old, new, regex=False)
    df.authors = df.authors.str.replace(old, new, regex=False)
    df.venue = df.venue.str.replace(old, new, regex=False)


""" Countries """

query_string = '''query countries($country: string) {
    q(func: match(name, $country, 1)) @filter(type(Country) OR type(Multinational)) { uid _unique_name name iso_3166_1_2 } 
}'''

df.countries = df.countries.fillna('')
wp2datasets.countries = wp2datasets.countries.fillna("")

countries_term_mapping = {}

wp2_mappings.meteor_term = wp2_mappings.meteor_term.fillna('')

for country in wp2_mappings.loc[wp2_mappings.wp2_column == 'countries',].to_dict(orient='records'):
    if country['meteor_term'] == "":
        continue
    countries_term_mapping[country['wp2_term']] = country['meteor_term']

df.countries = df.countries.str.replace(',', ';')
df.countries = df.countries.str.replace(' and ', '; ')
df.countries = df.countries.str.replace('Poland. Belarus', 'Poland; Belarus')

countries = list(set(df.countries.apply(lambda x: [y.strip() for y in x.split(';')]).explode().unique().tolist()))
countries.remove('')

country_uid_mapping = {}
country_unique_name_mapping = {}
country_code_mapping = {}
failed = []

for country_name in countries:
    if country_name in countries_term_mapping:
        country_query = countries_term_mapping[country_name]
    else:
        country_query = country_name
    country = client.txn(read_only=True).query(
        query_string, variables={'$country': country_query})
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
        failed.append(country_name)



""" Languages """

df.loc[df.languages.isna(), 'languages'] = ""
wp2datasets.languages = wp2datasets.languages.fillna("")

df.languages = df.languages.fillna('')
df.languages = df.languages.str.replace(',', ';')

languages_term_mapping = {}
wp2_mappings.wikidata_id = wp2_mappings.wikidata_id.fillna('')

for language in wp2_mappings.loc[wp2_mappings.wp2_column == 'languages',].to_dict(orient='records'):
    if language['wikidata_id'] == "":
        continue
    languages_term_mapping[language['wp2_term']] = language['wikidata_id']

for i, row in df.iterrows():
    if row['languages'] in languages_term_mapping:
        df.at[i, 'languages'] = languages_term_mapping[row['languages']]
    row_langs = [l.strip() for l in row['languages'].split(';') if l.strip() != ""]
    for lang in row_langs:
        if lang in languages_term_mapping:
            j = row_langs.index(lang)
            row_langs[j] = languages_term_mapping[lang]
    df.at[i, 'languages'] = "; ".join(row_langs)


query_string = '''query language($language: string) {
    q(func: type(Language)) @filter(match(name, $language, 2) OR eq(alternate_names, $language) or eq(wikidata_id, $language)) { 
        uid _unique_name name 
    } 
}'''


languages = list(set(df.languages.apply(lambda x: [y.strip() for y in x.split(';')]).explode().unique().tolist()))
languages.remove('')

language_uid_mapping = {}

failed = []

for language_name in languages:
    language = client.txn(read_only=True).query(
        query_string, variables={'$language': language_name.strip()})
    try:
        j = json.loads(language.json)
        language_uid_mapping[language_name.strip()] = j['q'][0]['uid']
    except:
        print('Could not find language:', language_name)
        failed.append(language_name)

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
        channel_uid_mapping[channel_name.lower()] = j['q'][0]['uid']
    except:
        print('Could not find channel:', channel_name)

# extract channels

channel_regexes = [r'(youtube)', r'(facebook)', r'(twitter)', r'(instagram)',
                   r'(reddit)', r'(4chan)', r'(tumblr)', r'(google)', r'(linkedin)',
                   r'(pinterest)', r'(weibo)', r'(vkontakte)']

matches = df.text_units.str.replace('tweets', 'twitter', flags=re.IGNORECASE).str.extract("|".join(channel_regexes), flags=re.IGNORECASE)
_matches = df['channels'].str.split(';', expand=True)
matches = pd.concat([matches, _matches], axis=1)
df['channels'] = matches.fillna('').agg(set, axis=1).apply(lambda x: list(x))

""" Methodologies """

df['methodologies'] = df.methodologies.str.replace(';', ',')
df['methodologies'] = df.methodologies.str.split(',').apply(lambda x: [y.strip() for y in x if y.strip() != ""])
wp2datasets['methodologies'] = wp2datasets.methodologies.str.split(';').apply(lambda x: [y.strip() for y in x if y.strip() != ""])

filt = (wp2_mappings.wp2_column == 'methodologies') & (wp2_mappings.meteor_uid.notna())

methodologies = wp2_mappings[filt].to_dict(orient='records')

query_string = '''query method($method: string) {
    q(func: uid($method)){ uid _unique_name name } 
}'''

methods_mapping = {}

for method in methodologies:
    res = client.txn(read_only=True).query(
        query_string, variables={'$method': method['meteor_uid']})
    try:
        j = json.loads(res.json)
        methods_mapping[method['wp2_term']] = j['q'][0]['uid']
        methods_mapping[method['wp2_term'].lower()] = j['q'][0]['uid']
    except:
        print('Could not find method:', method['wp2_term'])


""" Text Types """

df['text_units'] = df.text_units.str.replace(',', ';')
df.text_units = df.text_units.fillna('')
df.text_units = df.text_units.apply(lambda x: [t.strip() for t in x.split(";") if t.strip() != ""])

wp2datasets.text_units = wp2datasets.text_units.fillna('')
wp2datasets.text_units = wp2datasets.text_units.apply(lambda x: [t.strip() for t in x.split(";") if t.strip() != ""])


filt = (wp2_mappings.wp2_column == 'text_units') & (wp2_mappings.meteor_term.str.startswith('texttype'))

ttypes = wp2_mappings[filt].to_dict(orient='records')

query_string = '''query textype($texttype: string) {
    q(func: eq(_unique_name, $texttype)){ uid _unique_name name } 
}'''

text_type_mapping = {}

for ttype in ttypes:
    res = client.txn(read_only=True).query(
        query_string, variables={'$texttype': ttype['meteor_term']})
    try:
        j = json.loads(res.json)
        text_type_mapping[ttype['wp2_term']] = j['q'][0]['uid']
        text_type_mapping[ttype['wp2_term'].lower()] = j['q'][0]['uid']
    except:
        print('Could not find text type:', ttype['wp2_term'])


filt = (wp2_mappings.wp2_column == 'text_units') & (wp2_mappings.meteor_term.str.startswith('_:'))

ttypes = wp2_mappings[filt].to_dict(orient='records')

for ttype in ttypes:
    text_type_mapping[ttype['wp2_term']] = ttype["meteor_term"]


""" Resolve DOIs """

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
wp2datasets.doi = wp2datasets.doi.fillna('')

filt = wp2datasets.dgraph_type == 'Tool'

for index, row in wp2datasets[~filt].iterrows():
    doi = row['doi']
    new_entry = {**dataset_template, 
                 '_tmp_unique_name': row['wp2_paper_id'] + '_dataset',
                 'url': row['url'],
                 'doi': doi if doi != '' else None,
                 'description': '',
                'dgraph.type': ['Entry']}
    new_entry['dgraph.type'].append(row['dgraph_type'])
    if row['github'] != '':
        new_entry['github'] = row['github']
    try:
        publication = process_doi(doi, PUBLICATION_CACHE, entry_review_status=ENTRY_REVIEW_STATUS)
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
    # text_types
    new_entry['text_types'] = [{"uid": "_:texttype_citizen"}]
    try:
        for ttype in row['text_units']:
            try:
                new_entry['text_types'].append({'uid': text_type_mapping[ttype]})
            except:
                continue
    except:
        pass
    # tools_used
    # methodologies
    try:
        _methods = []
        for method in row['methodologies']:
            try:
                _methods.append({'uid': methods_mapping[method.lower()]})
            except:
                continue
        new_entry['methodologies'] = _methods
    except:
        pass
    # channels
    
    try:
        new_entry['description'] += 'Sample: ' + row['v16_sample_description']
    except:
        pass
    new_entry['name'] = row['name']
    new_entry['_unique_name'] = 'dataset_' + slugify(new_entry['name'], separator="")
    new_entry['uid'] = '_:' + new_entry['_unique_name']
    wp2_datasets_canonical[row['wp2_paper_id']] = new_entry


save_publication_cache()

""" Publications """

wp2_template = {
    'dgraph.type': ['Entry', 'ScientificPublication'],
    '_date_created': datetime.now().isoformat(),
    'entry_review_status': ENTRY_REVIEW_STATUS,
    '_added_by': {
        'uid': ADMIN_UID,
        '_added_by|timestamp': datetime.now().isoformat()},
}


cppt_entry = {
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
            '_added_by|timestamp': datetime.now().isoformat()}}


entry_template = {'_date_created': datetime.now().isoformat(),
                'entry_review_status': ENTRY_REVIEW_STATUS,
                '_added_by': {
                    'uid': ADMIN_UID,
                    '_added_by|timestamp': datetime.now().isoformat()}
                }

for ttype in wp2_texttypes:
    ttype.update(entry_template)


wp2_canonical = {}

df.doi = df.doi.fillna('')
failed_dois = []
for index, row in df.iterrows():
    doi = row['doi']
    print('Processing:', doi, row['url'])
    new_entry = {**wp2_template, 
                 '_tmp_unique_name': row['original_id'],
                 'url': row['url'],
                 'doi': doi if doi != '' else None,
                 'description': ''}
    # keep track whether the DOI is valid or not
    valid_doi = True
    try:
        publication = process_doi(doi, PUBLICATION_CACHE, entry_review_status=ENTRY_REVIEW_STATUS)
        if not 'title' in publication:
            publication['title'] = row['title']
        new_entry.update(publication)
    except Exception as e:
        publication = None
        print('could not resolve DOI:', doi, e)
        failed_dois.append(doi)
        try:
            doi = DOI_PATTERN.search(row['url'].upper())[0]
            publication = process_doi(doi, PUBLICATION_CACHE, entry_review_status=ENTRY_REVIEW_STATUS)
            new_entry.update(publication)
        except:
            # get rid of bad DOIs
            failed_dois.append(row['url'])
            _ = new_entry.pop('doi')
            valid_doi = False
    if not publication:
        new_entry['title'] = row['title']
        new_entry['date_published'] = datetime(year=int(row['date_published']), month=1, day=1).isoformat(), 
        new_entry['venue'] = row['venue']
        new_entry['_authors_fallback'] = row['authors'].split(', ')
        new_entry['_authors_fallback|sequence'] = {str(i): i for i in range(len(new_entry['_authors_fallback']))}
        valid_doi = False
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
        new_entry['countries'] = []
    try:
        _languages = [language_uid_mapping[l.strip()] for l in row['languages'].split(';') if l.strip() in language_uid_mapping]
        new_entry['languages'] = [{'uid': l} for l in _languages]
    except:
        print('could not resolve countries:', doi)
    try:
        new_entry['geographic_scope'] = row['geographic_scope'].lower()
    except:
        if len(new_entry['countries']) > 1:
            new_entry['geographic_scope'] = 'multinational'
        else:
            new_entry['geographic_scope'] = 'national'
    # text_units
    new_entry['text_types'] = [{"uid": "_:texttype_citizen"}]
    try:
        for ttype in row['text_units']:
            try:
                new_entry['text_types'].append({'uid': text_type_mapping[ttype]})
            except:
                continue
    except:
        pass
    # tools_used
    # methodologies
    try:
        _methods = []
        for method in row['methodologies']:
            try:
                _methods.append({'uid': methods_mapping[method.lower()]})
            except:
                continue
        new_entry['methodologies'] = _methods
    except:
        pass
    # channels
    try:
        _channels = []
        for ch in row['channels']:
            try:
                _channels.append({'uid': channel_uid_mapping[ch]})
            except:
                continue
        if len(_channels) > 0:
            new_entry['channels'] = _channels
    except:
        print('Could not parse channels', row['url'])
    # concepts
    try:
        if "sentiment_scoring" in row['v26_quant_method']:
            new_entry['concept_variables'] = [{'uid': '0x1ae2d'}]
    except:
        pass
    try:
        new_entry['description'] += '\nSample: ' + row['v16_sample_description']
        new_entry['description'] = new_entry['description'].strip()
    except:
        pass
    try:
        try:
            author_name = new_entry['authors'][0]['name']
        except:
            author_name = new_entry['_authors_fallback'][0]
        try:
            title = re.match(r".*?[\?:\.!–]", str(new_entry['title']))[0]
        except:
            title = str(new_entry['title'])
        title = title.replace(':', '').replace('–', '')
        year = datetime.fromisoformat(new_entry['date_published']).year
        name = f'{author_name} ({year}): {title}'
    except:
        name = new_entry['title']
    new_entry['name'] = name
    if valid_doi:
        new_entry['_unique_name'] = 'scientificpublication_' + slugify(doi, separator="")
    else:
        new_entry['_unique_name'] = 'scientificpublication_' + slugify(new_entry['url'].replace('https://', '').replace('http://', ''), separator="")[-64:]
    new_entry['uid'] = '_:' + new_entry['_unique_name']
    try:
        new_entry['datasets_used'] = [{'uid': wp2_datasets_canonical[row['original_id']]['uid']}]
    except:
        pass
    wp2_canonical[row['original_id']] = new_entry

save_publication_cache()


mutation_obj = wp2_texttypes + list(wp2_datasets_canonical.values()) + list(wp2_canonical.values())

p = Path.cwd()

wp2_mutation_json = p / 'data' / 'wp2_mutation.json'

with open(wp2_mutation_json, 'w') as f:
    json.dump(mutation_obj, f, indent=1)

with open(p / 'data' / 'wp2_failed_dois.json', 'w') as f:
    json.dump(failed_dois, f, indent=1)

txn = client.txn()
res = txn.mutate(set_obj=mutation_obj, commit_now=True)

# Deduplicate authors by name

duplicated = get_duplicated_authors()
print('Got', len(duplicated), 'duplicated authors:')
for a in duplicated:
    print('Deduplicating:', a)
    deduplicate_author(a)
