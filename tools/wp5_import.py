"""
    Script to import WP5 data (governments, parliaments and datasets) into Meteor
    Requires master spreadsheet "OPTED Taxonomy.xlsx" as input.
"""
import sys
sys.path.append('.')
import itertools
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from slugify import slugify
import requests
from dateutil import parser as dateparser
import secrets

from tools.countries_language_mapping import get_country_language_mapping, get_country_wikidata_mapping

from tools.migration_helpers import (PUBLICATION_CACHE, WIKIDATA_CACHE, 
                                     client, ADMIN_UID, process_doi, 
                                     save_publication_cache, save_wikidata_cache,
                                     remove_none, safe_clean_doi,
                                     get_duplicated_authors, deduplicate_author)


ENTRY_REVIEW_STATUS = 'accepted'

p = Path.cwd()

# Load Data from Excel sheet
xlsx = p / 'data' / 'OPTED Taxonomy.xlsx'

df = pd.read_excel(xlsx, sheet_name="WP5")
cap_df = pd.read_excel(xlsx, sheet_name="CAP")

# clean columns

df_strings = df.select_dtypes(['object'])
df[df_strings.columns] = df_strings.apply(lambda x: x.str.strip())

cap_df_strings = cap_df.select_dtypes(['object'])
cap_df[cap_df_strings.columns] = cap_df_strings.apply(lambda x: x.str.strip())


""" Get some wikidata mappings for dgraph """

country_wikidata_mapping = get_country_wikidata_mapping()
countries_language_mapping_dgraph = get_country_language_mapping()

""" Get Parliaments and Governments from Wikidata """
df.loc[df.parliament.isna(), 'parliament'] = ""
cap_df.loc[cap_df.parliament.isna(), 'parliament'] = ""


df['parliament'] = df.parliament.apply(lambda x: [y.strip() for y in x.split(';')])
cap_df['parliament'] = cap_df.parliament.apply(lambda x: [y.strip() for y in x.split(';')])


parliaments_wikidata_ids = df.parliament.explode().unique().tolist() + cap_df.parliament.explode().unique().tolist()
parliaments_wikidata_ids = list(set(parliaments_wikidata_ids))
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
    if wikidata_id in WIKIDATA_CACHE:
        wikidata = WIKIDATA_CACHE[wikidata_id]
    else:
        api = 'https://www.wikidata.org/w/api.php'
        params = {'action': 'wbgetentities', #'languages': 'en',
                'format': 'json'}
        params['ids'] = wikidata_id 
        r = requests.get(api, params=params)
        wikidata = r.json()['entities'][wikidata_id]
        WIKIDATA_CACHE[wikidata_id] = wikidata
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

""" Governments """

df.loc[df.government.isna(), 'government'] = ""
cap_df.loc[cap_df.government.isna(), 'government'] = ""

df['government'] = df.government.apply(lambda x: [y.strip() for y in x.split(';')])
cap_df['government'] = cap_df.government.apply(lambda x: [y.strip() for y in x.split(';')])

governments_wikidata_ids = df.government.explode().unique().tolist() + cap_df.government.explode().unique().tolist()
governments_wikidata_ids = list(set(governments_wikidata_ids))

governments_wikidata_ids.remove('')

canonical_governments = {}

government_template = {
    'dgraph.type': ['Entry', 'Government'],
    '_date_created': datetime.now().isoformat(),
    'entry_review_status': ENTRY_REVIEW_STATUS,
    '_added_by': {
        'uid': ADMIN_UID,
        '_added_by|timestamp': datetime.now().isoformat()},
}


