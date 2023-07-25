import typing as t
from functools import wraps
import inspect
import re

from werkzeug.routing import parse_rule
from flask import Blueprint, jsonify, current_app, request, abort, url_for, render_template
from flask.scaffold import F

from flask_login import current_user, login_required

from flaskinventory.flaskdgraph import dql
from flaskinventory.flaskdgraph import build_query_string
from flaskinventory.flaskdgraph.utils import validate_uid, restore_sequence
from flaskinventory.view.dgraph import get_entry, get_comments, get_rejected
from flaskinventory.view.utils import can_view

from flaskinventory.main.model import *

from flaskinventory.api.sanitizer import Sanitizer

""" Blueprint Class Declaration """

class API(Blueprint):

    routes = {}

    @staticmethod
    def abort(status_code, message=None):
        response = jsonify({
            'status': status_code,
            'message': message or "An error occurred ¯\_(ツ)_/¯",
        })
        response.status_code = status_code
        return response


    def query_params(self, f):
        """
        Decorator that will read the query parameters for the request.
        The names are the names that are mapped in the function.
        """
        func_params = inspect.signature(f).parameters

        @wraps(f)
        def logic(*args, **kw):
            params = dict(kw)
            for parameter_name, par in func_params.items():
                if parameter_name in request.args:
                    p = request.args.get(parameter_name)
                    try:
                        if t.get_origin(par.annotation) == list:
                            if isinstance(p, list):
                                p = [par.annotation.__args__[0](x) for x in p]
                            else:
                                p = [par.annotation.__args__[0](p)]
                        else:
                            p = par.annotation(p)
                    except ValueError:
                        abort(400)
                    params[parameter_name] = p

            return f(**params)
        return logic

    def route(self, rule: str, **options: t.Any) -> t.Callable[[F], F]:
        """ Custom extension of Flask default routing / rule creation 
            This decorator extract function arguments and details and 
            stores it the blueprint class (the dict "routes")
            This enables serving the OpenAPI scheme
            The decorator also applies the @query_params decorator
        """

        methods = options.get('methods', ['GET'])

        def decorator(f: F) -> F:
            """ Custom extension """
            self.routes[rule] = {} # register rule in API

            # get all Path parameters
            # we need that later to check 
            # which function args are query paramters 
            path_parameters = []
            query_parameters = []
            request_body_params = []
            for triple in parse_rule(rule):
                _, _, v = triple
                path_parameters.append(v)

            # print('*'* 80)
            # print(f.__name__)
            sig = inspect.signature(f)
            # print(sig.return_annotation)
            for arg, par in sig.parameters.items():
                # print('arg', arg)
                # print(arg, par)
                # print(t.get_origin(par.annotation))
                # if NoneType in par.annotation -> optional
                # print(par.default, par.annotation, par.name)
                # print('par default', type(par.default), par.default)
                # here we check whether the argument should 
                # be treated as a query parameter
                if par.name not in path_parameters:
                    if 'POST' in methods:
                        request_body_params.append(par.name)
                    else:
                        query_parameters.append(par.name)
            # try:
            #     return_val = sig.return_annotation
            #     if t.get_origin(return_val) is t.Union:
            #         return_val = [a for a in return_val.__args__]
                
            # except:
            #     return_val = []
            self.routes[rule]['parameters'] = sig.parameters
            self.routes[rule]['query_parameters'] = query_parameters
            self.routes[rule]['request_body_params'] = request_body_params
            self.routes[rule]['path_parameters'] = path_parameters 
            self.routes[rule]['methods'] = methods
            self.routes[rule]['description'] = inspect.getdoc(f)
            self.routes[rule]['func'] = f.__name__
            self.routes[rule]['path'] = re.sub(r'<(?P<converter>[a-zA-Z_][a-zA-Z0-9_]*\:).*?>', '', rule).replace('<', '{').replace('>', '}')
            self.routes[rule]['responses'] = sig.return_annotation

            # Final step: apply @query_params to all routing funtions
            # This way, every function has request arguments handled
            # as keyword arguments
            f_wrapped = self.query_params(f)
            
            """ Business as usual (see flask.Scaffolding) """
            endpoint = options.pop("endpoint", None)
            self.add_url_rule(rule, endpoint, f_wrapped, **options)
            return f_wrapped

        return decorator

api = API('api', __name__)

