# Script for Migrating WP3 Schema to new Schema
# Requires DGraph v23.0.0

import sys
from os.path import dirname
sys.path.append(dirname(sys.path[0]))

import pydgraph
from flaskinventory.main.model import Schema
import json
import math
from datetime import datetime
from slugify import slugify
import requests
from pathlib import Path

client_stub = pydgraph.DgraphClientStub('localhost:9080')
client = pydgraph.DgraphClient(client_stub)

ENTRY_REVIEW_STATUS = "accepted"

p = Path.cwd()

print('Loading Schema from model...')

# Apply new schema (after loading backup)
schema = Schema.generate_dgraph_schema()

# Add index for temporary unique names (drop later)
schema += "\n_tmp_unique_name: [string] @index(exact) ."

print('Setting Schema to DGraph')
# Set schema
client.alter(pydgraph.Operation(schema=schema))

""" Delete Rejected Entries """

print("Deleting rejected entries...")

query = """{ q(func: eq(entry_review_status, ["rejected", "deleted"])) {
			u as uid
  	}
}"""

delete = """
uid(u) * * .
uid(u) <name> * .
uid(u) <unique_name> * .
uid(u) <_date_created> * .
uid(u) <_added_by> * .
uid(u) <_edited_by> * .
uid(u) <_reviewed_by> * .
uid(u) <entry_review_status> * .
uid(u) <geographic_scope> * .
uid(u) <party_affiliated> * .
uid(u) <publication_kind> * .
uid(u) <special_interest> * .
uid(u) <publication_cycle> * .
uid(u) <contains_ads> * .
uid(u) <audience_size> * .
uid(u) <channel> * .
uid(u) <countries> * .
uid(u) <date_founded> * .
uid(u) <date_modified> * .
uid(u) <_languages_tmp> * .
uid(u) <identifier> * .    
uid(u) <input_file_formats> * .
uid(u) <output_file_formats> * .
uid(u) <language_independent> * .
uid(u) <_programming_languages_tmp> * .
uid(u) <website_comments_allowed> * .
uid(u) <geographic_scope_subunit> * .
uid(u) <graphical_user_interface> * .
uid(u) <publication_cycle_weekday> * .
uid(u) <website_comments_registration> * .
uid(u) <owns> * .
uid(u) <pypi> * .
uid(u) <cran> * .
uid(u) <conditions_of_access> * .
uid(u) <github> * .
uid(u) <address> * .
uid(u) <_authors_fallback> * .
uid(u) <author_validated> * .
uid(u) <doi> * .
uid(u) <url> * .
uid(u) <channel_comments> * .
uid(u) <sources_included> * .
uid(u) <special_interest> * .
uid(u) <affiliation> * .
uid(u) <verified_account> * .
uid(u) <publication_cycle> * .
uid(u) <validation_corpus> * .
uid(u) <entry_notes> * .
uid(u) <file_formats> * .
uid(u) <opensource> * .
uid(u) <alternate_names> * .
uid(u) <conditions_of_access> * .
uid(u) <concept_variables> * .
uid(u) <country_code> * .
uid(u) <iso_3166_1_2> * .
uid(u) <audience_size> * .
uid(u) <channel_feeds> * .
uid(u) <payment_model> * .
uid(u) <topical_focus> * .
uid(u) <_account_status> * .
uid(u) <address> * .
uid(u) <epaper_available> * .
uid(u) <location_point> * .
uid(u) <ownership_kind> * .
uid(u) <date_published> * .
uid(u) <countries> * .
uid(u) <defunct> * .
uid(u) <date_founded> * .
uid(u) <venue> * .
uid(u) <license> * .
uid(u) <related_news_sources> * .
uid(u) <designed_for> * .
uid(u) <temporal_coverage_end> * .
uid(u) <fulltext> * .
uid(u) <platforms> * .
uid(u) <used_for> * .
uid(u) <employees> * .
uid(u) <is_person> * .
uid(u) <_materials_tmp> * .
uid(u) <meta_variables> * .
uid(u) <publishes> * .
uid(u) <paper_kind> * .
uid(u) <temporal_coverage_start> * .
uid(u) <text_units> * .
uid(u) <wikidata_id> * .
uid(u) <address_geo> * .
uid(u) <identifier> * .
uid(u) <description> * .
"""


txn = client.txn()

mutation = txn.create_mutation(del_nquads=delete)
request = txn.create_request(query=query, mutations=[mutation], commit_now=True)
txn.do_request(request)

