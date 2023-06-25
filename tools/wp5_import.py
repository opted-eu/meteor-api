"""
    Script to import WP5 data (governments, parliaments and datasets) into Meteor
    Requires master spreadsheet "OPTED Taxonomy.xlsx" as input.
"""
import sys
sys.path.append('.')
import itertools
import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import date, datetime
import pydgraph
from slugify import slugify
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
    if wikidata_id in wikidata_cache:
        wikidata = wikidata_cache[wikidata_id]
    else:
        api = 'https://www.wikidata.org/w/api.php'
        params = {'action': 'wbgetentities', #'languages': 'en',
                'format': 'json'}
        params['ids'] = wikidata_id 
        r = requests.get(api, params=params)
        wikidata = r.json()['entities'][wikidata_id]
        wikidata_cache[wikidata_id] = wikidata
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

df['government'] = df.government.apply(lambda x: [y.strip() for y in x.split(';')])

governments_wikidata_ids = df.government.explode().unique().tolist()
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
    if wikidata_id in wikidata_cache:
        wikidata = wikidata_cache[wikidata_id]
    else:
        api = 'https://www.wikidata.org/w/api.php'
        params = {'action': 'wbgetentities', #'languages': 'en',
                'format': 'json'}
        params['ids'] = wikidata_id 
        r = requests.get(api, params=params)
        wikidata = r.json()['entities'][wikidata_id]
        wikidata_cache[wikidata_id] = wikidata
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

with open(wikidata_cache_file, "w") as f:
    json.dump(wikidata_cache, f)


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

text_type_mapping = {'Legislative speech': {'uid': '_:texttype_legislativespeech'},
                     'Questions': {'uid': '_:texttype_question'},
                     'Interpellations': {'uid': '_:texttype_interpelletion'},
                     'Legislative document': {'uid': '_:texttype_legislativedocument'},
                     'Laws': {'uid': '_:texttype_law'},
                     'Bills': {'uid': '_:texttype_bill'},
                     'Amendments': {'uid': '_:texttype_amendment'}}

df.loc[df.text_type.isna(), 'text_type'] = ""
df['text_types'] = df.text_type.apply(lambda x: [text_type_mapping[y.strip()] for y in x.split(';')])

""" Meta Vars """

df.loc[df.meta_vars.isna(), 'meta_vars'] = ""

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
                   #"eaf": {'uid': j['fileformat_eaf'][0]['uid']},
                   'rdata': {'uid': j['fileformat_rdata'][0]['uid']},
                   'tab': {'uid': j['fileformat_tsvtab'][0]['uid']},
                   'csv': {'uid': j['fileformat_csv'][0]['uid']},
                   #'rdf': {'uid': j['fileformat_rdf'][0]['uid']},
                   'odt': {'uid': j['fileformat_odt'][0]['uid']},
                   'xls': {'uid': j['fileformat_xls'][0]['uid']},
                   #'tmx': {'uid': j['fileformat_tmx'][0]['uid']},
                   }


df['file_formats'] = df.file_format.apply(lambda x: [fileformats_lookup[y.strip().lower()] for y in x.split(',') if y.strip().lower() in fileformats_lookup])

""" Countries """


query_string = '''query countries($country: string) {
    q(func: match(name, $country, 2)) @filter(type(Country) OR type(Multinational)) { uid _unique_name name iso_3166_1_2 } 
}'''

countries = df.countries.unique().tolist()

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
        else:
            author_entry = {'uid': j['q'][0]['uid']}
        authors.append(author_entry)
    return authors


def crossref(doi: str, cache):
    # clean input string
    doi = doi.replace("https://doi.org/", "")
    doi = doi.replace("http://doi.org/", "")
    doi = doi.replace("doi.org/", "")

    if doi in cache:
        publication = cache[doi]
    else:
        api = 'https://api.crossref.org/works/'
        r = requests.get(api + doi)
        if r.status_code != 200:
            r.raise_for_status()
        publication = r.json()

        if publication['status'] != 'ok':
            raise Exception
        publication = publication['message']
        cache[doi] = publication

    result = {'doi': doi}

    result['venue'] = publication.get('container-title')
    if isinstance(result['venue'], list):
        result['venue'] = result['venue'][0]
    result['title'] = publication.get('title')

    if isinstance(result['title'], list):
        result['title'] = result['title'][0]

    result['paper_kind'] = publication.get('type')

    if publication.get('created'):
        result['date_published'] = dateparser.parse(publication['created']['date-time']).isoformat()

    if publication.get('link'):
        result['url'] = publication['link'][0]['URL']
    
    return result


# get all entries with DOI

df.doi = df.doi.str.replace('https://doi.org/', '', regex=False)

dois = df[~df.doi.isna()].doi.unique()

authors = {}
publication_info = {}
failed = []

print('Retrieving Authors from OpenAlex ...')

for doi in dois:
    try:
        authors[doi] = resolve_openalex(doi, author_cache)
        # publication_info[doi] = crossref(doi, crossref_cache)
    except Exception as e:
        print(doi, e)
        failed.append(doi)


with open(author_cache_file, "w") as f:
    json.dump(author_cache, f)


with open(crossref_cache_file, "w") as f:
    json.dump(crossref_cache, f)

""" Dataframe to json """

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
            new_dataset['date_published'] = publication_info[doi]['date_published']
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
        new_dataset['temporal_coverage_start'] = int(min(dataset['temporal_coverage_start']))
        if new_dataset['temporal_coverage_start'] in ['ongoing', '?']:
             new_dataset['temporal_coverage_start'] = None
    except:
        pass
    try:
        new_dataset['temporal_coverage_end'] = int(max(dataset['temporal_coverage_end']))
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
    new_dataset['_unique_name'] = dataset['dgraph_type'][0].lower() + '_' + country_code_mapping[dataset['countries'][0]] + '_' + slugify(new_dataset['name'], separator="")

    clean_wp5.append(new_dataset)


mutation_obj = list(canonical_parliaments.values()) + clean_wp5 + wp5_texttypes

txn = client.txn()
res = txn.mutate(set_obj=mutation_obj, commit_now=True)

# wp5_mutation_json = p / 'data' / 'wp5_mutation.json'

# with open(wp5_mutation_json, 'w') as f:
#     json.dump(mutation_obj, f, indent=1)