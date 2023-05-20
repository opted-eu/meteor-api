# Alter Backup
# This script takes a WP3 Backup and alters the predicate names

from pathlib import Path
import re 
import gzip

p = Path.cwd()

g01_rdf = p / "data" / "g01.rdf.gz"

with gzip.open(g01_rdf) as f:
    tmp = f.read().decode()

tmp = tmp.replace("<country>", "<countries>")
tmp = tmp.replace("<languages>", "<_languages_tmp>")
tmp = tmp.replace("<programming_languages>", "<_programming_languages_tmp>")
tmp = tmp.replace("<authors>", "<_authors_tmp>")
tmp = tmp.replace("<materials>", "<_materials_tmp>")
tmp = tmp.replace("TextUnit", "UnitOfAnalysis")

# mapping dict 'old': 'new'
wp3_mapping = {'creation_date': '_date_created',
               'entry_added': '_added_by',
               'reviewed_by': '_reviewed_by',
               'entry_edit_history': '_edited_by',
               'other_names': 'alternate_names',
               'wikidataID': 'wikidata_id',
               'published_date': 'date_published',
               'last_updated': 'date_modified',
               'access': 'conditions_of_access',
               # 'fulltext': 'fulltext_available',
               'start_date': 'temporal_coverage_start',
               'end_date': 'temporal_coverage_end',
               'file_format': 'file_formats',
               'meta_vars': 'meta_variables',
               'concept_vars': 'concept_variables',
               'platform': 'platforms',
               'open_source': 'opensource',
               'user_access': 'conditions_of_access',
               'channels': 'designed_for',
               'input_file_format': 'input_file_formats',
               'output_file_format': "output_file_formats",
               'channel_url': 'identifier',
               'website_allows_comments': 'website_comments_allowed',
               'website_comments_registration_required': 'website_comments_registration',
               'founded': 'date_founded',
               'channel_epaper': 'epaper_available',
               'related': 'related_news_sources',
               'journal': 'venue',
               'address_string': 'address',
               'user_displayname': 'display_name',
               'pw': '_pw',
               'pw_reset': '_pw_reset',
               'user_orcid': 'orcid',
               'date_joined': '_date_joined',
               'user_role': '_role',
               'user_affiliation': 'affiliation',
               'account_status': '_account_status'}

for old, new in wp3_mapping.items():
    pat = re.compile(r"\b" + old + r"\b")
    tmp = re.sub(pat, new, tmp)


rdf_out = p / "data" / g01_rdf.name.replace(".gz", "")

with open(rdf_out, "w") as f:
    f.write(tmp)


g01_schema = p / "data" / "g01.schema.gz"

with gzip.open(g01_schema) as f:
    tmp = f.read().decode()

tmp = tmp.replace("<country>", "<countries>")
tmp = tmp.replace("<languages>", "<_languages_tmp>")
tmp = tmp.replace("<programming_languages>", "<_programming_languages_tmp>")
tmp = tmp.replace("<authors>", "<_authors_tmp>")
tmp = tmp.replace("<materials>", "<_materials_tmp>")
tmp = tmp.replace("TextUnit", "UnitOfAnalysis")

pat = re.compile(r"country\b")
tmp = re.sub(pat, r"countries", tmp)

pat = re.compile(r"\blanguages\b")
tmp = re.sub(pat, r"_languages_tmp", tmp)

pat = re.compile(r"programming_languages\b")
tmp = re.sub(pat, r"_programming_languages_tmp", tmp)

pat = re.compile(r"authors\b")
tmp = re.sub(pat, r"_authors_tmp", tmp)

pat = re.compile(r"materials\b")
tmp = re.sub(pat, r"_materials_tmp", tmp)


for old, new in wp3_mapping.items():
    pat = re.compile(r"\b" + old + r"\b")
    tmp = re.sub(pat, new, tmp)

tmp = tmp.replace("@index(fulltext_available", "@index(fulltext")

tmp = tmp.replace("[0x0] <conditions_of_access>:string @index(hash) . ", "", 1)
tmp = tmp.replace("[0x0] <address>:string . ", "", 1)
tmp = tmp.replace("[0x0] <display_name>:string . ", "", 1)

schema_out = p / "data" / g01_schema.name.replace(".gz", "")

with open(schema_out, "w") as f:
    f.write(tmp)