""" Get UID of Admin User """

query_string = '{ q(func: eq(email, "wp3@opted.eu")) { uid } }'


res = client.txn().query(query_string)

j = json.loads(res.json)['q']

ADMIN_UID = j[0]['uid']


""" Migrate Types """

print('Migrating Datasets and Corpora...')

""" text types """

# Dataset, Corpus, and Archives

query = """{
  c as var(func: type(Corpus))
  d as var(func: type(Dataset))
}"""

nquad = """uid(c) <fulltext_available> "true" .
            uid(c) <dgraph.type> "Dataset" .
            uid(d) <fulltext_available> "false" .
        """

delete = """uid(c) <dgraph.type> "Corpus" ."""

txn = client.txn()

mutation = txn.create_mutation(set_nquads=nquad, del_nquads=delete)
request = txn.create_request(query=query, mutations=[mutation], commit_now=True)
txn.do_request(request)

# News Sources

print('Migrating News Sources ...')


query = """{
  s as var(func: type(Source))
}"""

nquad = """uid(s) <dgraph.type> "NewsSource" . """

delete = """uid(s) <dgraph.type> "Source" ."""

txn = client.txn()

mutation = txn.create_mutation(set_nquads=nquad, del_nquads=delete)
request = txn.create_request(query=query, mutations=[mutation], commit_now=True)
txn.do_request(request)

# Journalistic Brands

print('Generating Journalistic Brands ...')

query_total_entries = """
{
	sources(func: type("NewsSource")) @filter(eq(entry_review_status, "accepted") or eq(entry_review_status, "pending")) {
        total: count(uid)
    }
} """

query_sources = """
query get_sources($maximum: int, $offset: int)
{
	sources(func: type("NewsSource"), first: $maximum, offset: $offset) @filter(eq(entry_review_status, "accepted") or eq(entry_review_status, "pending")) {
        uid name unique_name wikidata_id 
        countries { uid }
        subnational_scope { uid }
        channel { uid unique_name } 
        related_news_sources { 
            uid unique_name channel { unique_name } 
            countries { uid }
            subnational_scope { uid }
            }
    }
} """

total = client.txn(read_only=True).query(query_total_entries)
total = json.loads(total.json)

total_sources = total['sources'][0]['total']
results_maximum = 1000
offset = 0
variables = {'$maximum': str(results_maximum), '$offset': ""}

pages_sources = math.ceil(total_sources / results_maximum)

sources = []

for i in range(1, pages_sources + 1):
    variables['$offset'] = str(offset)
    res = client.txn(read_only=True).query(query_sources, variables=variables)
    raw = json.loads(res.json)
    sources += raw['sources']
    offset += results_maximum

# Order of priority: Transcript > Print > Website > Twitter > Facebook > Instagram > Telegram > VK

processed_memory = []
journalistic_brands = []
brand_template = {'dgraph.type': ["Entry", "JournalisticBrand"],
                   '_unique_name': "",
                  'name': "",
                  '_date_created': datetime.now().isoformat(),
                  'entry_review_status': ENTRY_REVIEW_STATUS,
                  '_added_by': {
                      'uid': ADMIN_UID,
                      '_added_by|timestamp': datetime.now().isoformat() },
                  }

# transcripts
for source in sources:
    if source['channel']['unique_name'] == 'transcript':
        processed_memory.append(source['uid'])
        brand = {**brand_template}
        brand['_unique_name'] = "journalisticbrand_" + slugify(source['name'], separator="") + "_" + datetime.now().strftime("%Y%m%d")
        brand['name'] = source['name']
        brand['countries'] = source['countries']
        try:
            brand['subnational_scope'] = source['subnational_scope']
        except:
            pass
        brand['sources_included'] = [{'uid': source['uid']}]
        if "wikidata_id" in source:
            brand['wikidata_id'] = "Q" + str(source['wikidata_id'])
        if "related_news_sources" in source:
            for related_news_sources in source['related_news_sources']:
                brand['sources_included'].append({'uid': related_news_sources['uid']})
                try:
                    brand['countries'] += related_news_sources['countries']
                except:
                    pass
                try:
                    brand['subnational_scope'] += related_news_sources['subnational_scope']
                except:
                    pass
                processed_memory.append(related_news_sources['uid'])
        journalistic_brands.append(brand)
        


