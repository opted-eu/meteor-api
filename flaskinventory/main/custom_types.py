import datetime
from typing import Union
from flask import current_app
from flaskinventory import dgraph
from flaskinventory.errors import InventoryValidationError
from flaskinventory.flaskdgraph.dgraph_types import (String, SingleChoice, 
                                                     MultipleChoice, GeoScalar,
                                                     ListString, ListRelationship,                                                      Geo, UniqueName,
                                                     ReverseListRelationship, 
                                                     NewID, UID, Scalar)

from flaskinventory.add.external import geocode, reverse_geocode, get_wikidata
from flaskinventory.flaskdgraph.utils import validate_uid

from slugify import slugify
import secrets



"""
    Custom Fields
"""


class GeoAutoCode(Geo):

    autoinput = 'address_string'

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    def autocode(self, data, **kwargs) -> Union[GeoScalar, None]:
        return self.str2geo(data)


class AddressAutocode(Geo):

    autoinput = 'name'
    dgraph_predicate_type = 'string'

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(overwrite=True, *args, **kwargs)

    def validation_hook(self, data):
        return str(data)

    def autocode(self, data: str, **kwargs) -> Union[dict, None]:
        query_result = self.str2geo(data)
        geo_result = None
        if query_result:
            geo_result = {'address_geo': query_result}
            address_lookup = reverse_geocode(
                query_result.lat, query_result.lon)
            geo_result['address_string'] = address_lookup.get('display_name')
        return geo_result


class SourceCountrySelection(ListRelationship):

    """
        Special field with constraint to only include countries with Scope of OPTED
    """

    def __init__(self, *args, **kwargs) -> None:

        super().__init__(relationship_constraint = ['Multinational', 'Country'], 
                            allow_new=False, autoload_choices=True, 
                            overwrite=True, *args, **kwargs)

    def get_choices(self):

        query_country = '''country(func: type("Country"), orderasc: name) @filter(eq(opted_scope, true)) { uid unique_name name  }'''
        query_multinational = '''multinational(func: type("Multinational"), orderasc: name) { uid unique_name name other_names }'''

        query_string = '{ ' + query_country + query_multinational + ' }'

        choices = dgraph.query(query_string=query_string)

        if len(self.relationship_constraint) == 1:
            self.choices = {c['uid']: c['name'] for c in choices[self.relationship_constraint[0].lower()]}
            self.choices_tuples = [(c['uid'], c['name']) for c in choices[self.relationship_constraint[0].lower()]]

        else:
            self.choices = {}
            self.choices_tuples = {}
            for dgraph_type in self.relationship_constraint:
                self.choices_tuples[dgraph_type] = [(c['uid'], c['name']) for c in choices[dgraph_type.lower()]]
                self.choices.update({c['uid']: c['name'] for c in choices[dgraph_type.lower()]})