""" Schema API routes """

#: Maps Flask/Werkzeug rooting types to Swagger ones
PATH_TYPES = {
    'int': 'integer',
    'float': 'number',
    'string': 'string',
    'default': 'string',
    str: 'string',
    int: 'integer',
    dict: 'object',
    bool: 'boolean'
}


@api.route('/swagger')
def swagger():
    """ Serves the Swagger UI """
    return render_template('swagger/swagger.html')

@api.route('/openapi.json')
def schema() -> dict:
    """ Serves the schema according to OpenAPI specifications """
    open_api = {
            "openapi": "3.0.3",
            "info": {
                "title": "Meteor API",
                "description": "API for Meteor clients",
                "termsOfService": "http://meteor.opted.eu/about/",
                "contact": {
                "email": "info@opted.eu"
                },
                "license": {
                    "name": "GPL-3.0",
                },
                "version": "0.1"
            },
            # "externalDocs": {
            #     "description": "Find out more about Swagger",
            #     "url": "http://swagger.io"
            # },
            "servers": [
                {
                "url": url_for('.schema', _external=True).replace('openapi.json', '')
                }
            ],
            }
    open_api['components'] = Schema.provide_types()
    open_api['components']['parameters'] = Schema.provide_queryable_predicates()
    open_api['paths'] = {}

    query_params_references = [{'$ref': '#/components/parameters/' + k} for k in open_api['components']['parameters'].keys()]

    for rule, details in api.routes.items():
        if rule in ['/openapi.json', '/swagger']:
            continue
        path = details['path']
        open_api['paths'][path] = {}
        parameters = []
        for param, param_type in details['parameters'].items():
            if param in details['request_body_params']:
                continue
            if param in details['path_parameters']:
                _in = 'path'
                required = True
            elif param in details['query_parameters']:
                _in = 'query'
                required = False

            p = {'name': param,
                 'in': _in,
                 'required': required
                 }
            if t.get_origin(param_type.annotation) is list:
                p['schema'] = {'type': 'array',
                               'items': {
                                   'type': PATH_TYPES[param_type.annotation.__args__[0]]
                                   }
                                }
            else:
                p['schema'] = {'type': PATH_TYPES[param_type.annotation]}

            if not param_type.default is param_type.empty:
                p['default'] = param_type.default
            parameters.append(p)
        
        # very unelegant solution
        if rule in ['/query', '/query/count']:
            parameters += query_params_references

        responses = {
            "description": "success", # dont know how to describe that in more detail
            "content": {
            "application/json": {
                "schema": {}
                }
            }       
        }

        if t.get_origin(details['responses']) is t.Union:
            oneOf = []
            for r in details['responses'].__args__:
                if issubclass(r, Schema):
                    r_type = r.__name__
                else:
                    r_type = PATH_TYPES[r]
                oneOf.append({'$ref': "#/components/schemas/" + r_type})
            responses["content"]["application/json"]["schema"] = {
                'type': 'object',
                'oneOf': oneOf
                }
        elif t.get_origin(details['responses']) is list:
            r = details['responses'].__args__[0]
            if issubclass(r, Schema):
                r_type = r.__name__
            else:
                r_type = PATH_TYPES[r]
            responses["content"]["application/json"]["schema"] = {
                'type': 'array',
                'items': {
                    '$ref': "#/components/schemas/" + r_type
                    }
                }
        
        else:
            r = details['responses']
            if issubclass(r, Schema):
                responses["content"]["application/json"]["schema"] = {
                    '$ref': "#/components/schemas/" + r.__name__
                }
            else:
                responses["content"]["application/json"]["schema"] = {
                    'type': PATH_TYPES[r]
                }

        for method in details['methods']:
            open_api['paths'][path][method.lower()] = {
                'description': details['description'],
                # 'operationId': details['func'],
                'parameters': parameters,
                'responses': {'200': responses,
                              '404': {'description': 'Not found'}}
                }
            if method == 'POST':
                open_api['paths'][path][method.lower()]['requestBody'] = {
                    'required': True,
                    'content': {
                        'application/json': {
                            'schema': {}

                        }
                    }
                }
            
    return jsonify(open_api)

