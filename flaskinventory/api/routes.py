__doc__ = """

API for Meteor clients.

General Notes:
- UIDs are DGraphs internal unique ids for entries. 
    They are always represented as hex values (e.g., `0x12a`). 
    The API expects UIDs formatted as strings. Therefore, just treat UIDs as strings.
- `_unique_name` is the externally used unique id for entries.
    Unique names are human-readable and assigned by the system automatically.
    They generally follow the pattern: `dgraph type` + `country` + `name` + `date added`.
    Unique names are all lowercase and also do not contain spaces, only ascii characters, and
    are separated by an underscore.
- Predicates (you could also call them "variables", "fields", or "attributes") starting with an
    underscore are system-managed (e.g., `_date_created`) and cannot be edited by users.


Currently work in progress.

Implemented:
- View
- External
- Lookup
- Query
- Quicksearch
- Schema

Semi-Implemented (because login not implemented):
- Add
- Edit
- Review

Not Implemented:
- Login routine. We will most probably implement a login procedure that leverages external identity providers. (see: https://github.com/opted-eu/meteor-dev/issues/31)
- User
- Admin
- Follow
- Notifications

"""

import typing as t
from functools import wraps
import inspect
import re
import collections

from flask import Blueprint, jsonify, current_app, request, abort, url_for, render_template
from flask.scaffold import F

from flask_login import current_user, login_required

from flaskinventory.flaskdgraph import dql
from flaskinventory.flaskdgraph import build_query_string
from flaskinventory.flaskdgraph.utils import validate_uid, restore_sequence
from flaskinventory.view.dgraph import get_entry, get_rejected
from flaskinventory.view.utils import can_view

from flaskinventory.external.dgraph import dgraph_resolve_doi
from flaskinventory.external.doi import clean_doi

from flaskinventory.main.model import *

from flaskinventory.api.sanitizer import Sanitizer
from flaskinventory.api.comments import get_comments, post_comment
from flaskinventory.api.responses import SuccessfulAPIOperation

#: Maps Flask/Werkzeug rooting types to Swagger ones
PATH_TYPES = {
    'int': 'integer',
    'float': 'number',
    'string': 'string',
    'default': 'string',
    str: 'string',
    int: 'integer',
    dict: 'object',
    bool: 'boolean',
    list: 'array',
    t.Any: 'object'
}

def safe_issubclass(
    __cls: type,
    __class_or_tuple: t.Union[type, tuple]) -> bool:
    """ 
        Regular `issubclass` raises an error when first
        argument is not a class but an instance. 
        This is a wrapper that just tries
    """
    try:
        return issubclass(__cls, __class_or_tuple)
    except TypeError:
        return False


""" Blueprint Class Declaration """