for wikidata_id in governments_wikidata_ids:
    if wikidata_id in WIKIDATA_CACHE:
        wikidata = WIKIDATA_CACHE[wikidata_id]
    else:
        api = 'https://www.wikidata.org/w/api.php'
        params = {'action': 'wbgetentities', #'languages': 'en',
                'format': 'json'}
        params['ids'] = wikidata_id 
        r = requests.get(api, params=params)
        wikidata = r.json()['entities'][wikidata_id]
        WIKIDATA_CACHE[wikidata_id] = wikidata
    new_government = {**government_template, 'wikidata_id': wikidata_id}
    # try to get native label first
    try:
        new_government['name'] = wikidata['claims']['P1705'][0]['mainsnak']['datavalue']['value']['text']
    except:
        new_government['name'] = wikidata['labels']['en']['value']
    new_government['name@en'] = wikidata['labels']['en']['value']
    try:
        new_government['alternate_names'] = [n['value'] for n in wikidata['aliases']['en']]
    except:
        pass
    try:
        new_government['description'] = wikidata['descriptions']['en']['value']
    except:
        pass
    try:
        new_government['hdl'] = wikidata['claims']['P1184'][0]['mainsnak']['datavalue']['value']
    except:
        pass
    try:
        country_wikidata = wikidata['claims']['P17'][0]['mainsnak']['datavalue']['value']['id']
    except: # P1001: aplies to jurisdiction
        country_wikidata = wikidata['claims']['P1001'][0]['mainsnak']['datavalue']['value']['id']
    country_uid = country_wikidata_mapping[country_wikidata]
    new_government['country'] = {'uid': country_uid}
    new_government['languages'] = countries_language_mapping_dgraph[country_uid]
    try:
        new_government['url'] = wikidata['claims']['P856'][0]['mainsnak']['datavalue']['value']
    except:
        pass
    # get country code
    query_string = 'query countryCode ($u: string) { q(func: uid($u)) { iso_3166_1_2 }}'
    res = client.txn().query(query_string, variables={'$u': country_uid})
    j = json.loads(res.json)
    country_code = j['q'][0]['iso_3166_1_2']
    new_government['_unique_name'] = 'government_' + country_code + '_' + slugify(new_government['name'], separator="")
    new_government['uid'] = '_:' + new_government['_unique_name']
    canonical_governments[wikidata_id] = new_government


# Manually fix European Commission
canonical_governments['Q8880']['_unique_name'] = "government_eu_europeancommission"
canonical_governments['Q8880']['uid'] = "_:government_eu_europeancommission"
query_string = '{ eu(func: eq(wikidata_id, "Q458")) { uid } french(func: eq(wikidata_id, "Q150")) { uid } english(func: eq(wikidata_id, "Q1860")) { uid } german(func: eq(wikidata_id, "Q188")) { uid } }'
res = client.txn().query(query_string)
j = json.loads(res.json)
canonical_governments['Q8880']['country'] = {'uid': j['eu'][0]['uid']}
canonical_governments['Q8880']['languages'] = [{'uid': j['french'][0]['uid']},
                                               {'uid': j['english'][0]['uid']},
                                               {'uid': j['german'][0]['uid']}]


""" Text Types """

wp5_texttypes_json = p / 'data' / 'wp5texttypes.json'

with open(wp5_texttypes_json) as f:
    wp5_texttypes = json.load(f)

for entry in wp5_texttypes:
    entry['_date_created'] = datetime.now().isoformat()
    entry['entry_review_status'] = ENTRY_REVIEW_STATUS
    entry['_added_by'] = {'uid': ADMIN_UID,
                         '_added_by|timestamp': datetime.now().isoformat()}
# get manifesto from WP4
query_string = '{ manifesto(func: eq(_unique_name, "texttype_manifesto")) { uid } }'
res = client.txn().query(query_string)
j = json.loads(res.json)

text_type_mapping = {'Legislative speech': {'uid': '_:texttype_legislativespeech'},
                     'Questions': {'uid': '_:texttype_question'},
                     'Interpellations': {'uid': '_:texttype_interpelletion'},
                     'Legislative document': {'uid': '_:texttype_legislativedocument'},
                     'Laws': {'uid': '_:texttype_law'},
                     'Bills': {'uid': '_:texttype_bill'},
                     'Amendments': {'uid': '_:texttype_amendment'},
                     'Manifesto': j['manifesto'][0]}

df.loc[df.text_type.isna(), 'text_type'] = ""
df['text_types'] = df.text_type.apply(lambda x: [text_type_mapping[y.strip()] for y in x.split(';')])


""" Meta Vars """

df.loc[df.meta_vars.isna(), 'meta_vars'] = ""
cap_df.loc[cap_df.meta_vars.isna(), 'meta_vars'] = ""