# print
for source in sources:
    if source['channel']['unique_name'] == 'print':
        if source['uid'] in processed_memory:
            continue
        processed_memory.append(source['uid'])
        brand = {**brand_template}
        brand['_unique_name'] = "journalisticbrand_" + slugify(source['name'], separator="") + "_" + datetime.now().strftime("%Y%m%d")
        brand['name'] = source['name']
        brand['countries'] = source['countries']
        try:
            brand['subnational_scope'] = source['subnational_scope']
        except:
            pass
        brand['sources_included'] = [{'uid': source['uid']}]
        if "wikidata_id" in source:
            brand['wikidata_id'] = "Q" + str(source['wikidata_id'])
        if "related_news_sources" in source:
            for related_news_sources in source['related_news_sources']:
                brand['sources_included'].append({'uid': related_news_sources['uid']})
                try:
                    brand['countries'] += related_news_sources['countries']
                except:
                    pass
                try:
                    brand['subnational_scope'] += related_news_sources['subnational_scope']
                except:
                    pass
                processed_memory.append(related_news_sources['uid'])
        journalistic_brands.append(brand)
        

# website
for source in sources:
    if source['channel']['unique_name'] == 'website':
        if source['uid'] in processed_memory:
            continue
        processed_memory.append(source['uid'])
        brand = {**brand_template}
        brand['_unique_name'] = "journalisticbrand_" + slugify(source['name'], separator="") + "_" + datetime.now().strftime("%Y%m%d")
        brand['name'] = source['name']
        brand['countries'] = source['countries']
        try:
            brand['subnational_scope'] = source['subnational_scope']
        except:
            pass
        brand['sources_included'] = [{'uid': source['uid']}]
        if "wikidata_id" in source:
            brand['wikidata_id'] = "Q" + str(source['wikidata_id'])
        if "related_news_sources" in source:
            for related_news_sources in source['related_news_sources']:
                brand['sources_included'].append({'uid': related_news_sources['uid']})
                processed_memory.append(related_news_sources['uid'])
                try:
                    brand['countries'] += related_news_sources['countries']
                except:
                    pass
                try:
                    brand['subnational_scope'] += related_news_sources['subnational_scope']
                except:
                    pass
        journalistic_brands.append(brand)
        

# twitter
for source in sources:
    if source['channel']['unique_name'] == 'twitter':
        if source['uid'] in processed_memory:
            continue
        processed_memory.append(source['uid'])
        brand = {**brand_template}
        brand['_unique_name'] = "journalisticbrand_" + slugify(source['name'], separator="") + "_" + datetime.now().strftime("%Y%m%d")
        brand['name'] = source['name']
        brand['countries'] = source['countries']
        try:
            brand['subnational_scope'] = source['subnational_scope']
        except:
            pass
        brand['sources_included'] = [{'uid': source['uid']}]
        if "wikidata_id" in source:
            brand['wikidata_id'] = "Q" + str(source['wikidata_id'])
        if "related_news_sources" in source:
            for related_news_sources in source['related_news_sources']:
                brand['sources_included'].append({'uid': related_news_sources['uid']})
                processed_memory.append(related_news_sources['uid'])
                try:
                    brand['countries'] += related_news_sources['countries']
                except:
                    pass
                try:
                    brand['subnational_scope'] += related_news_sources['subnational_scope']
                except:
                    pass
        journalistic_brands.append(brand)
        



# facebook
for source in sources:
    if source['channel']['unique_name'] == 'facebook':
        if source['uid'] in processed_memory:
            continue
        processed_memory.append(source['uid'])
        brand = {**brand_template}
        brand['_unique_name'] = "journalisticbrand_" + slugify(source['name'], separator="") + "_" + datetime.now().strftime("%Y%m%d")
        brand['name'] = source['name']
        brand['countries'] = source['countries']
        try:
            brand['subnational_scope'] = source['subnational_scope']
        except:
            pass
        brand['sources_included'] = [{'uid': source['uid']}]
        if "wikidata_id" in source:
            brand['wikidata_id'] = "Q" + str(source['wikidata_id'])
        if "related_news_sources" in source:
            for related_news_sources in source['related_news_sources']:
                brand['sources_included'].append({'uid': related_news_sources['uid']})
                processed_memory.append(related_news_sources['uid'])
                try:
                    brand['countries'] += related_news_sources['countries']
                except:
                    pass
                try:
                    brand['subnational_scope'] += related_news_sources['subnational_scope']
                except:
                    pass
        journalistic_brands.append(brand)
        