@api.route('/schema/type/<dgraph_type>')
def get_dgraph_type(dgraph_type: str, new: bool = False) -> dict:
    """ 
        Get all predicates of given type alongside a description.
        This route is practically a subset of the entire schema.
        Intended as utility for form generation.

        With parameter `new=True` this route does not return system managed predicates.
        (only returns the predicates for prompting the user).
    """
    dgraph_type = Schema.get_type(dgraph_type)
    if not dgraph_type:
        api.abort(404)
    if new:
        result = {k: v.openapi_component for k, v in Schema.get_predicates(dgraph_type).items() if v.new}
    else:
        result = {k: v.openapi_component for k, v in Schema.get_predicates(dgraph_type).items()}
    return jsonify(result)
    

@api.route('/schema/predicate/<predicate>')
def get_predicate(predicate: str) -> dict:
    """ 
        Get choices for given predicate. 
        This route is intended as a utility for form generation.
        For example, the country selection menu.
    """
    try:
        predicate = Schema.predicates()[predicate]
    except KeyError:
        api.abort(404)

    if not hasattr(predicate, 'choices'):
        return jsonify({'warning': f'Predicate <{predicate}> has no available choices'})
    
    if 'uid' in predicate.dgraph_predicate_type:
        if predicate.autoload_choices:
            predicate.get_choices()
        else:
            return jsonify({'warning': f'Available choices for <{predicate}> are not automatically loaded'})

    result = predicate.choices

    return jsonify(result)
    

""" View Routes """

@api.route('/view/recent')
def view_recent(limit: int = 5) -> t.List[Entry]:
    """ get the most recent entries. Default 5. Max: 50 """
    if limit > 50:
        limit = 50
    if limit < 1:
        limit = 1
    query_string = '''query getRecent ($limit : int)
                    {
                        data(func: has(dgraph.type), orderdesc: _date_created, first: $limit) 
                            @filter(eq(entry_review_status, "accepted") AND has(_date_created)) {
                                uid
                                _unique_name 
                                name 
                                dgraph.type 
                                title
                                _date_created
                                channel { name }
                                country { name }
                            }
                        }'''
    
    result = dgraph.query(query_string, variables={'$limit': str(limit)})
    for entry in result['data']:
        if 'Entry' in entry['dgraph.type']:
            entry['dgraph.type'].remove('Entry')
        if 'Resource' in entry['dgraph.type']:
            entry['dgraph.type'].remove('Resource')

    return jsonify(result)

@api.route('/view/uid/<uid>')
def view_uid(uid: str) -> t.Union[Entry, PoliticalParty,
                                  Organization, JournalisticBrand, 
                                  NewsSource, Government, 
                                  Parliament, Person,
                                  Channel, Country,
                                  Multinational, Subnational,
                                  Archive, Dataset,
                                  Tool, ScientificPublication,
                                  Author, Language,
                                  ProgrammingLanguage,
                                  Operation, 
                                  FileFormat,
                                  MetaVariable,
                                  ConceptVariable,
                                  TextType,
                                  UnitOfAnalysis,
                                  Collection,
                                  LearningMaterial]:
    """ detail view of a single entry by UID (hex value) """
    uid = validate_uid(uid)
    if not uid:
        return api.abort(404, message="Invalid UID")

    data = get_entry(uid=uid)

    if not data:
        return api.abort(404, message=f'The requested entry <{uid}> could not be found!')

    if not can_view(data, current_user):
        if current_user.is_authenticated:
            response = jsonify({
                'status': 403,
                'message': "You do not have the permissions to view this entry."})
            response.status_code = 403
            return api.abort(403, message="You do not have the permissions to view this entry.")
        else:
            return api.abort(403, message="You do not have the permissions to view this entry. Try to login?")
        
    return jsonify(data)



@api.route('/view/entry/<unique_name>')
def view_unique_name(unique_name: str) -> t.Union[Entry, PoliticalParty,
                                  Organization, JournalisticBrand, 
                                  NewsSource, Government, 
                                  Parliament, Person,
                                  Channel, Country,
                                  Multinational, Subnational,
                                  Archive, Dataset,
                                  Tool, ScientificPublication,
                                  Author, Language,
                                  ProgrammingLanguage,
                                  Operation, 
                                  FileFormat,
                                  MetaVariable,
                                  ConceptVariable,
                                  TextType,
                                  UnitOfAnalysis,
                                  Collection,
                                  LearningMaterial]:
    """ detail view of a single entry by unique name (human readable ID) """
        
    data = get_entry(unique_name=unique_name)

    if not data:
        return api.abort(404, message=f'The requested entry "{unique_name}" could not be found!')

    if not can_view(data, current_user):
        if current_user.is_authenticated:
            response = jsonify({
                'status': 403,
                'message': "You do not have the permissions to view this entry."})
            response.status_code = 403
            return api.abort(403, message="You do not have the permissions to view this entry.")
        else:
            return api.abort(403, message="You do not have the permissions to view this entry. Try to login?")

    return jsonify(data)

