"""
    Script for retrieving wikidata ids from partyfacts
    outputs a feather file with the partyfacts dataset (opted countries)
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import date
import pydgraph
from slugify import slugify
import requests
from urllib.parse import unquote
from tqdm import tqdm

p = Path.cwd()

# Load Data from Excel sheet
xlsx = p / 'data' / 'OPTED Taxonomy.xlsx'

df = pd.read_excel(xlsx, sheet_name="political_party")

# Join with Party facts data

partyfacts = pd.read_csv("https://partyfacts.herokuapp.com/download/external-parties-csv/")
partyfacts.partyfacts_id = partyfacts.partyfacts_id.astype(int)
countries_df = pd.read_csv("https://partyfacts.herokuapp.com/download/countries-csv/")
countries_mapping = {ctr: country for ctr, country in zip(countries_df.country.to_list(), countries_df.name.to_list())}
partyfacts.country = partyfacts.country.replace(countries_mapping)

opted_countries = df.dropna(subset="country").country.unique().tolist()
partyfacts = partyfacts.loc[partyfacts.country.isin(opted_countries), :]


# partyfacts core dataset to wikidata ID
# https://en.wikipedia.org/w/api.php?action=query&prop=pageprops&ppprop=wikibase_item&redirects=1&titles=Afghan_Millat_Party
partyfacts_core = pd.read_csv("https://partyfacts.herokuapp.com/download/core-parties-csv/")
partyfacts_core = partyfacts_core.dropna(subset="wikipedia").reset_index(drop=True)

partyfacts_core.country = partyfacts_core.country.replace(countries_mapping)
partyfacts_core = partyfacts_core.loc[partyfacts_core.country.isin(opted_countries), :].reset_index(drop=True)

partyfacts_core['wiki_title'] = partyfacts_core.wikipedia.str.extract(r"wiki/(.*$)", expand=False)
partyfacts_core['wiki_title'] = partyfacts_core.wiki_title.apply(unquote)

partyfacts_core['wiki_server'] = partyfacts_core.wikipedia.apply(lambda x: x.split('/')[2])

params = {'action': 'query',
          'prop': 'pageprops',
          'ppprop': 'wikibase_item',
          'redirects': 1,
          'titles': '',
          'format': 'json'}

partyfacts_core['wikidata_id'] = ""

for index, row in tqdm(partyfacts_core.iterrows(), total=len(partyfacts_core), desc="Getting wikidata IDs"):
    api = f"https://{row['wiki_server']}/w/api.php"
    params['titles'] = row['wiki_title']
    r = requests.get(api, params=params)
    j = r.json()
    try:
        for val in j['query']['pages'].values():
            wikidata_id = val['pageprops']['wikibase_item']
            break
    except:
        wikidata_id = ""
    partyfacts_core.at[index, 'wikidata_id'] = wikidata_id


keep_cols = ['partyfacts_id', 'name_other', 'wikidata_id']
partyfacts = partyfacts.join(partyfacts_core.loc[:, keep_cols].set_index('partyfacts_id'), on = "partyfacts_id", rsuffix='_other')


partyfacts.reset_index(drop=True).to_feather('data/partyfacts.feather', compression="uncompressed")