class API(Blueprint):

    REGEX_RULE_PATH_PARAM = re.compile(r"<(?:[a-zA-Z_][a-zA-Z0-9_]*\:)?([^/].*?)>")

    routes = {}

    @staticmethod
    def abort(status_code, message=None):
        response = jsonify({
            'status': status_code,
            'message': message or "An error occurred ¯\_(ツ)_/¯",
        })
        response.status_code = status_code
        return response

    @staticmethod
    def annotation_to_response(annotation, 
                                content_type='application/json'):
        
        content = collections.defaultdict(dict)

        if t.get_origin(annotation) is t.Union:
            oneOf = []
            for r in annotation.__args__:
                if safe_issubclass(r, Schema):
                    r_type = r.__name__
                else:
                    r_type = PATH_TYPES[r]
                oneOf.append({'$ref': "#/components/schemas/" + r_type})
            content[content_type]["schema"] = {
                'type': 'object',
                'oneOf': oneOf
                }
        elif t.get_origin(annotation) is list:
            r = annotation.__args__[0]
            if safe_issubclass(r, Schema):
                r_type = r.__name__
                content[content_type]["schema"] = {
                    'type': 'array',
                    'items': {
                        '$ref': "#/components/schemas/" + r_type
                        }
                    }
            else:
                r_type = PATH_TYPES[r]
        else:
            r = annotation
            if safe_issubclass(r, Schema):
                content[content_type]["schema"] = {
                    '$ref': "#/components/schemas/" + r.__name__
                }
            elif type(r) == t._TypedDictMeta:
                content[content_type]["schema"] = {
                        'type': 'object',
                        'properties': {}
                    }
                for key, val in r.__annotations__.items():
                    content[content_type][
                        "schema"][
                            'properties'][key] = {'type': PATH_TYPES[val]}
                    if val is list:
                        content[content_type][
                        "schema"][
                            'properties'][key]['items'] = {'type': 'string'}
                    
            else:
                content[content_type]["schema"] = {
                    'type': PATH_TYPES[r]
                }
       
        return content
    
    @staticmethod
    def annotation_to_request_params(annotations: list) -> dict:
    
        content = {
            'application/json': {
                'schema': {
                    'properties': {},
                    'required': []
                }
            },
            'application/x-www-form-urlencoded': {
                'schema': {
                    'properties': {},
                    'required': []
                }
            }
        }

        for a in annotations:
            if safe_issubclass(a.annotation, Schema):
                p_param_val_pair = {a.name: {
                    '$ref': "#/components/schemas/" + a.annotation.__name__
                }}
            elif type(a.annotation) == t._TypedDictMeta:
                _p_param_val_pair = {}          
                for key, val in a.annotation.__annotations__.items():
                    _p_param_val_pair[key] = {'type': PATH_TYPES[val]}
                    if val is list:
                        _p_param_val_pair[key]['items'] = {'type': 'string'}
                p_param_val_pair = {a.name: {
                                    'type': 'object',
                                    'properties': _p_param_val_pair
                                    }
                                }
                                        
            elif t.get_origin(a.annotation) is t.Union:
                p_param_val_pair = {}
                oneOf = []
                for r in a.annotation.__args__:
                    if safe_issubclass(r, Schema):
                        r_type = r.__name__
                        oneOf.append({'$ref': "#/components/schemas/" + r_type})
                    elif type(r) == t._TypedDictMeta:
                        r_type = {
                            'type': 'object',
                            'properties': {}
                            }
                            
                        
                        for key, val in r.__annotations__.items():
                            r_type['properties'][key] = {'type': PATH_TYPES[val]}
                            if val is list:
                                r_type['properties'][key]['items'] = {'type': 'string'}
                        oneOf.append(r_type)
                                
                    else:
                        r_type = PATH_TYPES[r]
                    
                content['application/json']["schema"]['type'] = 'object'
                content['application/json']["schema"]['oneOf'] = oneOf
                content['application/x-www-form-urlencoded']["schema"]['type'] = 'object'
                content['application/x-www-form-urlencoded']["schema"]['oneOf'] = oneOf
            elif t.get_origin(a.annotation) is t.Literal:
                p_param_val_pair = {a.name: {
                    'type': 'string',
                    'enum':  list(a.annotation.__args__)
                    }
                }
            elif t.get_origin(a.annotation) is list:
                r = a.annotation.__args__[0]
                if safe_issubclass(r, Schema):
                    r_type = r.__name__
                    p_param_val_pair = {
                        a.name: {
                            '$ref': '#/components/schemas/' + a.annotation.__name__
                            }
                        }
                else:
                    r_type = PATH_TYPES[r]
                    p_param_val_pair = {
                        a.name: {
                            'type': 'array',
                            'items': {
                                'type': r_type
                            }
                            
                        }
                    }
                
            else:
                post_param_type = PATH_TYPES[a.annotation]
                p_param_val_pair = {a.name: {'type': post_param_type}}
            if a.annotation is t.Any:
                p_param_val_pair[a.name]['additionalProperties'] = True
            content['application/json']['schema']['properties'].update(p_param_val_pair)
            content['application/json']['schema']['required'].append(a.name)
            content['application/x-www-form-urlencoded']['schema']['properties'].update(p_param_val_pair)
            content['application/x-www-form-urlencoded']['schema']['required'].append(a.name)

        return content

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
                if parameter_name in request.form.keys():
                    p = request.form.get(parameter_name)
                    params[parameter_name] = p
                if request.is_json:
                    if parameter_name in request.json:
                        p = request.json.get(parameter_name)
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
            for v in self.REGEX_RULE_PATH_PARAM.findall(rule):
                path_parameters.append(v)

            # print('*'* 80)
            # print(f.__name__)
            sig = inspect.signature(f)
            # print(sig.return_annotation)
            for arg, par in sig.parameters.items():
            
                # if NoneType in par.annotation -> optional
          
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
                "description": __doc__,
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
            elif t.get_origin(param_type.annotation) is t.Literal:
                p['schema'] = {
                    'type': 'string',
                    'enum':  list(param_type.annotation.__args__)
                    }
                # p['type'] = 'string',
                # p['enum'] = list(param_type.annotation.__args__)
            else:
                p['schema'] = {'type': PATH_TYPES[param_type.annotation]}

            if not param_type.default is param_type.empty:
                p['schema']['default'] = param_type.default
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
        content = api.annotation_to_response(details['responses'])
        responses['content'] = content

        for method in details['methods']:
            open_api['paths'][path][method.lower()] = {
                'tags': [path.split('/')[1]],
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
                            'schema': {
                                'type': 'object',
                                'properties': {
                                    # key-value pairs go here
                                },
                                'required': [
                                    # keys go here
                                ]
                            }
                        },
                        'application/x-www-form-urlencoded': {
                            'schema': {
                                'type': 'object',
                                'properties': {
                                    # key-value pairs go here
                                },
                                'required': [
                                    # keys go here
                                ]
                            }
                        },
                        } 
                    }
                post_params = [details['parameters'][p] for p in details['request_body_params']]
                content = api.annotation_to_request_params(post_params)
                open_api['paths'][path][method.lower()]['requestBody']['content'] = content
                # for post_param in details['request_body_params']:
                #     post_param_type = PATH_TYPES[details['parameters'][post_param].annotation]
                #     p_param_val_pair = {post_param: {'type': post_param_type}}
                #     if details['parameters'][post_param].annotation is t.Any:
                #         p_param_val_pair[post_param]['additionalProperties'] = True
                #     open_api['paths'][
                #         path][
                #             method.lower()][
                #                 'requestBody']['content'][
                #                     'application/json']['schema'][
                #                         'properties'].update(p_param_val_pair)
                #     open_api['paths'][
                #         path][
                #             method.lower()][
                #                 'requestBody']['content'][
                #                     'application/json']['schema'][
                #                         'required'].append(post_param)
                #     open_api['paths'][  
                #         path][
                #             method.lower()][
                #                 'requestBody']['content'][
                #                     'application/x-www-form-urlencoded']['schema'][
                #                         'properties'].update(p_param_val_pair)
                #     open_api['paths'][
                #         path][
                #             method.lower()][
                #                 'requestBody']['content'][
                #                     'application/x-www-form-urlencoded']['schema'][
                #                         'required'].append(post_param)
            
    return jsonify(open_api)