# TODO: add permission validation
@login_required
@api.route('/view/comments/<uid>')
def view_comments(uid: str) -> t.List[Comment]:
    """ list all comments for this entry """
    
    try:
        data = get_comments(uid)
    except ValueError:
        return api.abort(404, message=f'could not get comments for UID <{uid}>')

    return jsonify(data)

@api.route('/view/ownership/<uid>')
def view_ownership(uid: str) -> t.List[Entry]:
    """ get data for plotting ownership network """

    uid = validate_uid(uid)
    if not uid:
        return api.abort(404, message=f'Invalid UID <{uid}>')
    query_string = """query ownership($id: string) {
                        tmp(func: uid($id)) @recurse  {
                            u as uid owns publishes ~owns ~publishes                                     
                        }
                        q(func: uid(uid(u))) 
                            @filter(eq(entry_review_status, "accepted") AND 
                                eq(dgraph.type,["Organization", "NewsSource", "PoliticalParty"]))  {
                            name uid dgraph.type
                            channel { _unique_name }
                            publishes @filter(eq(entry_review_status, "accepted")) { uid }
                            owns @filter(eq(entry_review_status, "accepted")) { uid }
                        }
                    }"""
    result = dgraph.query(query_string=query_string, variables={'$id': uid})
    return jsonify(result['q'])


@login_required
@api.route("/view/rejected/<uid>")
def view_rejected(uid: str) -> Rejected:
    """ detail view of a rejected entry """
    uid = validate_uid(uid)
    if not uid:
        return api.abort(404, message='Invalid ID provided!')

    data = get_rejected(uid)

    if not data:
        return api.abort(404)

    if not can_view(data, current_user):
        return api.abort(403, message='You tried to view a rejected entry. Make sure you are logged in and have the right permissions.')

    return jsonify(data)

""" Query Routes """


@api.route('/quicksearch')
def quicksearch(term: str = None, limit: int = 10) -> t.List[Entry]:
    """ perform text search in name fields of entries. 
        Also searches for unique identifiers such as DOI
    """
    if term is None:
        return api.abort(400)
    if len(term) < 3:
        return api.abort(400, message="The search term has to be at least 3 characters long")
    
    if limit > 50:
        limit = 50
    if limit < 1:
        limit = 1
    
    query_regex = f'/^{strip_query(term)}/i'
    query_string = f'''
            query quicksearch($name: string, $name_regex: string, $limit: int)
            {{
            field1 as a(func: anyofterms(name, $name))
            field2 as b(func: anyofterms(alternate_names, $name))
            field3 as c(func: anyofterms(title, $name))
            field4 as d(func: eq(doi, $name))
            field5 as e(func: eq(arxiv, $name))
            field6 as g(func: regexp(name, $name_regex))
            field7 as h(func: regexp(_unique_name, $name_regex))
            
            data(func: uid(field1, field2, field3, field4, field5, field6, field7), first: $limit) 
                @normalize @filter(eq(entry_review_status, "accepted")) {{
                    uid 
                    _unique_name: _unique_name 
                    name: name 
                    alternate_names: alternate_names
                    type: dgraph.type 
                    title: title
                    channel {{ channel: _unique_name }}
                    doi: doi
                    arxiv: arxiv
                }}
            }}
        '''
    result = dgraph.query(query_string, variables={'$name': term, 
                                                   '$name_regex': query_regex,
                                                   '$limit': str(limit)})
    for item in result['data']:
        if 'Entry' in item['type']:
            item['type'].remove('Entry')
    return jsonify(result['data'])