class SubunitAutocode(ListRelationship):

    def __init__(self, *args, **kwargs) -> None:

        super().__init__(relationship_constraint = ['Subunit'], 
                            allow_new=True, autoload_choices=True, 
                            overwrite=True, *args, **kwargs)
        
    def get_choices(self):

        query_string = '''{
                            q(func: type(Country)) {
                            name
                                subunit: ~country @filter(type(Subunit)) {
                                        name uid
                                }
                            }
                        }
                        '''

        choices = dgraph.query(query_string=query_string)

        self.choices = {}
        self.choices_tuples = {}

        for country in choices["q"]:
            if country.get('subunit'):
                self.choices_tuples[country['name']] = [(s['uid'], s['name']) for s in country['subunit']]
                self.choices.update({s['uid']: s['name'] for s in country['subunit']})


    def _geo_query_subunit(self, query):
        geo_result = geocode(query)
        if geo_result:
            current_app.logger.debug(f'Got a result for "{query}": {geo_result}')
            dql_string = '''
            query get_country($country_code: string) {
                q(func: eq(country_code, $country_code)) @filter(type("Country")) { uid } 
                }'''
            dql_result = dgraph.query(dql_string, variables={'$country_code': geo_result['address']['country_code']})
            try:
                country_uid = dql_result['q'][0]['uid']
            except Exception:
                raise InventoryValidationError(
                    f"Error in <{self.predicate}>! While parsing {query} no matching country found in inventory: {geo_result['address']['country_code']}")
            geo_data = GeoScalar('Point', [
                float(geo_result.get('lon')), float(geo_result.get('lat'))])

            name = None
            other_names = [query]
            if geo_result['namedetails'].get('name'):
                other_names.append(geo_result['namedetails'].get('name'))
                name = geo_result['namedetails'].get('name')

            if geo_result['namedetails'].get('name:en'):
                other_names.append(geo_result['namedetails'].get('name:en'))
                name = geo_result['namedetails'].get('name:en')

            other_names = list(set(other_names))

            if not name:
                name = query

            if name in other_names:
                other_names.remove(name)

            new_subunit = {'name': name,
                           'country': UID(country_uid),
                           'other_names': other_names,
                           'location_point': geo_data,
                           'country_code': geo_result['address']['country_code']}

            if geo_result.get('extratags'):
                if geo_result.get('extratags').get('wikidata'):
                    if geo_result.get('extratags').get('wikidata').lower().startswith('q'):
                        try:
                            new_subunit['wikidataID'] = int(geo_result.get(
                                'extratags').get('wikidata').lower().replace('q', ''))
                        except Exception as e:
                            current_app.logger.debug(
                                f'<{self.predicate}>: Could not parse wikidata ID in subunit "{query}": {e}')

            return new_subunit
        else:
            return False

    def _resolve_subunit(self, subunit):
        geo_query = self._geo_query_subunit(subunit)
        if geo_query:
            current_app.logger.debug(f'parsing result of querying {subunit}: {geo_query}')
            geo_query['dgraph.type'] = ['Subunit']
            # prevent duplicates
            geo_query['unique_name'] = f"{slugify(subunit, separator='_')}_{geo_query['country_code']}"
            duplicate_check = dgraph.get_uid(
                'unique_name', geo_query['unique_name'])
            if duplicate_check:
                geo_query = {'uid': UID(duplicate_check)}
            else:
                geo_query['uid'] = NewID(
                    f"_:{slugify(secrets.token_urlsafe(8))}")
            return geo_query
        else:
            raise InventoryValidationError(
                f'Invalid Data! Could not resolve geographic subunit {subunit}')

    def validation_hook(self, data):
        uid = validate_uid(data)
        if not uid:
            if not self.allow_new:
                raise InventoryValidationError(
                    f'Error in <{self.predicate}>! provided value is not a UID: {data}')
            current_app.logger.debug(f'New subunit, trying to resolve "{data}"')
            new_subunit = self._resolve_subunit(data)
            return new_subunit
        if self.relationship_constraint:
            entry_type = dgraph.get_dgraphtype(uid)
            if entry_type not in self.relationship_constraint:
                raise InventoryValidationError(
                    f'Error in <{self.predicate}>! UID specified does not match constrain, UID is not a {self.relationship_constraint}!: uid <{uid}> <dgraph.type> <{entry_type}>')        
        return {'uid': UID(uid)}

    def validate(self, data, facets=None) -> list:
        if isinstance(data, str):
            data = data.split(',')
        data = set([item.strip() for item in data if item.strip() != ''])
        uids = []
        for item in data:
            uid = self.validation_hook(item)
            if uid:
                uids.append(uid)

        return uids
        