@api.route('/schema/type/<dgraph_type>')
def get_dgraph_type(dgraph_type: str, new: bool = False, edit: bool = False) -> dict:
    """ 
        Get all predicates of given type alongside a description.

        This route is practically a subset of the entire schema.
        
        _Intended as utility for form generation._

        With parameter `new=True` this route does not return system managed predicates.
        Using `edit=True` the route only returns editable predicates.
        (only returns the predicates for prompting the user).
    """

    #TODO: add permission check

    dgraph_type = Schema.get_type(dgraph_type)
    if not dgraph_type:
        return api.abort(404)
    if new:
        result = {k: v.openapi_component for k, v in Schema.get_predicates(dgraph_type).items() if v.new}
    elif edit:
        result = {k: v.openapi_component for k, v in Schema.get_predicates(dgraph_type).items() if v.edit}
    else:
        result = {k: v.openapi_component for k, v in Schema.get_predicates(dgraph_type).items()}
    return jsonify(result)
    

@api.route('/schema/predicate/<predicate>')
def get_predicate(predicate: str) -> t.TypedDict('Predicate', uid=str):
    """ 
        Get choices for given predicate. 

        Returns key-value-pairs of UIDs and Names for pretty printing.

        _This route is intended as a utility for form generation._
        _For example, the country selection menu._
    """
    try:
        predicate = Schema.predicates()[predicate]
    except KeyError:
        return api.abort(404)

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
    """ 
    
    Get the most recent entries. 
    
    Default 5. Max: 50 
    
    """
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

    return jsonify(result['data'])

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
    """ 
    
    detail view of a single entry by UID
    
    """
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
    """ 
        perform text search in name fields of entries. 
        
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


# TODO: Add sorting parameter
@api.route("/query")
def query(_max_results: int = 25, _page: int = 1, _terms: str = None) -> t.List[Entry]:
    """ 
        Perform query based on dgraph query parameters.

        Provides many options to query the database. Special query parameters are 
        pre-fixed with an underscore: 
        
        - `_max_results`: maximum entries per page (limit: 50)
        - `_page`: current page
        - `_terms`: free-text search (searches various text fields)

        Default Behaviour for other query parameters:

        - Most comparators check for equality by default.
            e.g., `paper_kind == "journal"`
        - different predicates are combined with AND connectors.
            e.g., `publication_kind == "newspaper" AND geographic_scope == "national"`
        - same Scalar predicates are combined with OR connectors
            e.g., `payment_model == "free" OR payment_model == "partly free"`
        - same List predicates are combined with AND connectors
            e.g., `languages == "en" AND languages == "de"`
        - Query parameters with an asterisk indicate how same List predicates should
            be combined. So queries such as `languages == "en" OR languages == "de"`
            are also possible
        
    """

    r = {k: v for k, v in request.args.to_dict(
        flat=False).items() if v[0] != ''}
    
    if len(r) > 0:
        query_string = build_query_string(r)
        if query_string:
            search_terms = _terms
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
def query_count(_terms: str = None) -> int:
    """ get total number of hits for query """

    r = {k: v for k, v in request.args.to_dict(
        flat=False).items() if v[0] != ''}
    
    if len(r) > 0:
        query_string = build_query_string(r, count=True)
        if query_string:
            search_terms = _terms
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
        Generic Lookup Endpoint. Search entries by names (i.e., strings).
        
        *For autocomplete / search ahead kind of queries use the `quicksearch` endpoint!*

        Can perform the following

        - `query`: your search query (default uses equality matching)
        - `predicate`: predicate to query;
        - special case for `predicate` is `"name"` which searches name-like fields (`name`, `_unique_name`, `alternate_names`, `title`)
        
        Filters:

        - `dgraph_types`: provide a list of types to filter

        Examples:

        - Main intention of this endpoint is to have live search for form fields. When a user adds a new entry, 
            then the form fields can lazily load the the available options. For example, searching for a political party:
            `query=spd&predicate=name&dgraph_types=PoliticalParty`
        - Search Entries based on a `name: query=autnes&predicate=name&dgraph_types=Entry`
        - You can lookup authors by their ORCID / OpenAlex ID, by providing `query=0000-0000-0000-0000&predicate=orcid`
        - Find a publication / dataset by DOI: `10.4232%2F1.12698&predicate=doi`. Watch out to URL encode / escape forward slashes `/`!
        - Find all News Sources that use a specific social media handle: `query=bild&predicate=identifier&dgraph_types=NewsSource`
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
                                   'name@*',
                                   'name_abbrev',
                                   'name_abbrev@*',
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
                'name@*',
                'name_abbrev',
                'name_abbrev@*',
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
        return api.abort(400)

    dgraph_type = Schema.get_type(dgraph_type)

    if not dgraph_type:
        return api.abort(400, message='Invalid DGraph type')

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
def add_new_entry(dgraph_type: str, data: t.Any = None) -> SuccessfulAPIOperation:
    """
        Send data for new entry.

        Use the path `/schema/type/{dgraph_type}` to retrieve a list of required predicates.

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
        response = {'status': 'success',
                    'message': 'New entry added!',
                    'redirect': url_for('api.view_uid', uid=uid),
                    'uid': uid}

        return jsonify(response)
    else:
        current_app.logger.error(f'DGraph Error - Could not perform mutation: {sanitizer.set_nquads}')
        return api.abort(500, message='DGraph Error - Could not perform mutation')