query_string = """{
    metavariable_date(func: eq(_unique_name, "metavariable_date")) { uid }
    metavariable_documenttitle(func: eq(_unique_name, "metavariable_documenttitle")) { uid }
    metavariable_year(func: eq(_unique_name, "metavariable_year")) { uid }
    metavariable_speakername(func: eq(_unique_name, "metavariable_speakername")) { uid }
    metavariable_datasource(func: eq(_unique_name, "metavariable_datasource")) { uid }
    metavariable_partyname(func: eq(_unique_name, "metavariable_partyname")) { uid }
    metavariable_language(func: eq(_unique_name, "metavariable_language")) { uid }
}"""

res = client.txn().query(query_string)

j = json.loads(res.json)


metavars_lookup = {'date': {'uid': j['metavariable_date'][0]['uid']},
                   'date (datum)': {'uid': j['metavariable_date'][0]['uid']},
                   'date of document': {'uid': j['metavariable_date'][0]['uid']},
                   'meeting date': {'uid': j['metavariable_date'][0]['uid']},
                   'title': {'uid': j['metavariable_documenttitle'][0]['uid']},
                   'year': {'uid': j['metavariable_year'][0]['uid']},
                   'speaker': {'uid': j['metavariable_speakername'][0]['uid']},
                   "speaker's name": {'uid': j['metavariable_speakername'][0]['uid']},
                   'source': {'uid': j['metavariable_datasource'][0]['uid']},
                   'party': {'uid': j['metavariable_partyname'][0]['uid']},
                   'language': {'uid': j['metavariable_language'][0]['uid']},
                   'publication language': {'uid': j['metavariable_language'][0]['uid']},
                   'languages': {'uid': j['metavariable_language'][0]['uid']},
                   'lang': {'uid': j['metavariable_language'][0]['uid']},
                   }


df['meta_variables'] = df.meta_vars.apply(lambda x: [metavars_lookup[y.strip().lower()] for y in x.split(',') if y.strip().lower() in metavars_lookup])


""" File Formats """

df.loc[df.file_format.isna(), 'file_format'] = ""

query_string = """{
    fileformat_rtf(func: eq(_unique_name, "fileformat_rtf")) { uid }
    fileformat_html(func: eq(_unique_name, "fileformat_html")) { uid }
    fileformat_rds(func: eq(_unique_name, "fileformat_rds")) { uid }
    fileformat_xml(func: eq(_unique_name, "fileformat_xml")) { uid }
    fileformat_txt(func: eq(_unique_name, "fileformat_txt")) { uid }
    fileformat_pdf(func: eq(_unique_name, "fileformat_pdf")) { uid }
    fileformat_doc(func: eq(_unique_name, "fileformat_doc")) { uid }
    fileformat_eaf(func: eq(_unique_name, "fileformat_eaf")) { uid }
    fileformat_rdata(func: eq(_unique_name, "fileformat_rdata")) { uid }
    fileformat_tsvtab(func: eq(_unique_name, "fileformat_tsvtab")) { uid }
    fileformat_csv(func: eq(_unique_name, "fileformat_csv")) { uid }
    fileformat_rdf(func: eq(_unique_name, "fileformat_rdf")) { uid }
    fileformat_odt(func: eq(_unique_name, "fileformat_odt")) { uid }
    fileformat_xls(func: eq(_unique_name, "fileformat_xls")) { uid }
    fileformat_tmx(func: eq(_unique_name, "fileformat_tmx")) { uid }
}"""

res = client.txn().query(query_string)

j = json.loads(res.json)


