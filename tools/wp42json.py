

sample_dataset = {
    'dgraph.type': ['Entry', 'Dataset'], # or Archive -> entity
    'entry_review_status': 'accepted',
    '_date_created': datetime.now().isoformat(), 
    '_added_by': '<Admin>', # fetch UID of Admin user
    'name': "AUTNES", # -> name
    'description': "Data set including a ...", # -> description
    'doi': '10.11587/6L3JKK', # -> doi
    'url': 'https://data.aussda.at/dataset.xhtml?persistentId=doi:10.11587/6L3JKK', # -> URL
    "authors": ["<https://explore.openalex.org/authors/A4358598361>", "..."], # fetch from OpenAlex API
    "date_published": "2021-05-28", # fetch from OpenAlex API
    "date_modified": "2021", # -> last_updated
    "conditions_of_access": "registration required", # -> access (to_lower!)
    "fulltext_available": False, # -> contains_full_text (as bool)
    "sources_included": ["<politicalparty_at_liberalforum_20230425>", "..."], # -> political_party
    "countries": "<Austria>", # infer from political_party
    "geographic_scope": "national", # -> region
    "languages": ["<de>"], # -> languages
    "temporal_coverage_start": "2002", # -> start_date
    "temporal_coverage_end": "2002", # -> end_date
    "text_type": "<Press Release>", # -> text.type
    "file_formats": ["<dta>", "<tab>", "<Rdata>"], # -> file_format
    "meta_variables": ["<party name>", "<sender>"], # -> meta_vars
    "concept_variables": ["<party communication>", "<issue salience>"], # -> concept_vars
}

# Linkage resolution strategy

# first!! resolve all parties and add them to dgraph
# authors: if entry has DOI, use OpenAlex and get author id, if author doesnt exist in dgraph, add new
# countries: infer from political party
# languages: query dgraph by Language -> icu_code
# text_type: create entries for all text types, then query dgraph by name 
# file_formats: get file formats from WP3, then query dgraph by name
# meta_variables: get meta variables from WP3, then query dgraph by name
# concept_variables: see above