""" Edit entries """

#TODO: refactor dgraph functions
from flaskinventory.review.dgraph import check_entry
from flaskinventory.edit.utils import can_delete, can_edit, channel_filter

from flaskinventory.api.requests import EditablePredicates

@api.route('/edit/<uid>', methods=['POST'])
def edit_uid(uid: str, data: EditablePredicates) -> SuccessfulAPIOperation:
    """ 
        Edit an entry by its UID

        Use the path `/schema/type/{dgraph_type}` to retrieve a list
        of editable predicates for a given type.
        
    """
    check = check_entry(uid=uid)
    
    if not check:
        return api.abort(404)

    if not can_edit(check, current_user):
        return api.abort(403)
    
    for dgraph_type in check['dgraph.type']:
        if Schema.is_private(dgraph_type):
            return api.abort(403, message='You cannot edit entries of this type')
        if current_user._role < Schema.permissions_edit(dgraph_type):
            return api.abort(403)
    
    if 'uid' not in data:
        data['uid'] = uid

    skip_fields = []
    # manually filter out fields depending on channel
    if dgraph_type == 'NewsSource':
        skip_fields = channel_filter(check['channel']['_unique_name'])
    
    for skip_f in skip_fields:
        try:
            _ = data.pop(skip_f)
        except:
            continue


    try:
        sanitizer = Sanitizer.edit(data, dgraph_type=dgraph_type)
    except Exception as e:
        if current_app.debug:
            current_app.logger.error(f'<{uid}> ({dgraph_type}) could not be updated: {e}', exc_info=True)
        return api.abort(400, f'<{uid}> could not be updated: {e}')
    
    try:
        result = dgraph.upsert(
            sanitizer.upsert_query, del_nquads=sanitizer.delete_nquads, set_nquads=sanitizer.set_nquads)
        return jsonify({'status': 'success',
                        'message': f'<{uid}> has been edited and accepted',
                        'uid': uid})
    except Exception as e:
        current_app.logger.warning(f'<{uid}> ({dgraph_type}) could not be updated: {e}', exc_info=True)
        return api.abort(500, f'<{uid}> could not be updated: {e}')