# instagram
for source in sources:
    if source['channel']['unique_name'] == 'instagram':
        if source['uid'] in processed_memory:
            continue
        processed_memory.append(source['uid'])
        brand = {**brand_template}
        brand['_unique_name'] = "journalisticbrand_" + slugify(source['name'], separator="") + "_" + datetime.now().strftime("%Y%m%d")
        brand['name'] = source['name']
        brand['countries'] = source['countries']
        try:
            brand['subnational_scope'] = source['subnational_scope']
        except:
            pass
        brand['sources_included'] = [{'uid': source['uid']}]
        if "wikidata_id" in source:
            brand['wikidata_id'] = "Q" + str(source['wikidata_id'])
        if "related_news_sources" in source:
            for related_news_sources in source['related_news_sources']:
                brand['sources_included'].append({'uid': related_news_sources['uid']})
                processed_memory.append(related_news_sources['uid'])
                try:
                    brand['countries'] += related_news_sources['countries']
                except:
                    pass
                try:
                    brand['subnational_scope'] += related_news_sources['subnational_scope']
                except:
                    pass
        journalistic_brands.append(brand)
        

# telegram
for source in sources:
    if source['channel']['unique_name'] == 'telegram':
        if source['uid'] in processed_memory:
            continue
        processed_memory.append(source['uid'])
        brand = {**brand_template}
        brand['_unique_name'] = "journalisticbrand_" + slugify(source['name'], separator="") + "_" + datetime.now().strftime("%Y%m%d")
        brand['name'] = source['name']
        brand['countries'] = source['countries']
        try:
            brand['subnational_scope'] = source['subnational_scope']
        except:
            pass
        brand['sources_included'] = [{'uid': source['uid']}]
        if "wikidata_id" in source:
            brand['wikidata_id'] = "Q" + str(source['wikidata_id'])
        if "related_news_sources" in source:
            for related_news_sources in source['related_news_sources']:
                brand['sources_included'].append({'uid': related_news_sources['uid']})
                processed_memory.append(related_news_sources['uid'])
                try:
                    brand['countries'] += related_news_sources['countries']
                except:
                    pass
                try:
                    brand['subnational_scope'] += related_news_sources['subnational_scope']
                except:
                    pass
        journalistic_brands.append(brand)

# Apply

txn = client.txn()

res = txn.mutate(set_obj=journalistic_brands, commit_now=True)

print('Adding audience_size_recent ...')

query_string = """{
	q(func: has(audience_size)) {
		uid audience_size @facets
  }
}"""

res = client.txn().query(query_string)

j = json.loads(res.json)['q']

audience_size_recent = []

for node in j:
    try:
        count = int(node['audience_size|count']['0'])
        updated = {'uid': node['uid'],
                'audience_size_recent': count,
                'audience_size_recent|unit': node['audience_size|unit']['0'],
                'audience_size_recent|timestamp': node['audience_size'][0]}
    except:
        print('Could not parse node', node['uid'])
        # print(node)
        continue
    audience_size_recent.append(updated)
    
res = client.txn().mutate(set_obj=audience_size_recent, commit_now=True)

""" Scientific Publication """

print('Migrating Scientific Publications ...')

query = """{
  r as var(func: type(ResearchPaper))
}"""

nquad = """uid(r) <dgraph.type> "ScientificPublication" . """

delete = """uid(r) <dgraph.type> "ResearchPaper" ."""

txn = client.txn()

mutation = txn.create_mutation(set_nquads=nquad, del_nquads=delete)
request = txn.create_request(query=query, mutations=[mutation], commit_now=True)
txn.do_request(request)

""" Organization """

print('Migrating Organizations to Parties and Persons ...')


query = """{
  party as var(func: type(Organization)) @filter(eq(ownership_kind, "political party")) 
  person as var(func: type(Organization)) @filter(eq(is_person, "true")) 
}"""

nquad = """uid(party) <dgraph.type> "PoliticalParty" . 
            uid(person) <dgraph.type> "Person" . 
        """

delete = """uid(party) <dgraph.type> "Organization" .
            uid(party) <ownership_kind> * .
            uid(person) <dgraph.type> "Organization" .
            uid(person) <is_persion> * .
        """

txn = client.txn()

mutation = txn.create_mutation(set_nquads=nquad, del_nquads=delete)
request = txn.create_request(query=query, mutations=[mutation], commit_now=True)
txn.do_request(request)

""" Countries predicate """