@api.route("/query")
def query(_max_results: int = 25, _page: int = 1) -> t.List[Entry]:
    """ perform query based on dgraph query parameters """

    r = {k: v for k, v in request.args.to_dict(
        flat=False).items() if v[0] != ''}
    
    if len(r) > 0:
        query_string = build_query_string(r)
        if query_string:
            search_terms = request.args.get('_terms', '')
            if not search_terms == '':
                variables = {'$searchTerms': search_terms}
            else:
                variables = None

            result = dgraph.query(query_string, variables=variables)
            result = result['q']

            # clean 'Entry' from types
            if len(result) > 0:
                for item in result:
                    if 'Entry' in item['dgraph.type']:
                        item['dgraph.type'].remove('Entry')
                    if any(t in item['dgraph.type'] for t in ['ScientificPublication', 'Tool', 'Corpus', 'Dataset']):
                        restore_sequence(item)

        return jsonify(result)
    else:
        return api.abort(400)


@api.route("/query/count")
def query_count() -> int:
    """ get total number of hits for query """

    r = {k: v for k, v in request.args.to_dict(
        flat=False).items() if v[0] != ''}
    
    if len(r) > 0:
        query_string = build_query_string(r, count=True)
        if query_string:
            search_terms = request.args.get('_terms', '')
            if not search_terms == '':
                variables = {'$searchTerms': search_terms}
            else:
                variables = None

            result = dgraph.query(query_string, variables=variables)
            result = result['total'][0]['count']

        return jsonify(result)
    else:
        return api.abort(400)

""" Lookup Routes """    

@api.route('/lookup')
def lookup(query: str = None, predicate: str = None, dgraph_types: t.List[str] = ['Entry']) -> t.List[Entry]:
    """
        Generic Lookup Endpoint. Search entries by names (i.e., strings)
        Can perform the following

        - `query`: your search query (default uses equality matching)
        - `predicate`: predicate to query;
        - special case for `predicate` is `"name"` which searches name-like fields (`name`, `_unique_name`, `alternate_names`, `title`)
        
        Filters:

        - `dgraph_types`: provide a list of types to filter
    """
    if not query or not predicate:
        return api.abort(400, message='Incorrect request parameters provided.')

    # Ensure private dgraph.types are protected here
    if any([Schema.is_private(t) for t in dgraph_types]):
        return api.abort(403, message='You cannot access this dgraph.type')
    
    # TODO: add check whether predicate is not private
    dgraph_types = [dql.type_(t) for t in dgraph_types]
    
    if predicate == 'name':
        query = strip_query(query)
        query_regex = dql.GraphQLVariable(query_regex=f"/{query}/i")
        query_beginning = dql.GraphQLVariable(query_beginning=f'/^{query}/i')

        field1 = dql.QueryBlock(dql.regexp(name=query_regex), 
                        query_filter=dgraph_types,
                        filter_connector="OR",
                        block_name="field1 as var")
        
        field2 = dql.QueryBlock(dql.regexp(alternate_names=query_regex),
                                query_filter=dgraph_types,
                                filter_connector="OR",
                                block_name="field2 as var")

        field3 = dql.QueryBlock(dql.regexp(_unique_name=query_regex),
                                query_filter=dgraph_types,
                                filter_connector="OR",
                                block_name="field3 as var")
        
        field4 = dql.QueryBlock(dql.allofterms(title=query),
                                query_filter=dgraph_types,
                                filter_connector="OR",
                                block_name="field4 as var")

        data = dql.QueryBlock(dql.uid("field1, field2, field3, field4"),
                            fetch=['uid', 
                                   '_unique_name', 
                                   'name', 
                                   'title',
                                   'dgraph.type',
                                   'alternate_names',
                                   'last_known_institution',
                                   'countries { name uid _unique_name }',
                                   'country { name uid _unique_name }',
                                   'channel { name uid _unique_name }',
                                   'authors @facets { name uid _unique_name }',
                                   '_authors_fallback @facets'],
                            block_name="data")

        dql_query = dql.DQLQuery('lookup', blocks=[field1, field2, field3, field4, data])

    else:            
        query_variable = dql.GraphQLVariable(query=query)
        fetch = ['uid', 
                '_unique_name', 
                'name', 
                'doi',
                'arxiv',
                'openalex',
                'pypi',
                'github',
                'cran',
                'dgraph.type',
                'countries { name uid _unique_name }',
                'country { name uid _unique_name }',
                'channel { name uid _unique_name }',
                'authors @facets { name uid _unique_name }',
                '_authors_fallback @facets']
        if predicate not in fetch:
            fetch.append(predicate)
        dql_query = dql.DQLQuery(block_name="data", func=dql.eq(predicate, query_variable), 
                        query_filter=dgraph_types,
                        fetch=fetch)
    try:
        result = dgraph.query(dql_query)
        return jsonify(result['data'])
    except Exception as e:
        current_app.logger.warning(f'could not lookup source with query "{query}". {e}')
        return api.abort(500, message=f'{e}')