""" Delete Drafts """

from flaskinventory.edit.dgraph import draft_delete

@api.route('/delete/draft', methods=['POST'])
def delete_draft(uid: str) -> SuccessfulAPIOperation:
    check = check_entry(uid=uid)
    if not check:
        return abort(404)
    if not can_delete(check):
        return abort(403)

    draft_delete(check['uid'])

    return jsonify({'status': 'success',
                    'message': 'Draft deleted!',
                    'uid': uid})

""" Review Entries """

from flaskinventory.api import review
from flaskinventory.review.dgraph import accept_entry, reject_entry, send_acceptance_notification

@api.route('/review')
def overview(dgraph_type: str = None, 
             country: str = None, 
             text_type: str = None,
             user: str = None) -> t.List[Entry]:

    if dgraph_type:
        dgraph_type = Schema.get_type(dgraph_type)

    overview = review.get_overview(dgraph_type,
                            country=country,
                            user=user,
                            text_type=text_type)

    return jsonify(overview)

@api.route('/review/submit', methods=['POST'])
def submit_review(uid: str, status: t.Literal['accepted', 'rejected', 'revise']) -> SuccessfulAPIOperation:
    if status == 'accepted':
        try:
            review.accept_entry(uid, current_user)
            # send_acceptance_notification(uid)
            return jsonify({'status': 'success',
                            'message': 'Entry has been accepted!',
                            'uid': uid})
        except Exception as e:
            current_app.logger.exception(f'Could not accept entry with uid {uid}: {e}')
            return api.abort(400, message=f'Reviewing entry failed! Error: {e}')
    
    elif status == 'rejected':
        try:
            review.reject_entry(uid, current_user)
            return jsonify({'status': 'success',
                            'message': 'Entry has been rejected!',
                            'uid': uid})
        except Exception as e:
            current_app.logger.error(f'Could not reject entry with uid {uid}: {e}')
            return api.abort(400, message=f'Reviewing entry failed! Error: {e}')
    
    elif status == 'revise':
        # TODO: send notification to user that entry should be revised
        return jsonify({'status': 'not implemented',
                        'message': 'Feature not ready yet!',
                        'uid': uid})
    else:
        return abort(404)