fileformats_lookup = {'rtf': {'uid': j['fileformat_rtf'][0]['uid']},
                   'html': {'uid': j['fileformat_html'][0]['uid']},
                   'rds': {'uid': j['fileformat_rds'][0]['uid']},
                   'xml': {'uid': j['fileformat_xml'][0]['uid']},
                   'txt': {'uid': j['fileformat_txt'][0]['uid']},
                   'info': {'uid': j['fileformat_txt'][0]['uid']},
                   'pdf': {'uid': j['fileformat_pdf'][0]['uid']},
                   'doc': {'uid': j['fileformat_doc'][0]['uid']},
                   "eaf": {'uid': j['fileformat_eaf'][0]['uid']},
                   'rdata': {'uid': j['fileformat_rdata'][0]['uid']},
                   'tab': {'uid': j['fileformat_tsvtab'][0]['uid']},
                   'csv': {'uid': j['fileformat_csv'][0]['uid']},
                   'rdf': {'uid': j['fileformat_rdf'][0]['uid']},
                   'odt': {'uid': j['fileformat_odt'][0]['uid']},
                   'xls': {'uid': j['fileformat_xls'][0]['uid']},
                   'tmx': {'uid': j['fileformat_tmx'][0]['uid']},
                   }


df['file_formats'] = df.file_format.apply(lambda x: [fileformats_lookup[y.strip().lower()] for y in x.split(',') if y.strip().lower() in fileformats_lookup])

""" Countries """


query_string = '''query countries($country: string) {
    q(func: match(name, $country, 2)) @filter(type(Country) OR type(Multinational)) { uid _unique_name name iso_3166_1_2 } 
}'''

countries = list(set(df.countries.unique().tolist() + cap_df.countries.unique().tolist()))

country_uid_mapping = {}
country_unique_name_mapping = {}
country_code_mapping = {}

for country_name in countries:
    country = client.txn(read_only=True).query(
        query_string, variables={'$country': country_name})
    j = json.loads(country.json)
    country_uid_mapping[country_name] = j['q'][0]['uid']
    country_unique_name_mapping[country_name] = j['q'][0]['_unique_name']
    try:
        country_code_mapping[country_name] = j['q'][0]['iso_3166_1_2']
    except:
        country_code_mapping[country_name] = j['q'][0]['name'].lower()
        


""" Resolve DOIs """


# get all entries with DOI

df.doi = df.doi.apply(safe_clean_doi)

dois = df[~df.doi.isna()].doi.unique()

authors = {}
publication_info = {}
failed = []

print('Resolving DOIs and retrieving author information ...')

for doi in dois:
    try:
        print(doi)
        publication_info[doi] = process_doi(doi, PUBLICATION_CACHE, entry_review_status=ENTRY_REVIEW_STATUS)
        authors[doi] = publication_info[doi]['authors']
        # publication_info[doi] = crossref(doi, crossref_cache)
    except Exception as e:
        print('Problem at:', doi, e)
        failed.append(doi)

save_publication_cache()

""" Dataframe to json """

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
    # "conditions_of_access": "registration", # -> access (to_lower!)
    "fulltext_available": False, # -> contains_full_text (as bool)
    "geographic_scope": "national", # -> region
    # "languages": "", # -> languages
    # "text_types": "", # -> text.type
    # "file_formats": "", # -> file_format
    # "meta_variables": "", # -> meta_vars
    # "concept_variables": "", # -> concept_vars
    # "sources_included": '', # -> political_party
    # "countries": "<Austria>", 
    # "temporal_coverage_start": "2002", # -> start_date
    # "temporal_coverage_end": "2002", # -> end_date
}

""" smaller preparations"""

df.loc[df.dgraph_type.isna(), "dgraph_type"] = "Dataset"

wp5_datasets = df.fillna('').groupby("url").agg(list).to_dict(orient='index')

clean_wp5 = []

# keep track on unique names
_unique_names = []