""" Add new Entries """

@api.route('/add/check')
def duplicate_check(name: str = None, dgraph_type: str = None) -> t.List[Entry]:
    """ 
        perform potential duplicate check. 
        
        If entries with similar name (or DOI) are found then it returns list of potential duplicates 
    """
    if not name or not dgraph_type:
        api.abort(400)

    dgraph_type = Schema.get_type(dgraph_type)
    if not dgraph_type:
        api.abort(400, message='Invalid DGraph type')

    query = name.replace('https://', '').replace('http://', '').replace('www.', '')
    query = strip_query(query)
    identifier = name.strip()
    query_string = f'''
            query database_check($query: string, $identifier: string)
            {{
                field1 as a(func: regexp(name, /$query/i)) @filter(type("{dgraph_type}"))
                field2 as b(func: allofterms(name, $query)) @filter(type("{dgraph_type}"))
                field3 as c(func: allofterms(alternate_names, $query)) @filter(type("{dgraph_type}"))
                field4 as d(func: match(name, $query, 3)) @filter(type("{dgraph_type}"))
                field5 as e(func: allofterms(title, $query)) @filter(type("{dgraph_type}"))
                doi as f(func: eq(doi, $identifier))
                arxiv as g(func: eq(arxiv, $identifier))
                cran as h(func: eq(cran, $identifier))
                pypi as i(func: eq(pypi, $identifier))
                github as j(func: eq(github, $identifier))

                check(func: uid(field1, field2, field3, field4, field5, doi, arxiv, cran, pypi, github)) {{
                    uid
                    expand(_all_) {{ name }}
                    }}
            }}
    '''
    result = dgraph.query(query_string, variables={
                            '$query': query, '$identifier': identifier})
    
    return jsonify(result['check'])
    

@api.route('/add/<dgraph_type>', methods=['POST'])
def add_new_entry(dgraph_type: str) -> dict:
    """
        Send data for new entry. Data has to be in JSON format.

        If the new entry was added successfully, the JSON response includes a `redirect` 
        key which shows the link to view the new entry.
    """
    dgraph_type = Schema.get_type(dgraph_type)
    if not dgraph_type:
        api.abort(400, message="Invalid DGraph type")

    current_app.logger.debug(f'Received JSON: \n{request.json}')
    try:
        if 'uid' in request.json.keys():
            sanitizer = Sanitizer.edit(request.json, dgraph_type=NewsSource)
        else:
            sanitizer = Sanitizer(request.json, dgraph_type=NewsSource)
        current_app.logger.debug(f'Processed Entry: \n{sanitizer.entry}\n{sanitizer.related_entries}')
        current_app.logger.debug(f'Set Nquads: {sanitizer.set_nquads}')
        current_app.logger.debug(f'Delete Nquads: {sanitizer.delete_nquads}')
    except Exception as e:
        import traceback
        error = {'error': f'{e}'}
        tb_str = ''.join(traceback.format_exception(None, e, e.__traceback__))
        current_app.logger.error(tb_str)
        return api.abort(500, message=error)

    try:
        if sanitizer.is_upsert:
            result = dgraph.upsert(sanitizer.upsert_query, del_nquads=sanitizer.delete_nquads, set_nquads=sanitizer.set_nquads)
        else:
            result = dgraph.upsert(None, del_nquads=sanitizer.delete_nquads, set_nquads=sanitizer.set_nquads)
    except Exception as e:
        error = {'error': f'{e}'}
        tb_str = ''.join(traceback.format_exception(
            None, e, e.__traceback__))
        current_app.logger.error(tb_str)
        current_app.logger.error(f'Upsert Query: {sanitizer.upsert_query}')
        current_app.logger.error(f'Delete nquads: {sanitizer.delete_nquads}')
        current_app.logger.error(f'Set nquads: {sanitizer.set_nquads}')
        return api.abort(500, message=error)

    if result:
        if sanitizer.is_upsert:
            uid = str(sanitizer.entry_uid)
        else:
            newuids = dict(result.uids)
            uid = newuids[str(sanitizer.entry_uid).replace('_:', '')]
        response = {'redirect': url_for('api.view_uid', uid=uid),
                    'uid': uid}

        return jsonify(response)
    else:
        current_app.logger.error(f'DGraph Error - Could not perform mutation: {sanitizer.set_nquads}')
        return api.abort(500, message='DGraph Error - Could not perform mutation')