@api.route('/review/<uid>/comment', methods=['POST'])
def leave_comment(uid: str, message: str) -> SuccessfulAPIOperation:
    """
        Post a new comment for this entry.

        If successfull, then the `uid` key is the UID of the new comment.
    """

    try:
        result = post_comment(uid, message)
        uid_return = list(result.values())[0]
        return jsonify({'status': 'success',
                        'message': f'Comment posted on <{uid}>.',
                        'uid': uid_return})
    except Exception as e:
        api.abort(400, message=f"Could not post comment on <{uid}>: {e}")


""" User Related """

from flaskinventory.api.responses import LoginToken

@api.route('/user/login', methods=['POST'])
def login(email: str, password: str) -> LoginToken:
    """ login to account, get a token back """
    return api.abort(501)


@api.route('/user/logout')
def logout() -> SuccessfulAPIOperation:
    """ logout; invalidates token """
    return api.abort(501)


@api.route('/user/register', methods=['POST'])
def register(email: str, password: str) -> SuccessfulAPIOperation:
    """ create a new account; sends a verification email to the user """
    return api.abort(501)


@api.route('/user/register/verify/<token>')
def verify_email(token: str) -> SuccessfulAPIOperation:
    """ verify user's email address """
    return api.abort(501)

@api.route('/user/register/resend', methods=['POST'])
def resend_verify_email(email: str) -> SuccessfulAPIOperation:
    """ resend verification email """
    return api.abort(501)

@api.route('/user/password/reset', methods=['POST'])
def reset_password(email: str) -> SuccessfulAPIOperation:
    """ send password reset request """
    return api.abort(501)

@api.route('/user/password/reset/<token>')
def confirm_password_reset(token: str) -> SuccessfulAPIOperation:
    """ confirm password reset """
    return api.abort(501)

@api.route('/user/password/change', methods=['POST'])
def change_password(old_pw: str, new_pw: str) -> SuccessfulAPIOperation:
    """ send password reset request """
    return api.abort(501)


@api.route('/user/profile')
def profile() -> User:
    """ view current user's profile """
    return api.abort(501)

@api.route('/user/profile/update', methods=['POST'])
def update_profile(display_name: str, 
                    affiliation: str, 
                    orcid: str, 
                    notifications: bool) -> SuccessfulAPIOperation:
    """ update current user's profile """
    return api.abort(501)


@api.route('/user/profile/delete', methods=['POST'])
def delete_account(email: str) -> SuccessfulAPIOperation:
    """ delete current user's account """
    return api.abort(501)


@api.route('/user/<uid>/entries')
def show_user_entries(uid: str) -> t.List[Entry]:
    """ 
        show all entries of a given user 
        
        Results vary depending on permission; e.g., drafts are only visible to oneself and admins 
    """

    return api.abort(501)

""" Administer Users """

@api.route('/admin/users')
def show_all_users() -> t.List[User]:
    """ 
        lists all users with their roles
    """
    
    return api.abort(501)


@api.route('/admin/users/<uid>')
def change_user(uid: str, role: int) -> SuccessfulAPIOperation:
    """ 
        change user role
    """
    
    return api.abort(501)



""" Follow Entries """

@api.route('/follow')
def show_follow() -> t.List[Entry]:
    """ lists all entries that the current user is following """
    return abort(501)

@api.route('/follow/<uid>', methods=['POST'])
def follow_entry(uid: str, status: t.Literal['follow', 'unfollow']) -> SuccessfulAPIOperation:
    """ (un)follow new entries related to this entry. """
    return abort(501)


@api.route('/follow/<dgraph_type>', methods=['POST'])
def follow_type(dgraph_type: str, status: t.Literal['follow', 'unfollow']) -> SuccessfulAPIOperation:
    """ (un)follow new entries related to this dgraph.type. Status: "follow", "unfollow" """
    return abort(501)

""" Notifications """

@api.route('/notifications')
def show_notifications() -> t.List[Notification]:
    """ lists all notifications for the current user """
    return abort(501)

@api.route('/notifications/dismiss', methods=['POST'])
def dismiss_notifications(uids: t.List[str]) -> SuccessfulAPIOperation:
    """ mark notification(s) as read; dismiss them """
    return abort(501)



""" External APIs """