for dataset_url, dataset in wp5_datasets.items():
    for v in dataset.values():
        remove_none(v)
    new_dataset = {**sample_dataset}
    new_dataset['name'] = dataset['name'][0]
    new_dataset['uid'] = '_:' + slugify(dataset_url, separator="_")
    new_dataset['dgraph.type'] = dataset['dgraph_type'] + ['Entry']
    # new_dataset['countries'] = [{'uid': country_uid_mapping[c]} for c in dataset['countries']]
    try:
        doi = dataset['doi'][0] if dataset['doi'][0].strip() != '' else None
        new_dataset['doi'] = doi
        if doi in publication_info:
            new_dataset['date_published'] = str(publication_info[doi]['date_published'])
            new_dataset['venue'] = publication_info[doi]['venue']
            new_dataset['paper_kind'] = publication_info[doi]['paper_kind']
    except:
        pass
    new_dataset['url'] = dataset_url
    # new_dataset['description'] = dataset['description'][0]
    if 'doi' in new_dataset and new_dataset['doi'] is not None and new_dataset['doi'] in authors:
        new_dataset['authors'] = authors[new_dataset['doi']]
    else:
        try:
            new_dataset['_authors_fallback'] = [a.strip() for a in dataset['authors'][0].split(";")]
            new_dataset['_authors_fallback|sequence'] = {str(i): i for i in range(len(new_dataset['authors']))}
        except:
            pass
    try:
        new_dataset['conditions_of_access'] = dataset['user_access'][0].lower()
    except:
        new_dataset['conditions_of_access'] = "NA"
    new_dataset['fulltext_available'] = bool(dataset['fulltext_available'][0])
    new_dataset['geographic_scope'] = [t.lower() for t in dataset['geographic_scope']]
    try:
        new_dataset['hdl'] = dataset['hdl'][0]
    except:
        pass
    # looks complicated:
    # get UID for country then get languages associated for country
    _countries = [country_uid_mapping[c] for c in dataset['countries']]
    languages = []
    for c in _countries:
        try:
            languages += countries_language_mapping_dgraph[c]
        except:
            print(f'Could not find language for country <{c}>')
    new_dataset['languages'] = languages
    new_dataset['text_types'] = list(itertools.chain(*dataset['text_types']))
    new_dataset['file_formats'] = list(itertools.chain(*dataset['file_formats']))
    new_dataset['meta_variables'] = list(itertools.chain(*dataset['meta_variables']))
    sources_included = [{'uid': canonical_parliaments[p]['uid']} for p in list(itertools.chain(*dataset['parliament'])) if p in canonical_parliaments]
    sources_included += [{'uid': canonical_governments[g]['uid']} for g in list(itertools.chain(*dataset['government'])) if g in canonical_governments]
    new_dataset['sources_included'] = sources_included
    try:
        new_dataset['temporal_coverage_start'] = str(int(min(dataset['temporal_coverage_start'])))
        if new_dataset['temporal_coverage_start'] in ['ongoing', '?']:
             new_dataset['temporal_coverage_start'] = None
    except:
        pass
    try:
        new_dataset['temporal_coverage_end'] = str(int(max(dataset['temporal_coverage_end'])))
        if new_dataset['temporal_coverage_end'] in ['ongoing', '?']:
            new_dataset['temporal_coverage_end'] = None
    except:
        pass
    new_dataset_countries = []
    for i, dataset_country_list in enumerate(dataset['countries']):
        dataset_country_list = [country_uid_mapping[c.strip()] for c in dataset_country_list.split(',')]
        for dataset_country in dataset_country_list:
            try:
                new_dataset_countries.append({'uid': dataset_country, 
                                'countries|temporal_coverage_start': int(dataset['temporal_coverage_start'][i]),
                                'countries|temporal_coverage_end': int(dataset['temporal_coverage_end'][i])})
            except:
                pass
    new_dataset['countries'] = new_dataset_countries
    # assert unique name not already taken
    _unique_name = dataset['dgraph_type'][0].lower() + '_' + country_code_mapping[dataset['countries'][0]] + '_' + slugify(new_dataset['name'], separator="")
    if _unique_name not in _unique_names:
        new_dataset['_unique_name'] = _unique_name
        _unique_names.append(_unique_name)
    else:
        _unique_name += secrets.token_urlsafe(6)
        new_dataset['_unique_name'] = _unique_name
        _unique_names.append(_unique_name)
    try:
        new_dataset['_legacy_id'] = dataset['original_id']
    except:
        pass

    clean_wp5.append(new_dataset)

""" CAP Comparative Agendas Project """

# Only principal investigators, in alphabetical order