""" External APIs """

@api.route('/external/cran/<package>')
def cran(package: str) -> dict:
    """ 
    Make an API call to CRAN. Get meta data on a CRAN package. 
    
    (CRAN's cors policy requires this workaround) 
    """
    package = package.strip()
    from flaskinventory.add.external import cran

    result = cran(package)
    if result:
        return jsonify(result)
    else:
        return api.abort(404, message=f'Package <{package}> not found. Check the spelling?')


from flaskinventory.add.external import (instagram, twitter, get_wikidata, telegram, vkontakte,
                                         parse_meta, siterankdata, find_sitemaps, find_feeds,
                                         build_url)

@api.route('/external/twitter', methods=['POST'])
def fetch_twitter(handle: str) -> dict:
    try:
        profile = twitter(handle.replace('@', ''))
    except Exception as e:
        return api.abort(404, message=f"Twitter profile not found: {handle}. {e}")

    result = {
        'name': handle.lower().replace('@', '')
    }

    if profile.get('fullname'):
        result['alternate_names'] = [profile['fullname']]
    if profile.get('followers'):
        result['audience_size'] = str(datetime.date.today())
        result['audience_size|count'] = int(profile['followers'])
        result['audience_size|unit'] = 'followers'
        result['audience_size_recent'] = int(profile['followers'])
        result['audience_size_recent|unit'] = 'followers'
    if profile.get('joined'):
        result['date_founded'] = profile.get('joined').isoformat()
    result['verified_account'] = profile.get('verified')
    return jsonify(result)

def parse_wikidata(self):
    predicates = Schema.get_predicates(self.dgraph_type)
    if not self.is_upsert:
        wikidata = get_wikidata(self.data.get('name'))
        if wikidata:
            for key, val in wikidata.items():
                if val is None:
                    continue
                if key not in predicates.keys():
                    continue
                if key not in self.entry.keys():
                    self.entry[key] = val
                elif key == 'alternate_names':
                    if 'alternate_names' not in self.entry.keys():
                        self.entry['alternate_names'] = []
                    self.entry[key] += val

def process_source(self, channel):
    if channel == 'website':
        self.resolve_website()
        self.fetch_siterankdata()
        self.fetch_feeds()
    elif channel == 'instagram':
        self.fetch_instagram()
    elif channel == 'twitter':
        self.fetch_twitter()
    elif channel == 'vkontakte':
        self.fetch_vk()
    elif channel == 'telegram':
        self.fetch_telegram()
    elif channel == 'facebook':
        self.entry['identifier'] = self.entry['name']


def resolve_website(self):
    # first check if website exists
    entry_name = str(self.entry['name'])
    try:
        result = parse_meta(entry_name)
        names = result['names']
        urls = result['urls']
    except:
        raise InventoryValidationError(
            f"Could not resolve website! URL provided does not exist: {self.data.get('name')}")

    if urls == False:
        raise InventoryValidationError(
            f"Could not resolve website! URL provided does not exist: {self.data.get('name')}")

    # clean up the display name of the website
    entry_name = entry_name.replace(
        'http://', '').replace('https://', '').lower()

    if entry_name.endswith('/'):
        entry_name = entry_name[:-1]

    # append automatically retrieved names to alternate_names
    if len(names) > 0:
        if 'alternate_names' not in self.entry.keys():
            self.entry['alternate_names'] = []
        for name in names:
            if name.strip() == '':
                continue
            if name not in self.entry['alternate_names']:
                self.entry['alternate_names'].append(name.strip())

    if len(urls) > 0:
        if 'alternate_names' not in self.entry.keys():
            self.entry['alternate_names'] = []
        for url in urls:
            if url.strip() == '':
                continue
            if url not in self.entry['alternate_names']:
                self.entry['alternate_names'].append(url.strip())

    self.entry['name'] = Scalar(entry_name)
    self.entry['identifier'] = build_url(
        self.data['name'])