print('Changing "Countries" predicate to "Country" predicate for organizations and subunits')

query_string = """{ q(func: has(countries))
    @filter(type(Organization) OR type(PoliticalParty) or type(Person) or type(Subnational) ) {
        uid countries { uid }
    }
}"""

res = client.txn().query(query_string)

j = json.loads(res.json)['q']

set_nquads = []
del_nquads = []

for entry in j:
    update = f"<{entry['uid']}> <country> <{entry['countries'][0]['uid']}> ."
    delete = f"<{entry['uid']}> <countries> * ."
    set_nquads.append(update)
    del_nquads.append(delete)

txn = client.txn()

txn.mutate(set_nquads="\n".join(set_nquads),
           del_nquads="\n".join(del_nquads),
           commit_now=True)

txn.discard()

""" Authors """

print('Migrating Authors ...')

author_cache_file = p / "data" / "author_cache.json"

try:
    with open(author_cache_file) as f:
        author_cache = json.load(f)
except:
    author_cache = {}

def resolve_openalex(entry, cache):
    doi = entry['doi']
    if doi in cache:
        j = cache[doi]
    else:
        api = "https://api.openalex.org/works/doi:"
        r = requests.get(api + doi)
        j = r.json()
        cache[doi] = j
    output = {'uid': entry['uid'],
              '_date_modified': datetime.now().isoformat()}
    authors = []
    for i, author in enumerate(j['authorships']):
        a_name = author['author']['display_name']
        open_alex = author['author']['id'].replace('https://openalex.org/', "")
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
        authors.append(author_entry)
    output['authors'] = authors
    return output

# get all entries with DOI

query = """{
	q(func: has(_authors_fallback)) @filter(has(doi))  {
		uid name doi _authors_fallback
        }
    }
"""

res = client.txn().query(query)

entries_with_doi = json.loads(res.json)['q']
authors = []
failed = []
delete_nquads = []

print('Retrieving Authors from OpenAlex ...')

for entry in entries_with_doi:
    try:
        authors.append(resolve_openalex(entry, author_cache))
        delete_nquads.append(f"<{entry['uid']}> <_authors_fallback> * .")
    except:
        failed.append(entry)

txn = client.txn()
res = txn.mutate(set_obj=authors, 
                 del_nquads="\n".join(delete_nquads), 
                 commit_now=True)

with open(author_cache_file, "w") as f:
    json.dump(author_cache, f)

# Delete _authors_fallback

uids = [a['uid'] for a in authors]

delete_nquads = [f'<{uid}> <_authors_fallback> * .' for uid in uids]

txn = client.txn()
res = txn.mutate(del_nquads="\n".join(delete_nquads), commit_now=True)

""" Languages """

print('Migrating Languages ...')

langs_json = p / 'data' / 'languages.json'

with open(langs_json, 'r') as f:
    languages = json.load(f)

languages = languages['set']

for l in languages:
    l['entry_review_status'] = 'accepted'
    l['_added_by'] = {'uid': ADMIN_UID,
                      '_added_by|timestamp': datetime.now().isoformat()}

languages_lookup = {l['icu_code']: l['uid'] for l in languages}

# find all entries with languages

query_string = """{
	q(func: has(_languages_tmp)) {
		uid _languages_tmp
  }
}"""

res = client.txn().query(query_string)

j = json.loads(res.json)['q']

updated_entries = []

for entry in j:
    updated = {'uid': entry['uid'],
               'languages': []}
    for l in entry['_languages_tmp']:
        updated['languages'].append({'uid': languages_lookup[l]})
    updated_entries.append(updated)

updated_entries += languages

res = client.txn().mutate(set_obj=updated_entries, commit_now=True)

# delete _languages_tmp


query = """{
  l as var(func: has(_languages_tmp))
}"""

delete = """uid(l) <_languages_tmp> * ."""

txn = client.txn()

mutation = txn.create_mutation(del_nquads=delete)
request = txn.create_request(query=query, mutations=[mutation], commit_now=True)
txn.do_request(request)


""" Programming Languages """

print('Migrating Programming Languages ...')

langs_json = p / 'data' / 'programming_languages.json'

with open(langs_json, 'r') as f:
    languages = json.load(f)

languages = languages['set']

for l in languages:
    l['entry_review_status'] = 'accepted'
    l['_added_by'] = {'uid': ADMIN_UID,
                    '_added_by|timestamp': datetime.now().isoformat()}