class OrganizationAutocode(ReverseListRelationship):

    def __init__(self, predicate_name, *args, **kwargs) -> None:

        super().__init__(predicate_name,
                            relationship_constraint = 'Organization', 
                            allow_new=True, 
                            autoload_choices=False, 
                            overwrite=True, 
                            *args, **kwargs)

    def validation_hook(self, data, node, facets=None):
        uid = validate_uid(data)
        if not uid:
            if not self.allow_new:
                raise InventoryValidationError(
                    f'Error in <{self._predicate}>! provided value is not a UID: {data}')
            new_org = {'uid': NewID(data, facets=facets), self._target_predicate: node, 'name': data}
            new_org = self._resolve_org(new_org)
            if self.default_predicates:
                new_org.update(self.default_predicates)
            return new_org
        if self.relationship_constraint:
            entry_type = dgraph.get_dgraphtype(uid)
            if entry_type not in self.relationship_constraint:
                raise InventoryValidationError(
                    f'Error in <{self._predicate}>! UID specified does not match constrain, UID is not a {self.relationship_constraint}!: uid <{uid}> <dgraph.type> <{entry_type}>')        
        return {'uid': UID(uid, facets=facets), self._target_predicate: node}

    def validate(self, data, node, facets=None) -> Union[UID, NewID, dict]:
        if isinstance(data, str):
            data = data.split(',')

        data = set([item.strip() for item in data])
        uids = []

        for item in data:
            uid = self.validation_hook(item, node, facets=facets)
            uids.append(uid)
        
        return uids

    def _resolve_org(self, org):

        geo_result = geocode(org['name'])
        if geo_result:
            try:
                org['address_geo'] = GeoScalar('Point', [
                    float(geo_result.get('lon')), float(geo_result.get('lat'))])
            except:
                pass
            try:
                address_lookup = reverse_geocode(
                    geo_result.get('lat'), geo_result.get('lon'))
                org['address_string'] = address_lookup['display_name']
            except:
                pass

        wikidata = get_wikidata(org['name'])

        if wikidata:
            for key, val in wikidata.items():
                if key not in org.keys():
                    org[key] = val
        
        if self.relationship_constraint:
            org['dgraph.type'] = self.relationship_constraint
            
        return org


class OrderedListString(ListString):

    def validate(self, data, facets=None, **kwargs):
        data = self.validation_hook(data)
        ordered_data = []
        if not facets:
            facets = {"sequence": 0}
        if isinstance(data, (list, set, tuple)):
            for i, item in enumerate(data):
                f = facets.copy()
                f.update(sequence=i)
                if isinstance(item, (str, int, datetime.datetime, datetime.date)):
                    ordered_data.append(Scalar(item, facets=f))
                elif hasattr(item, "facets"):
                    ordered_data.append(item.update_facets(f))
                else:
                    raise InventoryValidationError(
                        f'Error in <{self.predicate}>! Do not know how to handle {type(item)}. Value: {item}')
            return ordered_data
        elif isinstance(data, (str, int, datetime.datetime, datetime.date)):
            return Scalar(data, facets=facets)
        elif hasattr(data, facets):
            data.update_facets(facets)
            return data
        else:
            raise InventoryValidationError(
                f'Error in <{self.predicate}>! Do not know how to handle {type(data)}. Value: {data}')


class SingleChoiceInt(SingleChoice):

    dgraph_predicate_type = 'int'
    dgraph_directives = ['@index(int)']

    
class MultipleChoiceInt(MultipleChoice):

    dgraph_predicate_type = '[int]'
    dgraph_directives = ['@index(int)']

    def validation_hook(self, data):
        if isinstance(data, str):
            data = data.split(',')
        if not isinstance(data, list):
            raise InventoryValidationError(
                f'Error in <{self.predicate}>! Provided data cannot be coerced to "list": {data}')
        for val in data:
            if val.strip() not in self.values:
                raise InventoryValidationError(
                    f"Wrong value provided for {self.predicate}: {val}. Value has to be one of {', '.join(self.values)}")
            if val.strip().lower() == 'na':
                data = None

        return data


class GitHubAuto(String):

    def validation_hook(self, data):
        if "github" in data:
            data = data.replace('https://www.', '')
            data = data.replace('http://www.', '')
            data = data.replace('https://', '')
            data = data.replace('http://', '')
            data = data.replace('github.com/', '')
            if data.startswith('/'):
                data = data[1:]
        
        return data