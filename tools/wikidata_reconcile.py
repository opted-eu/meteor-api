import pandas as pd
from flaskinventory.auxiliary import icu_codes, programming_languages
from reconciler import reconcile
import requests
import json
from slugify import slugify

icu = [{'iso': k, 'language': v} for k, v in icu_codes.items()]

df = pd.DataFrame(icu)

reconciled = reconcile(df["iso"], type_id="Q34770", property_mapping={"P218": df['iso']})

# reconciled.to_csv('languages.csv')

no_match = reconciled[reconciled.match == False]

no_match.to_json('languages_nomatch.json', orient='records',indent=1)

reconciled = reconciled[reconciled.match == True]


api = 'https://www.wikidata.org/w/api.php'


params = {'action': 'wbgetentities', #'languages': 'en',
          'format': 'json'}

languages = []

for index, row in reconciled.iterrows():
    print(row['name'])
    wikidataid = row['id']
    params['ids'] = wikidataid 
    r = requests.get(api, params=params)
    wikidata = r.json()
    result = {'name': row['name'],
              'wikidata_id': wikidataid,
              'description': row['description'],
              'icu_code': row['input_value']}
    result['alternate_names'] = []
    try:
        result['name' + '@' + row['input_value']] = wikidata['entities'][wikidataid]['labels'][row['input_value']]['value'] # native label
    except:
        pass
    result['name@en'] = wikidata['entities'][wikidataid]['labels']['en']['value']
    aliases = wikidata['entities'][wikidataid]['aliases']['en']
    for alias in aliases:
        result['alternate_names'].append(alias['value'])
    # P219 ISO 639-2; P220 ISO 639-3
    try:
        result['iso_639_2'] = wikidata['entities'][wikidataid]['claims']['P219'][0]['mainsnak']['datavalue']['value']
        result['iso_639_3'] = wikidata['entities'][wikidataid]['claims']['P220'][0]['mainsnak']['datavalue']['value']
    except:
        pass
    languages.append(result)


with open('languages_nomatch.json') as f:
    manual_langs = json.load(f)

languages += manual_langs

for l in languages:
    l['_unique_name'] = slugify(f'language_{l["name"]}', separator="_")
    l['dgraph.type'] = "Language"
    l['uid'] = "_:" + l['_unique_name']


mutation = {'set': languages}

with open('data/languages.json', 'w') as f:
    json.dump(mutation, f, indent=2)


""" Programming Languages """


programming = [{'short': k, 'programming_language': v} for k, v in programming_languages.items()]

df = pd.DataFrame(programming)

reconciled = reconcile(df["programming_language"], type_id="Q9143")

reconciled.to_json('programming_languages.json', orient='records',indent=1)

df = pd.read_json('programming_languages.json')

programming_languages = []

for index, row in df.iterrows():
    print(row['name'])
    wikidataid = row['id']
    params['ids'] = wikidataid 
    r = requests.get(api, params=params)
    wikidata = r.json()
    result = {'name': row['name'],
              'wikidata_id': wikidataid,
              'description': row['description']}
    result['alternate_names'] = []
    try:
        aliases = wikidata['entities'][wikidataid]['aliases']['en']
    except:
        aliases = []
    for alias in aliases:
        result['alternate_names'].append(alias['value'])
    programming_languages.append(result)


for l in programming_languages:
    l['_unique_name'] = slugify(f'programming_language_{l["name"]}', separator="_")
    l['dgraph.type'] = ["ProgrammingLanguage", "Entry"]
    l['uid'] = "_:" + l['_unique_name']


mutation = {'set': programming_languages}

with open('data/programming_languages.json', 'w') as f:
    json.dump(mutation, f, indent=2)