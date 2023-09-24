import typing

from meteor.flaskdgraph import Schema
from meteor.flaskdgraph.dgraph_types import (UID, MutualRelationship, NewID,
                                             ReverseRelationship, Scalar,
                                             SingleRelationship,
                                             Variable,
                                             dict_to_nquad)

from meteor.errors import InventoryValidationError, InventoryPermissionError

from meteor.users.constants import USER_ROLES
from meteor.main.model import User
from meteor import dgraph
from flask import current_app

from meteor.main.model import Entry
from meteor.misc import get_ip

# External Utilities

from slugify import slugify
import secrets
import re

import datetime


class Sanitizer:
    """ 
        Sanitizer for validating data and generating mutation object.
        Validates all predicates from dgraph type 'Entry'
        also keeps track of user & ip address.
        Relevant return attributes are upsert_query (string), set_nquads (string), delete_nquads (string)
    """

    upsert_query = None

    def __init__(self,
                 data: dict,
                 user: User,
                 fields: dict = None,
                 dgraph_type=Entry,
                 entry_review_status: typing.Literal['draft',
                                                     'pending', 'revise', 'accepted'] = None,
                 **kwargs):
        current_app.logger.debug(f'Got the following data: {data}')

        self.user = user
        self.user_ip = get_ip()
        self._prevalidate_inputdata(data, self.user, self.user_ip)
        if not isinstance(dgraph_type, str):
            dgraph_type = dgraph_type.__name__
        self.dgraph_type = dgraph_type
        self.fields = fields or Schema.get_predicates(dgraph_type)
        if self.dgraph_type and fields is None:
            if Schema.get_reverse_predicates(dgraph_type):
                self.fields.update(Schema.get_reverse_predicates(dgraph_type))

        if self.user._role < USER_ROLES.Contributor:
            raise InventoryPermissionError

        self.data = data

        self.is_upsert = kwargs.get('is_upsert', False)
        self.skip_keys = kwargs.get('skip_keys', [])
        self.entry_review_status = entry_review_status
        self.overwrite = {}
        self.newsubunits = []

        self.entry = {}
        self.related_entries = []
        self.facets = {}
        self.entry_uid = None

        self.delete_nquads = None
        self.upsert_query = None
        self.set_nquads = None

        if not self.is_upsert:
            self.entry['dgraph.type'] = Schema.resolve_inheritance(dgraph_type)
        self._parse()
        self.process_related()
        if self.dgraph_type == 'NewsSource':
            if not self.is_upsert or self.entry_review_status == 'draft':
                self.process_source()

        if self.dgraph_type == 'ScientificPublication':
            self.process_scientificpublication()

        self._delete_nquads()
        self._set_nquads()

    @staticmethod
    def _prevalidate_inputdata(data: dict, user: User, ip: str) -> bool:
        if not isinstance(data, dict):
            raise TypeError('Data object has to be type dict!')
        if not isinstance(user, User):
            raise InventoryPermissionError(
                f'User Object is not class User! Received class: {type(user)}')
        if not isinstance(ip, str):
            raise TypeError('IP Address is not string!')
        return True

    @classmethod
    def edit(cls, data: dict, user: User, fields=None, dgraph_type=Entry, **kwargs):
        cls._prevalidate_inputdata(data, user, get_ip())

        if 'uid' not in data.keys():
            raise InventoryValidationError(
                'You cannot edit an entry without a UID')

        check = cls._check_entry(data['uid'])
        if not check:
            raise InventoryValidationError(
                f'Entry can not be edited! UID does not exist: {data["uid"]}')

        if user._role < USER_ROLES.Reviewer:
            if check.get('_added_by').get('uid') != user.id:
                raise InventoryPermissionError(
                    'You do not have the required permissions to edit this entry!')

        entry_review_status = check.get('entry_review_status')

        edit_fields = fields or Schema.get_predicates(dgraph_type)
        if dgraph_type and fields is None:
            if Schema.get_reverse_predicates(dgraph_type):
                edit_fields.update(Schema.get_reverse_predicates(dgraph_type))

        if entry_review_status != 'draft':
            edit_fields = {key: field for key,
                           field in edit_fields.items() if field.edit or key == 'uid'}

        if not isinstance(dgraph_type, str):
            dgraph_type = dgraph_type.__name__

        return cls(data,
                   user,
                   is_upsert=True,
                   dgraph_type=dgraph_type,
                   entry_review_status=entry_review_status,
                   fields=edit_fields,
                   **kwargs)

    def _set_nquads(self):
        nquads = dict_to_nquad(self.entry)
        for related_news_sources in self.related_entries:
            nquads += dict_to_nquad(related_news_sources)
        self.set_nquads = " \n".join(nquads)

    def _delete_nquads(self):
        if self.is_upsert:
            # for upserts, we first have to delete all list type predicates
            # otherwise, the user cannot remove relationships, but just add to them

            del_obj = []

            upsert_query = ''

            for key, val in self.overwrite.items():
                for predicate in list(set(val)):
                    del_obj.append({'uid': key, predicate: '*'})
                    try:
                        if isinstance(self.fields[predicate], (MutualRelationship, ReverseRelationship)):
                            var = Variable(predicate, 'uid')
                            upsert_query += f""" q_{predicate}(func: has(dgraph.type)) 
                                                    @filter(uid_in({predicate}, {key.query})) {{
                                                        {var.query}
                                                    }} """
                            del_obj.append({'uid': var, predicate: key})
                    except KeyError:
                        pass

            nquads = [" \n".join(dict_to_nquad(obj)) for obj in del_obj]
            self.delete_nquads = " \n".join(nquads)
            if upsert_query != '':
                self.upsert_query = upsert_query
            else:
                self.upsert_query = None
        else:
            self.delete_nquads = None

    @staticmethod
    def _check_entry(uid):
        query = f'''query check_entry($value: string)
                    {{ q(func: uid($value)) @filter(has(dgraph.type))'''
        query += "{ _unique_name dgraph.type entry_review_status _added_by { uid } } }"
        data = dgraph.query(query, variables={'$value': uid})

        if len(data['q']) == 0:
            return False

        return data['q'][0]

    def _add_entry_meta(self, entry, newentry=False):
        # verify that dgraph.type is not added to self if the entry already exists
        if newentry:
            if entry.get('dgraph.type'):
                if type(entry['dgraph.type']) != list:
                    entry['dgraph.type'] = Schema.resolve_inheritance(
                        entry['dgraph.type'])
                elif isinstance(entry['dgraph.type'], list):
                    dtypes = []
                    for dt in entry['dgraph.type']:
                        dtypes += Schema.resolve_inheritance(dt)
                    entry['dgraph.type'] = list(set(dtypes))
            else:
                entry['dgraph.type'] = ["Entry"]

            entry['_unique_name'] = self.generate_unique_name(entry)

        facets = {'timestamp': datetime.datetime.now(
            datetime.timezone.utc),
            'ip': self.user_ip}

        if not newentry:
            entry['_edited_by'] = UID(self.user.uid, facets=facets)
        else:
            entry['_added_by'] = UID(self.user.uid, facets=facets)
            entry['entry_review_status'] = 'pending'
            entry['_date_created'] = datetime.datetime.now(
                datetime.timezone.utc)

        return entry

    def _preprocess_facets(self):
        # helper function to sieve out facets from the input data
        # currently only supports single facets
        # can only update on facet per mutation (no list facets)
        for key in self.data:
            if '|' in key:
                predicate, facet = key.split('|')
                if predicate in self.facets:
                    self.facets[predicate].update({facet: self.data[key]})
                else:
                    self.facets[predicate] = {facet: self.data[key]}

            # for list predicates, we track facets via the value
            if '@' in key:
                val, facet = key.split('@')
                self.facets[val] = {facet: self.data[key]}

    def _postprocess_list_facets(self):
        for ll in self.entry.values():
            if isinstance(ll, list):
                for val in ll:
                    if isinstance(val, Scalar):
                        if str(val) in self.facets.keys():
                            val.update_facets(self.facets[str(val)])

    def _parse(self):
        # UID validation
        if self.data.get('uid'):
            uid = self.data.pop('uid')
            self.entry_uid = self.fields['uid'].validate(uid)
        else:
            self.entry_uid = self.fields['uid'].default

        self.entry['uid'] = self.entry_uid
        self.skip_keys.append(self.fields['uid'].predicate)

        # unpack facets from input dict (JSON)
        self._preprocess_facets()

        # run all parse_ methods
        for item in dir(self):
            if item.startswith('parse_'):
                m = getattr(self, item)
                try:
                    m()
                except:
                    continue

        for key, item in self.fields.items():
            validated = None
            if key in self.skip_keys:
                continue

            if key not in self.data and self.is_upsert:
                continue

            if key in self.facets.keys():
                facets = self.facets[key]
            else:
                facets = None

            if self.data.get(key) and isinstance(item, ReverseRelationship):
                validated = item.validate(
                    self.data[key], self.entry_uid, facets=facets)
                if item.required and validated is None and not self.is_upsert:
                    raise InventoryValidationError(
                        f'Error in predicate <{key}>. Is required, but no value supplied!')

                if isinstance(validated, list):
                    self.related_entries += validated
                else:
                    self.related_entries.append(validated)
                continue
            elif self.data.get(key) and isinstance(item, MutualRelationship):
                node_data, data_node = item.validate(
                    self.data[key], self.entry_uid, facets=facets)
                self.entry[item.predicate] = node_data
                if isinstance(data_node, list):
                    self.related_entries += data_node
                else:
                    self.related_entries.append(data_node)
                continue

            elif key in self.data and isinstance(item, SingleRelationship):
                related_items = item.validate(self.data[key], facets=facets)
                if item.required and related_items is None and not self.is_upsert:
                    raise InventoryValidationError(
                        f'Error in predicate <{key}>. Is required, but no value supplied!')

                if isinstance(related_items, list):
                    validated = []
                    for i in related_items:
                        validated.append(i['uid'])
                        if isinstance(i['uid'], NewID):
                            self.related_entries.append(i)

                else:
                    validated = related_items['uid']
                    if isinstance(related_items['uid'], NewID):
                        self.related_entries.append(related_items)

            elif self.data.get(key) and hasattr(item, 'validate'):
                validated = item.validate(self.data[key], facets=facets)

            elif hasattr(item, 'autocode'):
                if item.autoinput in self.data.keys():
                    validated = item.autocode(
                        self.data[item.autoinput], facets=facets)

            elif hasattr(item, 'default'):
                validated = item.default
                if hasattr(validated, 'facets') and facets is not None:
                    validated.update_facets(facets)

            #  assert validation procedure really yields values for required fields
            if item.required and validated is None and not self.is_upsert:
                raise InventoryValidationError(
                    f'Error in predicate <{key}>. Is required, but no value supplied!')

            if validated is None:
                continue

            if type(validated) == dict:
                self.entry.update(validated)
            elif type(validated) == list and key in self.entry.keys():
                try:
                    self.entry[key] += validated
                except TypeError:
                    validated.append(self.entry[key])
                    self.entry[key] = validated
            elif type(validated) == set and key in self.entry.keys():
                self.entry[key] = set.union(validated, self.entry[key])
            else:
                self.entry[key] = validated

        if self.is_upsert:
            self.entry = self._add_entry_meta(self.entry)
            self.overwrite[self.entry_uid] = [item.predicate for k, item in self.fields.items(
            ) if item.overwrite and k in self.data.keys()]
        else:
            self.entry = self._add_entry_meta(self.entry, newentry=True)
            # self.entry['_unique_name'] = self.generate_unique_name(self.entry)

        self._postprocess_list_facets()

    def process_related(self):
        for related_news_sources in self.related_entries:
            related_news_sources = self._add_entry_meta(
                related_news_sources, newentry=isinstance(related_news_sources['uid'], NewID))
            if isinstance(related_news_sources['uid'], NewID) and 'name' not in related_news_sources.keys():
                related_news_sources['name'] = str(related_news_sources['uid']).replace(
                    '_:', '').replace('_', ' ').title()

    def parse_entry_review_status(self):
        if self.data.get('accept'):
            if self.user._role < USER_ROLES.Reviewer:
                raise InventoryPermissionError(
                    'You do not have the required permissions to change the review status!')
            self.entry['entry_review_status'] = 'accepted'
            self.entry['_reviewed_by'] = UID(self.user.uid, facets={
                'timestamp': datetime.datetime.now(datetime.timezone.utc)})
            self.skip_keys.append('entry_review_status')
        elif self.data.get('entry_review_status'):
            if self.entry_review_status == 'draft' and self.data['entry_review_status'] == 'pending':
                self.entry['entry_review_status'] = 'pending'
            elif self.data['entry_review_status'] == 'pending':
                self.entry['entry_review_status'] = 'pending'
            elif self.user._role >= USER_ROLES.Reviewer:
                validated = self.fields.get('entry_review_status').validate(
                    self.data.get('entry_review_status'))
                self.entry['entry_review_status'] = validated
            else:
                raise InventoryPermissionError(
                    'You do not have the required permissions to change the review status!')

    def parse_unique_name(self):
        """ If the input data contains a _unique_name 
            make sure that the _unique_name is not already taken
            otherwise leave add a dummy value and 
            generate the unique name after all other fields have been validated
        """
        if self.data.get('_unique_name') and self.is_upsert:
            unique_name = self.data['_unique_name'].strip().lower()
            if self.is_upsert:
                check = dgraph.get_uid('_unique_name', unique_name)
                if check:
                    if check != str(self.entry_uid):
                        raise InventoryValidationError(
                            'Unique Name already taken!')
            self.entry['_unique_name'] = unique_name
        elif self.is_upsert:
            # if no _unique_name is supplied when editing, just do nothing
            pass
        else:
            self.data['_unique_name'] = 'dummy'

    @staticmethod
    def generate_unique_name(entry: dict):
        """
        Utility function to assign a unique name to every entry
        Naming convention
        [entry type] + [country (first)]  + [name (as slug without spaces)] + [date added (optional)]
        no spaces, only underscores
        all lowercase
        only ascii characters

        get the first dgraph.type that is not 'Entry'
        """
        try:
            entry_type = list(
                set(entry['dgraph.type']).difference({'Entry'}))[0]
        except:
            entry_type = ""

        # figure out which key is used for country
        country_key = list({'country', 'countries'} & set(entry.keys()))
        country_code = None
        # does the entry have the predicate at all?
        if len(country_key) > 0:
            try:
                country = entry[country_key[0]][0]
            except:
                country = entry[country_key[0]]
            try:
                # at this point of the sanitation chain the country should be a clean UID
                query_string = f"{{ q(func: uid({country})) {{ iso_3166_1_2 }} }}"
                res = dgraph.query(query_string)
                country_code = res['q'][0]['iso_3166_1_2']
            except Exception as e:
                current_app.logger.warning(
                    f'Could not retrieve country code for new entry <{entry.get("name", entry)}>: {e}', exc_info=True)

        if 'openalex' in entry:
            _name = slugify(str(entry['openalex']), separator="")
        else:
            try:
                _name = slugify(str(entry['name']), separator="")
            except KeyError:
                current_app.logger.debug(
                    f'<{entry["uid"]}> No key "name" in dict. Autoassigning')
                _name = slugify(str(entry['uid']), separator="")
                if hasattr(entry['uid'], 'original_value'):
                    entry['name'] = entry['uid'].original_value

        # assemble unique name
        unique_name = entry_type.lower() + '_'
        if country_code:
            unique_name += country_code + '_'

        unique_name += _name

        if dgraph.get_uid('_unique_name', unique_name):
            # add timestamp as fallback
            _stamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
            unique_name += f'_{_stamp}'

        return unique_name

    def process_scientificpublication(self):

        # TODO: completely rework this
        """
            Special steps for papers
            Generate a name based on author and title
        """
        for author in self.entry['authors']:
            if author.facets['sequence'] == 0:
                break
        if isinstance(author, NewID):
            for entry in self.related_entries:
                if entry['uid'] == author:
                    break
            author_name = entry['name']
        else:
            query_string = """query author ($authoruid : string) { q(func: uid($authoruid)) { name } }"""
            res = dgraph.query(query_string, variables={
                               '$authoruid': str(author)})
            author_name = res["q"][0]['name']
        if len(self.entry['authors']) > 1:
            author_name += " et al."

        try:
            title = re.match(r".*?[\?:\.!–]", str(self.entry['title']))[0]
        except:
            title = str(self.entry['title'])

        title = title.replace(':', '').replace('–', '')

        year = self.entry['date_published'].year

        self.entry['name'] = f'{author_name} ({year}): {title}'

        self.entry['_unique_name'] = slugify(self.entry['name'], separator="_")

    def process_source(self):
        """
            Special processing step for new Sources
            And also make sure that _new_ related_news_sources sources inherit fields
        """

        try:
            channel = dgraph.get_unique_name(self.entry['channel'].query)
        except KeyError:
            channel = dgraph.get_unique_name(self.data['channel'])

        try:
            country_uid = self.entry['countries'][0]
        except TypeError:
            country_uid = self.entry['countries']

        self.entry['_unique_name'] = self.source_unique_name(
            self.entry['name'], channel, country_uid)

        # inherit from main source
        for source in self.related_entries:
            if isinstance(source['uid'], NewID):
                if 'NewsSource' in source['dgraph.type']:
                    rel_channel = self.data.get('newsource_' + source['name'])
                    if rel_channel:
                        if dgraph.get_dgraphtype(rel_channel) == 'Channel':
                            source['channel'] = UID(rel_channel)
                    else:
                        raise InventoryValidationError(
                            f'No channel provided for related_news_sources source {source["name"]}! Please indicate channel')
                    source['entry_review_status'] = 'draft'
                    source['_unique_name'] = secrets.token_urlsafe(8)
                    source['publication_kind'] = self.entry.get(
                        'publication_kind')
                    source['special_interest'] = self.entry.get(
                        'special_interest')
                    source['topical_focus'] = self.entry.get('topical_focus')
                    source['geographic_scope'] = self.entry.get(
                        'geographic_scope')
                    source['country'] = self.entry.get('country')
                    source['subnational_scope'] = self.entry.get(
                        'subnational_scope')
                    source['languages'] = self.entry.get('languages')
                    source['party_affiliated'] = self.entry.get(
                        'party_affiliated')

    @staticmethod
    def source_unique_name(name, channel, country_uid):
        """
        Special case for assigning a unique to a news source
        Naming convention
        [entry type] + [country (first)]  + [name (as slug without spaces)] + [channel] + [date added (optional)]
        no spaces, only underscores
        all lowercase
        only ascii characters
        """

        name = slugify(str(name), separator="")
        channel = slugify(str(channel), separator="")
        country = dgraph.get_unique_name(country_uid)
        country = slugify(country, separator="_")

        unique_name = f'newssource_{country}_{name}_{channel}'

        if dgraph.get_uid('_unique_name', unique_name):
            # add timestamp as fallback
            _stamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
            unique_name += f'_{_stamp}'

        return unique_name