languages_lookup = {l['_unique_name'].replace("programming_language_", ""): l['uid'] for l in languages}

# find all entries with languages

query_string = """{
	q(func: has(_programming_languages_tmp)) {
		uid _programming_languages_tmp
  }
}"""

res = client.txn().query(query_string)

j = json.loads(res.json)['q']

updated_entries = []

for entry in j: 
    updated = {'uid': entry['uid'],
               'programming_languages': []}
    for l in entry['_programming_languages_tmp']:
        updated['programming_languages'].append({'uid': languages_lookup[l]})
    updated_entries.append(updated)

updated_entries += languages

res = client.txn().mutate(set_obj=updated_entries, commit_now=True)

# delete _programming_languages_tmp

query = """{
  l as var(func: has(_programming_languages_tmp))
}"""

delete = """uid(l) <_programming_languages_tmp> * ."""

txn = client.txn()

mutation = txn.create_mutation(del_nquads=delete)
request = txn.create_request(query=query, mutations=[mutation], commit_now=True)
txn.do_request(request)


""" Generate new unique names """

print("Assigning new unique names")

def generate_unique_name(entry): 
    unique_name = ""
    dgraph_type = entry['dgraph.type']
    try:
        dgraph_type.remove('Entry')
    except:
        pass
    unique_name += slugify(dgraph_type[0], separator="")
    if "country" in entry:
        country = entry['country']['iso_3166_1_2']
        unique_name += "_"
        unique_name += country
    elif "countries" in entry:
        country = entry['countries'][0]['iso_3166_1_2']
        unique_name += "_"
        unique_name += country
    else: 
        country = None
    name = slugify(entry['name'], separator="")
    unique_name += "_"
    unique_name += name
    if "channel" in entry:
        channel = entry['channel']['unique_name']
        unique_name += "_"
        unique_name += channel
    return unique_name

query_string = """{
    q(func: has(unique_name)) @filter(NOT has(_unique_name)) {
			uid unique_name name dgraph.type 
            country { iso_3166_1_2 }
            countries { iso_3166_1_2 }
            channel { unique_name }
  }
}"""


res = client.txn().query(query_string)

j = json.loads(res.json)['q']

updated_entries = []
del_nquads = []

for entry in j:
    if 'Channel' in entry['dgraph.type']:
        unique_name = entry['unique_name']
    else:
        unique_name = generate_unique_name(entry)
    updated = {'uid': entry['uid'],
               "_unique_name": unique_name}
    updated_entries.append(updated)
    del_string = f"<{entry['uid']}> <unique_name> * ."
    del_nquads.append(del_string)


res = client.txn().mutate(set_obj=updated_entries, 
                          del_nquads="\n".join(del_nquads), 
                          commit_now=True)

""" Wikidata IDs """

print('Updating Wikidata IDs ...')

query_string = """{
	q(func: has(wikidata_id)) {
		uid wikidata_id
  }
}"""


res = client.txn().query(query_string)

j = json.loads(res.json)['q']

updated_entries = []

for entry in j:
    if entry['wikidata_id'].startswith("Q"):
        continue
    updated = {'uid': entry['uid'],
               "wikidata_id": "Q" + entry['wikidata_id']}
    updated_entries.append(updated)

res = client.txn().mutate(set_obj=updated_entries, 
                          commit_now=True)

# Text types

text_types = [{'uid': '_:texttype_journalistictext',
               '_unique_name': 'texttype_journalistictext',
               'name': 'Journalistic Text',
               'alternate_names': ['Journalistic Mass-mediated political text', 'JMPT'],
               '_date_created': datetime.now().isoformat(),
               'entry_review_status': 'accepted',
                '_added_by': {
                    'uid': ADMIN_UID,
                    '_added_by|timestamp': datetime.now().isoformat()},
                'dgraph.type': ['Entry', 'TextType']
               }]

txn = client.txn()
res = txn.mutate(set_obj=text_types, commit_now=True)

# Dataset, Corpus, and Archives

query = """{
  d as var(func: type(Dataset))
  a as var(func: type(Archive))
  jmpt as var(func: eq(_unique_name, "texttype_journalistictext"))
}"""

nquad = """uid(d) <text_types> uid(jmpt) .
           uid(a) <text_types> uid(jmpt) .
        """

txn = client.txn()

mutation = txn.create_mutation(set_nquads=nquad)
request = txn.create_request(query=query, mutations=[mutation], commit_now=True)
txn.do_request(request)

client_stub.close()