def fetch_siterankdata(self):
    try:
        daily_visitors = siterankdata(self.entry['name'])
    except Exception as e:
        current_app.logger.warning(
            f'Could not fetch siterankdata for {self.entry["name"]}! Exception: {e}')
        daily_visitors = None

    if daily_visitors:
        self.entry['audience_size'] = Scalar(datetime.date.today(), facets={
            'count': daily_visitors,
            'unit': "daily visitors",
            'data_from': f"https://siterankdata.com/{str(self.entry['name']).replace('www.', '')}"})

def fetch_feeds(self):
    self.entry['channel_feeds'] = []
    sitemaps = find_sitemaps(self.entry['name'])
    if len(sitemaps) > 0:
        for sitemap in sitemaps:
            self.entry['channel_feeds'].append(
                Scalar(sitemap, facets={'kind': 'sitemap'}))

    feeds = find_feeds(self.entry['name'])

    if len(feeds) > 0:
        for feed in feeds:
            self.entry['channel_feeds'].append(
                Scalar(feed, facets={'kind': 'rss'}))

def fetch_instagram(self):
    profile = instagram(self.data['name'].replace('@', ''))
    if profile:
        self.entry['name'] = self.data[
            'name'].lower().replace('@', '')
        self.entry['identifier'] = self.data[
            'name'].lower().replace('@', '')
    else:
        raise InventoryValidationError(
            f"Instagram profile not found: {self.data['name']}")

    if profile.get('fullname'):
        try:
            self.entry['alternate_names'].append(profile['fullname'])
        except KeyError:
            self.entry['alternate_names'] = [profile['fullname']]
    if profile.get('followers'):
        facets = {'count': int(
            profile['followers']),
            'unit': 'followers'}
        self.entry['audience_size'] = Scalar(
            str(datetime.date.today()), facets=facets)
    self.entry['verified_account'] = profile['verified']

def fetch_vk(self):
    self.entry['identifier'] = self.data[
        'name'].replace('@', '')
    try:
        profile = vkontakte(self.data['name'].replace('@', ''))
    except Exception as e:
        raise InventoryValidationError(
            f"VKontakte profile not found: {self.data['name']}. {e}")

    self.entry['name'] = self.data[
        'name'].lower().replace('@', '')

    if profile.get('fullname'):
        try:
            self.entry['alternate_names'].append(profile['fullname'])
        except KeyError:
            self.entry['alternate_names'] = [profile['fullname']]
    if profile.get('followers'):
        facets = {'count': int(
            profile['followers']),
            'unit': 'followers'}
        self.entry['audience_size'] = Scalar(
            str(datetime.date.today()), facets=facets)
    self.entry['verified_account'] = profile.get('verified')
    if profile.get('description'):
        self.entry['description'] = profile.get('description')

def fetch_telegram(self):
    self.entry['identifier'] = self.data[
        'name'].replace('@', '')
    try:
        profile = telegram(self.data['name'].replace('@', ''))
    except Exception as e:
        current_app.logger.error(
            f'Telegram could not be resolved. username: {self.data["name"]}. Exception: {e}')
        raise InventoryValidationError(
            f"""Telegram user or channel not found: {self.data['name']}. 
                Please check whether you typed the username correctly. 
                If the issue persists, please contact us and we will look into this issue.""")

    if profile == False:
        raise InventoryValidationError(
            f"""Telegram user or channel not found: {self.data['name']}. 
                Please check whether you typed the username correctly. 
                If the issue persists, please contact us and we will look into this issue.""")

    self.entry['name'] = self.data[
        'name'].lower().replace('@', '')

    if profile.get('fullname'):
        try:
            self.entry['alternate_names'].append(profile['fullname'])
        except KeyError:
            self.entry['alternate_names'] = [profile['fullname']]
    if profile.get('followers'):
        facets = {'count': int(
            profile['followers']),
            'unit': 'followers'}
        self.entry['audience_size'] = Scalar(
            str(datetime.date.today()), facets=facets)
    self.entry['verified_account'] = profile.get('verified', False)
    if profile.get('telegram_id'):
        self.entry['identifier'] = profile.get('telegram_id')
    if profile.get('joined'):
        self.entry['date_founded'] = profile.get('joined')