from flaskinventory.add.external import (instagram, twitter, get_wikidata, telegram, vkontakte,
                                         parse_meta, siterankdata, find_sitemaps, find_feeds,
                                         build_url, cran)

from flaskinventory.api.responses import PublicationLike

@api.route('/external/cran', methods=['POST'])
def fetch_cran(package: str) -> PublicationLike:
    """ 
    Make an API call to CRAN. Get meta data on a CRAN package. 

    (CRAN's cors policy requires this workaround)

    Authors are returned as a list of strings `_authors_fallback` with the literal names as they are listed on CRAN.
    In some cases, CRAN provides machine-readable authors, in this case there is also the key `authors` that includes
    their information in a structured way.
    This means that the resulting authors list has to be checked against existing authors in 
    Meteor or on OpenAlex.

    Programming languages are returned as UIDs and do not need any further processing. 
    
    """
    package = package.strip()

    result = cran(package)
    if result:
        r_uid = dgraph.get_uid('_unique_name', 'programming_language_r')
        result['programming_languages'] = [r_uid]
        return jsonify(result)
    else:
        return api.abort(404, message=f'Package <{package}> not found. Check the spelling?')

from flaskinventory.api.responses import SocialMediaProfile
      
@api.route('/external/twitter', methods=['POST'])
def fetch_twitter(handle: str) -> SocialMediaProfile:
    """ 
        Get metadata about a Twitter user from the Twitter API.

        Meteor acts here as a middle-man that takes the request and forwards it to the
        Twitter API. It parses the result and provides it in the right format.
        
    """
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

@api.route('/external/instagram', methods=['POST'])
def fetch_instagram(handle: str) -> SocialMediaProfile:
    """ 
        Get metadata about a Instagram user from the Instagram API.

        Meteor acts here as a middle-man that takes the request and forwards it to the
        Instagram API. It parses the result and provides it in the right format.
        
    """
    profile = instagram(handle.replace('@', ''))
    result = {}
    if profile:
        result['name'] = handle.lower().replace('@', '')
        result['identifier'] = handle.lower().replace('@', '')
    else:
        return api.abort(404, message=f"Instagram profile not found: {handle}")

    if profile.get('fullname'):
        try:
            result['alternate_names'].append(profile['fullname'])
        except KeyError:
            result['alternate_names'] = [profile['fullname']]
    if profile.get('followers'):
        result['audience_size'] = str(datetime.date.today())
        result['audience_size|count'] = int(profile['followers'])
        result['audience_size|unit'] = 'followers'
    result['verified_account'] = profile['verified']
    print(result)
    return jsonify(result)

@api.route("/external/vk", methods=['POST'])
def fetch_vk(handle: str) -> SocialMediaProfile:
    """ 
        Get metadata about a VK user from the VK API.

        Meteor acts here as a middle-man that takes the request and forwards it to the
        VK API. It parses the result and provides it in the right format.
        
    """
    result = {
        'identifier': handle.replace('@', '')
    }
    try:
        profile = vkontakte(handle.replace('@', ''))
    except Exception as e:
        return api.abort(404, message=f"VKontakte profile not found: {handle}. {e}")

    result['name'] = handle.lower().replace('@', '')

    if profile.get('fullname'):
        try:
            result['alternate_names'].append(profile['fullname'])
        except KeyError:
            result['alternate_names'] = [profile['fullname']]
    if profile.get('followers'):
        result['audience_size'] = str(datetime.date.today())
        result['audience_size|count'] = int(profile['followers'])
        result['audience_size|unit'] = 'followers'
        
    result['verified_account'] = profile.get('verified')
    if profile.get('description'):
        result['description'] = profile.get('description')

    return jsonify(result)