cap_authors_ids = [
                   'A5042975485', # Stefaan Walgrave, Belgium
                   'A5005872138', # Daniela Širinić, Croatia
                   'A5036452910', # Christoffer Green-Pedersen, Denmark
                   'A5035906707', # Peter B. Mortensen, Denmark
                   'A5040846387', # Petya Alexandrova, European Union
                   'A5019366355', # Sebastiaan Princen, European Union
                   'A5079553683', # Marcello Carammia, European Union
                   'A5051442026', # Emiliano Grossman, France
                   'A5042265529', # Christian Breunig, Germany
                   'A5020080306', # Miklós Sebők, Hungary
                   'A5057176896', # Zsolt Boda, Hungary
                   'A5019287978', # Conor Little, Ireland
                   'A5028913176', # Amnon Cavari, Israel
                   'A5005044683', # Maoz Rosenthal, Israel
                   'A5033970527', # Ilana Shpaizman, Israel 
                   'A5087287508', # Enrico Borghetto, Italy
                   'A5079553683', # Marcello Carammia, Italy
                   'A5030370639', # Federico Russo, Italy
                   'A5021118986', # Arco Timmermans, Nederlands
                   'A5080131973', # Gerard Breeman, Nederlands
                   'A5033691267', # Łukasz Wordliczek, Poland
                   'A5066211324', # Ana Maria Belchior, Portugal
                   'A5087287508', # Enrico Borghetto, Portugal
                   'A5057507122', # Catherine Moury, Portugal
                   'A5066975041', # Laura Chaqués Bonafont, Spain
                   'A5087496824', # Pascal Sciarini, Switzerland
                   'A5068843325', # Frédéric Varone, Switzerland
                   'A5012934179', # Shaun Bevan, UK
                   ]

cap_authors = []
print('Getting CAP authors ...')
for i, open_alex in enumerate(cap_authors_ids):
    print('Author:', open_alex)
    query_string = """query lookupAuthor ($openalex: string) 
    {
        q(func: eq(openalex, $openalex)) {
                uid
        }
    }"""
    res = client.txn(read_only=True).query(query_string, variables={'$openalex': open_alex})
    j = json.loads(res.json)
    if len(j['q']) == 0:
        if open_alex in PUBLICATION_CACHE:
            author_details = PUBLICATION_CACHE[open_alex]
        else:
            api = "https://api.openalex.org/people/"
            r = requests.get(api + open_alex, params={'mailto': "info@opted.eu"})
            author_details = r.json() 
            PUBLICATION_CACHE[open_alex] = author_details
        author_entry = {'uid': '_:' + slugify(open_alex, separator="_"),
                        '_unique_name': 'author_' + slugify(open_alex, separator=""),
                        'entry_review_status': ENTRY_REVIEW_STATUS,
                        'openalex': open_alex,
                        'name': author_details['display_name'],
                        '_date_created': datetime.now().isoformat(),
                        'authors|sequence': i,
                        '_added_by': {
                            'uid': ADMIN_UID,
                            '_added_by|timestamp': datetime.now().isoformat()},
                        'dgraph.type': ['Entry', 'Author']
                        }
        if author_details['ids'].get("orcid"):
            author_entry['orcid'] = author_details['ids']['orcid'].replace('https://orcid.org/', '')
        try:
            if author_details['last_known_institution']['display_name']:
                author_entry['affiliations'] = [author_details['last_known_institution']['display_name']]
        except:
            pass
    else:
        author_entry = {'uid': j['q'][0]['uid']}
    cap_authors.append(author_entry)

cap_metavars = cap_df.meta_vars.apply(lambda x: [y.strip().lower() for y in x.split(',')]).explode().unique()
cap_metavariables = [metavars_lookup[v] for v in cap_metavars.tolist() if v in metavars_lookup]

cap_df['countries_uid'] = cap_df.countries.replace(country_uid_mapping)

cap_countries = {c: {'uid': c} for c in cap_df['countries_uid'].unique().tolist()}
cap_df.temporal_coverage_start = cap_df.temporal_coverage_start.astype(int)
cap_df.temporal_coverage_end = cap_df.temporal_coverage_end.astype(int)
cap_start = cap_df.groupby("countries_uid").agg(list).temporal_coverage_start.apply(min).to_dict()
cap_end = cap_df.groupby("countries_uid").agg(list).temporal_coverage_end.apply(max).to_dict()

for k in cap_countries:
    cap_countries[k]['countries|temporal_coverage_start'] = datetime.strptime(str(cap_start[k]), "%Y").isoformat()
    cap_countries[k]['countries|temporal_coverage_end'] = datetime.strptime(str(cap_end[k]), "%Y").isoformat()

cap_df.loc[cap_df.parties.isna(), 'parties'] = "" 
cap_parties_tmp_names = cap_df.parties.apply(lambda x: [y.strip().lower() for y in x.split(';')]).explode().unique().tolist()
cap_parties_tmp_names.remove('')
query_string = """query party($party: string) {
    q(func: eq(_tmp_unique_name, $party)) { uid }
}"""

parties_lookup = {}

for party in cap_parties_tmp_names:
    try:
        res = client.txn().query(query_string, variables={'$party': party})
        j = json.loads(res.json)['q'][0]
        parties_lookup[party] = j['uid']
    except:
        print('couldnt find party:', party)

filt = cap_df.parties != ""

cap_parties = []

for index, row in cap_df[filt].iterrows():
    parties = [p.lower().strip() for p in row['parties'].split(';')]
    temporal_coverage_start = str(row['temporal_coverage_start'])
    temporal_coverage_end = str(row['temporal_coverage_end'])
    for p in parties:
        try:
            party = {'uid': parties_lookup[p],
                    'sources_included|temporal_coverage_start': datetime.strptime(temporal_coverage_start, "%Y").isoformat(),
                    'sources_included|temporal_coverage_end': datetime.strptime(temporal_coverage_end, "%Y").isoformat()}
            cap_parties.append(party)
        except:
            continue

sources_included = [{'uid': canonical_parliaments[p]['uid']} for p in cap_df.parliament.explode().unique().tolist() if p in canonical_parliaments]
sources_included += [{'uid': canonical_governments[g]['uid']} for g in cap_df.government.explode().unique().tolist() if g in canonical_governments]
sources_included += cap_parties

cap_entry = {
    'name': 'Comparative Agendas Project',
    '_unique_name': 'dataset_global_comparative_agendas_project',
    'uid': '_:dataset_global_comparative_agendas_project',
    'alternate_names': ['CAP', 
                        'French Policy Agendas Project', 
                        'German Comparative Agenda',
                        'Agenda Dynamics in Spain',
                        'UK Policy Agendas Project'],
    'url': 'https://www.comparativeagendas.net/',
    'description': 'The Comparative Agendas Project (CAP) assembles and codes information on the policy processes of governments from around the world. [Authors listed in alphabetical order]',
    'dgraph.type': ['Entry', 'Dataset'],
    'authors': cap_authors,
    'conditions_of_access': 'free',
    'fulltext_available': True,
    'geographic_scope': ['national', 'supranational'],
    'text_types': list(text_type_mapping.values()),
    'file_formats': [fileformats_lookup['csv']],
    'meta_variables': cap_metavariables,
    'temporal_coverage_start': str(int(cap_df.temporal_coverage_start.min())),
    'temporal_coverage_end': str(int(cap_df.temporal_coverage_end.max())),
    'countries': list(cap_countries.values()),
    'sources_included': sources_included,
    '_date_created': datetime.now().isoformat(),
    'entry_review_status': ENTRY_REVIEW_STATUS,
    '_added_by': {
        'uid': ADMIN_UID,
        '_added_by|timestamp': datetime.now().isoformat()},
}

mutation_obj = list(canonical_parliaments.values()) + clean_wp5 + wp5_texttypes + list(canonical_governments.values())
mutation_obj.append(cap_entry)

txn = client.txn()
res = txn.mutate(set_obj=mutation_obj, commit_now=True)

p = Path.cwd()

wp5_mutation_json = p / 'data' / 'wp5_mutation.json'

with open(wp5_mutation_json, 'w') as f:
    json.dump(mutation_obj, f, indent=1)


save_publication_cache()

save_wikidata_cache()

# Deduplicate authors by name

duplicated = get_duplicated_authors()
print('Got', len(duplicated), 'duplicated authors:')
for a in duplicated:
    print('Deduplicating:', a)
    deduplicate_author(a)