@api.route('/external/telegram', methods=['POST'])
def fetch_telegram(handle: str) -> SocialMediaProfile:
    """ 
        Get metadata about a Telegram bot or channel from the Telegram API.

        Meteor acts here as a middle-man that takes the request and forwards it to the
        Telegram API. It parses the result and provides it in the right format.
        
    """
    result = {'identifier': handle.replace('@', '')}
    try:
        profile = telegram(handle.replace('@', ''))
    except Exception as e:
        current_app.logger.error(
            f'Telegram could not be resolved. username: {handle}. Exception: {e}')
        api.abort(404, message=f"""Telegram user or channel not found: {handle}. 
                Please check whether you typed the username correctly. 
                If the issue persists, please contact us and we will look into this issue.""")

    if profile == False:
        api.abort(404, f"""Telegram user or channel not found: {handle}. 
                Please check whether you typed the username correctly. 
                If the issue persists, please contact us and we will look into this issue.""")

    result['name'] = handle.lower().replace('@', '')

    if profile.get('fullname'):
        try:
            result['alternate_names'].append(profile['fullname'])
        except KeyError:
            result['alternate_names'] = [profile['fullname']]
    if profile.get('followers'):
        result['audience_size'] = str(datetime.date.today())
        result['audience_size|count'] = int(profile['followers'])
        result['audience_size|unit'] = 'followers'
        
    result['verified_account'] = profile.get('verified', False)
    if profile.get('telegram_id'):
        result['identifier'] = profile.get('telegram_id')
    if profile.get('joined'):
        result['date_founded'] = profile.get('joined')

    return jsonify(result)

@api.route('/external/website', methods=['POST'])
def resolve_website(url: str) -> SocialMediaProfile:
    # first check if website exists
    result = {'alternate_names': []}
    try:
        parsing_result = parse_meta(url)
        names = parsing_result['names']
        urls = parsing_result['urls']
    except:
        api.abort(404, f"Could not resolve website! URL provided does not exist: {url}")

    if urls == False:
        api.abort(404, f"Could not resolve website! URL provided does not exist: {url}")

    # clean up the display name of the website
    entry_name = url.replace(
        'http://', '').replace('https://', '').lower()

    if entry_name.endswith('/'):
        entry_name = entry_name[:-1]

    result['name'] = entry_name

    # append automatically retrieved names to alternate_names
    for name in names:
        if name.strip() == '':
            continue
        if name not in result['alternate_names']:
            result['alternate_names'].append(name.strip())

    for url in urls:
        if url.strip() == '':
            continue
        if url not in result['alternate_names']:
            result['alternate_names'].append(url.strip())

    result['identifier'] = build_url(url)

    # siterank data
    try:
        daily_visitors = siterankdata(url)
    except Exception as e:
        current_app.logger.warning(
            f'Could not fetch siterankdata for {url}! Exception: {e}')
        daily_visitors = None

    if daily_visitors:
        result['audience_size'] = str(datetime.date.today())
        result['audience_size|count'] = int(daily_visitors)
        result['audience_size|unit'] = "daily visitors"
        result['audience_size|data_from'] = f"https://siterankdata.com/{str(result['name']).replace('www.', '')}"

    # RSS and XML feeds
    result['channel_feeds'] = []
    result['channel_feeds|kind'] = {}
    kinds = []
    sitemaps = find_sitemaps(url)
    for sitemap in sitemaps:
        result['channel_feeds'].append(sitemap)
        kinds.append('sitemap')

    feeds = find_feeds(url)

    for feed in feeds:
        result['channel_feeds'].append(feed)
        kinds.append('rss')
    
    for i, kind in enumerate(kinds):
        result['channel_feeds|kind'][str(i)] = kind
    
    return jsonify(result)


@api.route('/external/doi', methods=['POST'])
def resolve_doi(identifier: str, fresh: bool=False) -> PublicationLike:
    """ 
        Automatically resolve meta data for a DOI.

        If the DOI is already listed in Meteor, it will return the UID for the provided DOI.
        You can overwrite this behaviour by setting the `fresh` parameter to `true`

        Meteor tries different APIs to find the best meta-information for a
        DOI. It also tries to resolve author unique IDs (ORCID). The route returns 
        cleaned metadata, and if the author's were already found in Meteor, it will include
        their UIDs as well.   
        
    """
    if not fresh:
        doi = clean_doi(identifier)
        uid = dgraph.get_uid(field="doi", value=doi)
        if uid:
            return jsonify({'uid': uid})
    try:
        return jsonify(dgraph_resolve_doi(identifier))
    except Exception as e:
        return api.abort(404, f'Could not resolve DOI <{identifier}>. Please verify that the DOI is correct. {e}')

