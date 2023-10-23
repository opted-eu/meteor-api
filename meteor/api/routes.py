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
- Login Routine
- Add (**NEW**)
- Edit (**NEW**)
- Review (**NEW**)
- User actions (**NEW**)
- Commenting (**NEW**)
- Admin actions (**NEW**)

Not Implemented:
- Follow
- Notifications
- Recommender system

"""

import typing as t
from functools import wraps
import inspect
import re
import collections

from flask import Blueprint, jsonify, current_app, request, abort, url_for, render_template
from flask.scaffold import F

from flask_login import current_user, login_required
import flask_jwt_extended as jwtx
# TODO: reimplement this class for jwtx!
from meteor import AnonymousUser

from meteor.flaskdgraph import dql
from meteor.flaskdgraph import build_query_string
from meteor.flaskdgraph.utils import validate_uid, recursive_restore_sequence
from meteor.view.dgraph import get_entry, get_rejected
from meteor.view.utils import can_view

from meteor.external.dgraph import dgraph_resolve_doi
from meteor.external.doi import clean_doi

from meteor.main.model import *

from meteor.api.sanitizer import Sanitizer
from meteor.api.comments import get_comments, post_comment, remove_comment
from meteor.api.responses import SuccessfulAPIOperation

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

    _jwt_required_kwargs = ['optional', 'fresh', 'refresh', 'locations', 
                            'verify_type', 'skip_revocation_check']

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
                try:
                    r_type = PATH_TYPES[r]
                except KeyError:
                    r_type = api.annotation_to_response(r)[content_type]['schema']
                content[content_type]["schema"] = {
                    'type': 'array',
                    'items': r_type
                    }
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
        And call the decorated function with the request parameters.

        E.g.: `my_func(a, b, c)`
        it will check if `a`, `b`, or `c` are in the request parameters
        (either in the url query `some_url?a=value`, in the form data, and in the json data) 
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
                        elif t.get_origin(par.annotation) == t.Literal:
                            if not p in t.get_args(par.annotation):
                                raise ValueError
                        elif t.get_origin(par.annotation) == t.Any:
                            p = p
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

    def route(self, rule: str, authentication: bool = False, **options: t.Any) -> t.Callable[[F], F]:
        """ Custom extension of Flask default routing / rule creation 
            This decorator extract function arguments and details and 
            stores it the blueprint class (the dict "routes")
            This enables serving the OpenAPI scheme
            The decorator also applies the @query_params decorator
        """

        methods = options.get('methods', ['GET'])
        jwt_kwargs = {}
        for k in self._jwt_required_kwargs:
            try:
                v = options.pop(k)
                jwt_kwargs[k] = v
            except:
                continue

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

            sig = inspect.signature(f)
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

            # Check if we need authentication
            if authentication:
                self.routes[rule]['security'] = [{'BearerAuth': []}]
                _wrapper = jwtx.jwt_required(**jwt_kwargs)
                f = _wrapper(f)

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
                "termsOfService": "https://meteor.opted.eu/about",
                "contact": {
                    "email": "info@opted.eu"
                },
                "license": {
                    "name": "GPL-3.0",
                },
                "version": current_app.config['APP_VERSION']
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
    open_api['components']['securitySchemes'] = {'BearerAuth': {
        'type': 'http',
        'scheme': 'bearer',
        'bearerFormat': 'JWT'}
        }
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

            if 'security' in details:
                open_api['paths'][path][method.lower()]['security'] = details['security']

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
        predicates = {k: v.openapi_component for k, v in Schema.get_predicates(dgraph_type).items() if v.new}
    elif edit:
        predicates = {k: v.openapi_component for k, v in Schema.get_predicates(dgraph_type).items() if v.edit}
    else:
        predicates = {k: v.openapi_component for k, v in Schema.get_predicates(dgraph_type).items()}
    
    result = {'dgraph.type': dgraph_type,
              'description': Schema.get_type_description(dgraph_type),
              'predicates': predicates}
    
    return jsonify(result)

from meteor.api.responses import DGraphTypeDescription

@api.route('/schema/types')
def list_dgraph_types() -> t.List[DGraphTypeDescription]:
    """ 
        List all public Dgraph Types alongside a description
   
        _Intended as utility for form generation._

    """

    dgraph_types = []
    for dgtype in Schema.get_types(private=False):
        dgraph_types.append({'name': dgtype,
                             'description': Schema.get_type_description(dgtype)})
    
    return jsonify(dgraph_types)
    

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

@api.route('/view/uid/<uid>', authentication=True, optional=True)
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

    current_user = jwtx.current_user or AnonymousUser()
    if not can_view(data, current_user):
        if current_user.is_authenticated:
            return api.abort(403, message="You do not have the permissions to view this entry.")
        else:
            return api.abort(401, message="You do not have the permissions to view this entry. Try to login?")
        
    return jsonify(data)



@api.route('/view/entry/<unique_name>', authentication=True, optional=True)
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
@api.route("/view/rejected/<uid>", authentication=True)
def view_rejected(uid: str) -> Rejected:
    """ detail view of a rejected entry """
    uid = validate_uid(uid)
    if not uid:
        return api.abort(404, message='Invalid ID provided!')

    data = get_rejected(uid)

    if not data:
        return api.abort(404)
    
    if not can_view(data, jwtx.current_user):
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
        try:
            query_string = build_query_string(r)
        except ValueError as e:
            return api.abort(400, message=f'{e}')  
          
        search_terms = _terms
        if search_terms is not None and search_terms.strip() != '':
            variables = {'$searchTerms': search_terms.strip()}
        else:
            variables = None
        result = dgraph.query(query_string, variables=variables)
        result = result['q']

        # clean 'Entry' from types
        if len(result) > 0:
            for item in result:
                if 'Entry' in item['dgraph.type']:
                    item['dgraph.type'].remove('Entry')
        recursive_restore_sequence(result)

        return jsonify(result)
    else:
        return api.abort(400)


@api.route("/query/count")
def query_count(_terms: str = None) -> int:
    """ get total number of hits for query """

    r = {k: v for k, v in request.args.to_dict(
        flat=False).items() if v[0] != ''}
    
    if len(r) > 0:
        try:
            query_string = build_query_string(r, count=True)
        except ValueError as e:
            return api.abort(400, message=f'{e}')  
        search_terms = _terms
        if search_terms is not None and search_terms.strip() != '':
            variables = {'$searchTerms': search_terms.strip()}
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
                                   'affiliations',
                                   'countries { name uid _unique_name }',
                                   'country { name uid _unique_name }',
                                   'channel { name uid _unique_name }',
                                   'authors @facets { name uid _unique_name }',
                                   '_authors_fallback @facets'],
                            block_name="data")

        dql_query = dql.DQLQuery('lookup', blocks=[field1, field2, field3, field4, data])

    else:            
        query_variable = dql.GraphQLVariable(query=query)
        query_variable_upper = dql.GraphQLVariable(query_upper=query.upper())
        query_variable_lower = dql.GraphQLVariable(query_lower=query.lower())
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
        dql_query = dql.DQLQuery(block_name="data", 
                                 func=dql.eq(predicate, [query_variable, query_variable_upper, query_variable_lower]), 
                                 query_filter=dgraph_types,
                                 fetch=fetch)
    try:
        result = dgraph.query(dql_query)
        return jsonify(result['data'])
    except Exception as e:
        current_app.logger.warning(f'could not lookup source with query "{query}". {e}')
        return api.abort(500, message=f'{e}')

""" Add new Entries """

@api.route('/add/check', authentication=True)
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
    
from meteor.api.requests import EditablePredicates, PublicDgraphTypes

@api.route('/add/<dgraph_type>', methods=['POST'], authentication=True)
def add_new_entry(dgraph_type: str, data: EditablePredicates, draft: bool = False) -> SuccessfulAPIOperation:
    """
        Send data for new entry. Only accepts JSON data.

        Use the path `/schema/type/{dgraph_type}` to retrieve a list of required predicates.

        If the new entry was added successfully, the JSON response includes a `redirect` 
        key which shows the link to view the new entry

        Data for new entry should be structured as follows:

        ```
        {"data":                                                    # wrap the data in `data`
            {
                "name": "New Entry",
                "alternate_names": ["A list", "of more"],
                "country": "0x123",
                "tools": ["0x234", "0x345"],
                "date_modified": "2023-09-23T18:34:42.652102",      # datetime always in isoformat
                "audience_size: "2023-09-23",                       # truncated also ok
                "audience_size|unit": "followers"                   # facets are separated with `|`
            }
        }
        ```


        The optional `draft` (default = `false`) argument can be used to add new entries that are only in draft status. This 
        means they will be visible for only the user who created them. A draft also gets a UID,
        and if the user wishes to continue to work on this draft, use the same route and send the 
        `uid` also in the `data`.

        ```
        {"data":
            {
                ...

                "uid": "0x213"          # UID of the draft
            }
        }
        ```
    """
    dgraph_type = Schema.get_type(dgraph_type)
    if dgraph_type is None:
        return api.abort(400, message="Invalid DGraph type")
    
    if Schema.is_private(dgraph_type):
        return api.abort(403, message=f"You cannot add new entries of type <{dgraph_type}>")

    if not request.is_json:
        return api.abort(400, message=f"This route only accepts JSON formatted data")

    current_app.logger.debug(f'Received JSON: \n{data}')
    try:
        if 'uid' in data.keys():
            sanitizer = Sanitizer.edit(data, jwtx.current_user, dgraph_type=dgraph_type)
        else:
            entry_review_status = None
            if draft:
                entry_review_status = 'draft'
            sanitizer = Sanitizer(data, 
                                  jwtx.current_user, 
                                  dgraph_type=dgraph_type, 
                                  entry_review_status=entry_review_status)
        current_app.logger.debug(f'Processed Entry: \n{sanitizer.entry}\n{sanitizer.related_entries}')
        current_app.logger.debug(f'Set Nquads: {sanitizer.set_nquads}')
        current_app.logger.debug(f'Delete Nquads: {sanitizer.delete_nquads}')
    except Exception as e:
        import traceback
        tb_str = ''.join(traceback.format_exception(None, e, e.__traceback__))
        current_app.logger.error(tb_str)
        return api.abort(500, message=f'{e}')

    try:
        if sanitizer.is_upsert:
            result = dgraph.upsert(sanitizer.upsert_query, del_nquads=sanitizer.delete_nquads, set_nquads=sanitizer.set_nquads)
        else:
            result = dgraph.upsert(None, del_nquads=sanitizer.delete_nquads, set_nquads=sanitizer.set_nquads)
    except Exception as e:
        tb_str = ''.join(traceback.format_exception(
            None, e, e.__traceback__))
        current_app.logger.error(tb_str)
        current_app.logger.error(f'Upsert Query: {sanitizer.upsert_query}')
        current_app.logger.error(f'Delete nquads: {sanitizer.delete_nquads}')
        current_app.logger.error(f'Set nquads: {sanitizer.set_nquads}')
        return api.abort(500, message=f'{e}')

    if result:
        if sanitizer.is_upsert:
            uid = str(sanitizer.entry_uid)
        else:
            newuids = dict(result.uids)
            uid = newuids[str(sanitizer.entry_uid).replace('_:', '')]
        response = {'status': 200,
                    'message': 'New entry added!',
                    'redirect': url_for('api.view_uid', uid=uid),
                    'uid': uid}

        return jsonify(response)
    else:
        current_app.logger.error(f'DGraph Error - Could not perform mutation: {sanitizer.set_nquads}')
        return api.abort(500, message='DGraph Error - Could not perform mutation')

""" Edit entries """

#TODO: refactor dgraph functions
from meteor.review.dgraph import check_entry
from meteor.edit.utils import can_delete, can_edit, channel_filter


@api.route('/edit/<uid>', methods=['POST'], authentication=True)
def edit_uid(uid: str, data: EditablePredicates) -> SuccessfulAPIOperation:
    """ 
        Edit an entry by its UID

        Use the path `/schema/type/{dgraph_type}` to retrieve a list
        of editable predicates for a given type.
        
    """
    check = check_entry(uid=uid)
    
    if not check:
        return api.abort(404, message=f"No entry found with UID <{uid}>")

    if not can_edit(check, jwtx.current_user):
        return api.abort(403, message=f"You do not have the right permissions to edit <{uid}>")
    
    for dgraph_type in check['dgraph.type']:
        if Schema.is_private(dgraph_type):
            return api.abort(403, message='You cannot edit entries of this type')
        if jwtx.current_user._role < Schema.permissions_edit(dgraph_type):
            return api.abort(403, message=f"You do not have the permission to edit types <{dgraph_type}>")
    
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
        sanitizer = Sanitizer.edit(data, 
                                   jwtx.current_user,
                                   dgraph_type=dgraph_type)
    except Exception as e:
        if current_app.debug:
            current_app.logger.error(f'<{uid}> ({dgraph_type}) could not be updated: {e}', exc_info=True)
        return api.abort(400, f'<{uid}> could not be updated: {e}')
    
    try:
        result = dgraph.upsert(
            sanitizer.upsert_query, del_nquads=sanitizer.delete_nquads, set_nquads=sanitizer.set_nquads)
        return jsonify({'status': 'success',
                        'message': f'<{uid}> has been edited',
                        'uid': uid})
    except Exception as e:
        current_app.logger.warning(f'<{uid}> ({dgraph_type}) could not be updated: {e}', exc_info=True)
        return api.abort(500, f'<{uid}> could not be updated: {e}')

""" Delete Drafts """

from meteor.edit.dgraph import draft_delete

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

from meteor.api import review
from meteor.review.dgraph import accept_entry, reject_entry, send_acceptance_notification

@api.route('/review', authentication=True)
def overview(dgraph_type: str = None, 
             country: str = None, 
             text_type: str = None,
             user: str = None) -> t.List[Entry]:
    """ Get an overview of all entries that need to be reviewed """

    if jwtx.current_user.role < USER_ROLES.Reviewer:
        return api.abort(403, message="You need to be a reviewer to view this route.")

    if dgraph_type:
        dgraph_type = Schema.get_type(dgraph_type)

    overview = review.get_overview(dgraph_type,
                                   country=country,
                                   user=user,
                                   text_type=text_type)

    return jsonify(overview)

@api.route('/review/submit', methods=['POST'], authentication=True)
def submit_review(uid: str, 
                  status: t.Literal['accepted', 'rejected', 'revise']) -> SuccessfulAPIOperation:
    """ Submit a review decision """
    
    if jwtx.current_user.role < USER_ROLES.Reviewer:
        return api.abort(403, message='You need to be a reviewer to access this route.')

    if status == 'accepted':
        try:
            review.accept_entry(uid, jwtx.current_user)
            # send_acceptance_notification(uid)
            return jsonify({'status': 200,
                            'message': 'Entry has been accepted!',
                            'uid': uid})
        except Exception as e:
            current_app.logger.exception(f'Could not accept entry with uid {uid}: {e}')
            return api.abort(400, message=f'Reviewing entry failed! Error: {e}')
    
    elif status == 'rejected':
        try:
            review.reject_entry(uid, jwtx.current_user)
            return jsonify({'status': 200,
                            'message': 'Entry has been rejected!',
                            'uid': uid})
        except Exception as e:
            current_app.logger.error(f'Could not reject entry with uid {uid}: {e}')
            return api.abort(400, message=f'Reviewing entry failed! Error: {e}')
    
    elif status == 'revise':
        # TODO: send notification to user that entry should be revised
        return jsonify({'status': 501,
                        'message': 'Feature not ready yet!',
                        'uid': uid})
    else:
        return abort(404)
    

@api.route('/comment/view/<uid>', authentication=True)
def view_comments(uid: str) -> t.List[Comment]:
    """ 
        list all comments for this entry 
    
        Comments are sorted by date (oldest first)
    """
    
    try:
        data = get_comments(uid)
    except ValueError:
        return api.abort(404, message=f'could not get comments for UID <{uid}>')

    return jsonify(data)


@api.route('/comment/post/<uid>', methods=['POST'], authentication=True)
def leave_comment(uid: str, message: str) -> SuccessfulAPIOperation:
    """
        Post a new comment for this entry `uid`.

        If successfull, then the `uid` key is the UID of the new comment.
    """

    try:
        result = post_comment(uid, message, jwtx.current_user)
        uid_return = list(result.values())[0]
        return jsonify({'status': 'success',
                        'message': f'Comment posted on <{uid}>.',
                        'uid': uid_return})
    except PermissionError:
        return api.abort(403, message=f"You do not have the permission to post a comment on <{uid}>")
    except Exception as e:
        return api.abort(400, message=f"Could not post comment on <{uid}>: {e}")

@api.route('/comment/delete/<uid>', authentication=True)
def delete_comment(uid: str) -> SuccessfulAPIOperation:
    """
        Delete a comment by uid

        Users can only delete their own comments. (Admins can delete any comment)
    
    """

    try:
        result = remove_comment(uid, jwtx.current_user)
        if result == True:
            return jsonify({'status': 'success',
                            'message': f'Comment deleted!',
                            'uid': uid})
        else:
            return api.abort(500, message=f'Could not delete comment with uid <{uid}>')
    except PermissionError:
        return api.abort(403, message=f"You do not have the permission to post delete this comment")
    except Exception as e:
        return api.abort(400, message=f'Could not delete comment with uid <{uid}>')


""" User Related """

from meteor.api.responses import LoginToken

@api.route('/user/login', methods=['POST'])
def login(email: str, password: str) -> LoginToken:
    """ 
        login to account, get a session cookie back 

        This route provides a JWT as a session cookie. It is
        recommended method for the login routine, because
        it allows Meteor to refresh tokens automatically.
    """
    
    user = User.login(email, password)
    if not user:
        return api.abort(401, message="Wrong credentials. Make sure you have an account.")
    
    response = jsonify({"message": "login successful"})
    access_token = jwtx.create_access_token(identity=user)
    jwtx.set_access_cookies(response, access_token)
    return response

@api.route('/user/login/token', methods=['POST'])
def login_token(email: str, password: str) -> LoginToken:
    """ login to account, get a JWT token back """
    
    user = User.login(email, password)
    if not user:
        return api.abort(401, message="Wrong credentials. Make sure you have an account.")
    
    access_token = jwtx.create_access_token(identity=user)
    refresh_token = jwtx.create_refresh_token(identity=user)
    return jsonify(access_token=access_token,
                   refresh_token=refresh_token, 
                   status=200)

@api.route('/user/is_logged_in', authentication=True, optional=True)
def is_logged_in() -> SuccessfulAPIOperation:
    if jwtx.get_jwt_identity():
        return jsonify({'status': 200, 'message': 'Logged in',
                        'is_logged_in': True})
    else:
        return jsonify({'status': 200, 'message': 'Not logged in',
                        'is_logged_in': False})
    

@api.route('/user/login/refresh', methods=['POST'], authentication=True, refresh=True)
def refresh_token() -> LoginToken:
    """ login to account, get a JWT token back """
    
    identity = jwtx.get_jwt_identity()
    access_token = jwtx.create_access_token(identity=identity)
    return jsonify(access_token=access_token, status=200)

@api.after_app_request
def refresh_expiring_jwts(response):
    """ Automatically handle refreshing of JWT (stored as session cookies) """
    try:
        exp_timestamp = jwtx.get_jwt()["exp"]
        now = datetime.datetime.now(datetime.timezone.utc)
        target_timestamp = datetime.datetime.timestamp(now + datetime.timedelta(minutes=30))
        if target_timestamp > exp_timestamp:
            access_token = jwtx.create_access_token(identity=jwtx.get_jwt_identity())
            jwtx.set_access_cookies(response, access_token)
            current_app.logger.debug(f'Refreshed Token for user <{jwtx.get_jwt_identity()}>')
        return response
    except (RuntimeError, KeyError):
        # Case where there is not a valid JWT. Just return the original response
        return response


@api.route('/user/logout', authentication=True, verify_type=False)
def logout() -> SuccessfulAPIOperation:
    """ 
        logout; invalidates session cookie and revokes current JWT 
    
        Ensure to call the API route twice to also invalidate the refresh token!

        Implementation Details see: https://flask-jwt-extended.readthedocs.io/en/stable/blocklist_and_token_revoking.html
    """

    response = jsonify({"message": "logout successful"})
    token = jwtx.get_jwt()
    dgraph.mutation({'uid': '_:jwt', 
                     'dgraph.type': '_JWT', 
                     '_jti': token["jti"],
                     '_token_type': token['type'], 
                     '_revoked_timestamp': datetime.datetime.now().isoformat()})
    jwtx.unset_jwt_cookies(response)
    return response

from meteor.api.users import validate_email, email_is_taken
from meteor.users.emails import send_accept_email, send_invite_email, send_reset_email, send_verification_email

@api.route('/user/register', methods=['POST'], authentication=True, optional=True)
def register(email: str, password: str, confirm_password: str) -> SuccessfulAPIOperation:
    """ create a new account; sends a verification email to the user """

    if jwtx.current_user:
        return api.abort(400, message="You are already registered")

    try:
        email_is_taken(email)
    except Exception as e:
        return api.abort(422, message=f'{e}')
    
    if len(password) < 6:
        return api.abort(422, message=f'Password should be a minimum of 6 characters')

    if password != confirm_password:
        return api.abort(422, message=f'Passwords do not match')

    new_user = {'email': email,
                '_pw': password}
    
    new_uid = User.create_user(new_user)
    user = User(uid=new_uid)
    send_verification_email(user)

    return jsonify({'status': 200,
                    'message': f'Accounted created for {email} ({new_uid})! Please check your inbox and verify your email address!',
                    'uid': new_uid})


@api.route('/user/register/verify/<token>', authentication=True, optional=True)
def verify_email(token: str) -> SuccessfulAPIOperation:
    """ verify user's email address """
    if jwtx.current_user:
        return api.abort(400, message="You are already logged in.")

    user = User.verify_email_token(token)
    if user is None:
        return api.abort(400, message='That is an invalid or expired token! Please contact us if you experiencing issues.')
    dgraph.update_entry({'_account_status': 'active'}, uid=user.id)
    return jsonify({'status': 200, 'message': 'Email verified! You can now try to log in'})


@api.route('/user/register/resend', methods=['POST'], authentication=True, optional=True)
def resend_verify_email(email: str) -> SuccessfulAPIOperation:
    """ resend verification email """
    if jwtx.current_user:
        return api.abort(400, message="You are already logged in.")
    
    try:
        validate_email(email)
    except Exception as e:
        return api.abort(422, message=f'{e}')

    try:
        user = User(email=email)
    except ValueError:
        return api.abort(404, message='Could not find user with this email address')
    if user._account_status == 'active':
        return jsonify({'status': 400, 
                        "message": f'Your email is already verified. Please try to login. Have you forgotten your password?'})
    
    send_verification_email(user)
    return jsonify({'status': 200, 'message': f'Verification email send to {email}! Please check your inbox and verify your email address!'})


@api.route('/user/password/reset_request', methods=['POST'], authentication=True, optional=True)
def reset_password_request(email: str) -> SuccessfulAPIOperation:
    """ send password reset request """

    if jwtx.current_user:
        return api.abort(400, message="You are already logged in.")
    
    try:
        validate_email(email)
    except Exception as e:
        return api.abort(422, message=f'{e}')

    try:
        user = User(email=email)
    except ValueError:
        return api.abort(404, message='Could not find user with this email address')
    token = user.get_reset_token()
    send_reset_email(token, user.email)

    return jsonify(status=200, message='An email has been sent with instructions to reset your password')

@api.route('/user/password/reset/<token>', methods=['POST'], authentication=True, optional=True)
def confirm_password_reset(token: str, password: str, confirm_password: str) -> SuccessfulAPIOperation:
    """ confirm password reset """

    if jwtx.current_user:
        return api.abort(400, message="You are already logged in.")
    
    user = User.verify_reset_token(token)
    if not user:
        return api.abort(404, message='That is an invalid or expired token')

    if len(password) < 6:
        return api.abort(422, message=f'Password should be a minimum of 6 characters')

    if password != confirm_password:
        return api.abort(422, message=f'Passwords do not match')

    new_password = {'_pw': password, '_pw_reset': False}
    change_pw = dgraph.update_entry(new_password, uid=user.id)
    if not change_pw:
        return api.abort(403)
    dgraph.update_entry({'_pw_reset': user._pw_reset, '_pw_reset|used': True}, uid=user.id)

    return jsonify(status=200, message=f'Password updated for {user.id}!')

from meteor.api.errors import ValidationError

@api.route('/user/password/change', methods=['POST'], authentication=True)
def change_password(old_pw: str, new_pw: str, confirm_new: str) -> SuccessfulAPIOperation:
    """ send password reset request """

    if not User.user_verify(jwtx.current_user.uid, old_pw):
        raise ValidationError('Old password is incorrect!')
    
    if len(new_pw) < 6:
        return api.abort(422, message=f'Password should be a minimum of 6 characters')

    if new_pw != confirm_new:
        return api.abort(422, message=f'Passwords do not match')

    jwtx.current_user.change_password(new_pw)

    return jsonify(status=200, message=f'Your password has been changed')


from meteor.api.requests import UserProfile

@api.route('/user/profile', authentication=True)
def profile() -> User:
    """ view current user's profile """
    return jsonify(jwtx.current_user.json)

@api.route('/user/profile/update', methods=['POST'], authentication=True)
def update_profile(data: UserProfile) -> SuccessfulAPIOperation:
    """ 
        update current user's profile 
    
        Profile details can be deleted by sending `null` values. E.g., 
        delete a user's affiliation:

        ```
        {"data": 
            {"affiliation": null}
        }
        ```
    """
    try:
        jwtx.current_user.update_profile(data)
        return jsonify({'status': 200,
                        'message': 'Profile updated'})
    except Exception as e:
        return api.abort(500, message=f'{e}')


@api.route('/user/profile/delete', methods=['POST'], authentication=True)
def delete_account() -> SuccessfulAPIOperation:
    """ 
        delete current user's account 

    """
    if jwtx.current_user._role == USER_ROLES.Admin:
        return api.abort(400, message='Cannot delete admin accounts!')

    mutation = {'_account_status': 'deleted', 
                '_account_status|timestamp': datetime.datetime.now().isoformat(),
                'display_name': 'Deleted User',
                'email': secrets.token_urlsafe(8),
                '_pw': secrets.token_urlsafe(8),
                'orcid': '',
                '_role': 1,
                'affiliation': '',
                'preference_emails': False}
    
    dgraph.update_entry(mutation, uid=jwtx.current_user.id)
    dgraph.delete({'uid': jwtx.current_user.id,
                   'follows_entities': None,
                   'follows_types': None})

    response = jsonify({"message": "Account deleted"})
    token = jwtx.get_jwt()
    dgraph.mutation({'uid': '_:jwt', 
                     'dgraph.type': '_JWT', 
                     '_jti': token["jti"],
                     '_token_type': token['type'], 
                     '_revoked_timestamp': datetime.datetime.now().isoformat()})
    jwtx.unset_jwt_cookies(response)

    return response


@api.route('/user/<uid>/entries', authentication=True, optional=True)
def show_user_entries(uid: str, 
                      dgraph_type: PublicDgraphTypes = None, 
                      entry_review_status: t.Literal['accepted',
                                                     'revise',
                                                     'pending',
                                                     'draft',
                                                     'rejected'] = None,
                      page: int = 0) -> t.List[Entry]:
    """ 
        show all entries of a given user 
        
        Results vary depending on permission; e.g., drafts are only visible to oneself and admins.

        Shows a maximum of 100 entries per page, use the `page` parameter to scroll. 
    """
    try:
        user = User(uid=uid)
    except:
        return api.abort(404, message='User not found')
    
    current_user = jwtx.current_user or AnonymousUser()

    if current_user.uid == user.uid:
        entries = user.my_entries(dgraph_type=dgraph_type, 
                                  entry_review_status=entry_review_status,
                                  page=page)
        return jsonify(entries)

    # Anonymous Users and contributors can only see accepted entries
    if current_user._role <= USER_ROLES.Contributor:
        entry_review_status = 'accepted'
    else:
        if entry_review_status == 'draft':
            return api.abort(403, message='You cannot view draft entries of other users')
    
    entries = user.my_entries(dgraph_type=dgraph_type, 
                              entry_review_status=entry_review_status)
    return jsonify(entries)

""" Administer Users """

@api.route('/admin/users', authentication=True)
def show_all_users() -> t.List[User]:
    """ 
        lists all users with their roles
    """
    if jwtx.current_user.role < USER_ROLES.Admin:
        return api.abort(403)
    user_list = User.list_users()
    return jsonify(user_list)


@api.route('/admin/users/<uid>', authentication=True)
def change_user(uid: str, role: int) -> SuccessfulAPIOperation:
    """ 
        change user role
    """
    if jwtx.current_user.role < USER_ROLES.Admin:
        return api.abort(403)
    
    res = dgraph.query(User.uid == uid)
    try:
        editable_user = res['q'][0]
    except:
        return api.abort(404, message='User not found')
    
    if role not in USER_ROLES.dict_reverse:
        return api.abort(400, message=f"Unknown user level <{role}>")

    try:
        result = dgraph.update_entry({'role': role}, uid=uid)
    except Exception as e:
        return api.abort(500, message=f'Database error {e}')

    if not result:
        return api.abort(500, message="Could not update user")
    
    return jsonify({'status': 200,
                    'uid': uid,
                    'message': f'User role updated to {USER_ROLES.dict_reverse[role]}'})



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

from meteor.api.notifications import get_all_notifications, get_unread_notifications, mark_notifications_as_read
from meteor.main.model import Notification


@api.route('/notifications/all', authentication=True)
def show_all_notifications() -> t.List[Notification]:
    """ lists all notifications for the current user """

    return get_all_notifications(jwtx.current_user)

@api.route('/notifications/unread', authentication=True)
def show_unread_notifications() -> t.List[Notification]:
    """ lists unread notifications for the current user """

    return get_unread_notifications(jwtx.current_user)


@api.route('/notifications/dismiss', methods=['POST'], authentication=True)
def dismiss_notifications(uids: t.List[str]) -> SuccessfulAPIOperation:
    """ mark notification(s) as read; dismiss them 
    
        If notification has been dismissed before, then the route silently
        ignores it.

        Raises error if a supplied UID is invalid.

    """

    try:
        mark_notifications_as_read(uids, jwtx.current_user)
    except Exception as e:
        return api.abort(500, message=f'Could not mark notification as read: {e}')
    
    return jsonify({'status': 200,
                    'message': 'Done'})

@api.route('/debug/notification/dispatch')
def debug_dispatch_notification(uid: str) -> SuccessfulAPIOperation:
    """ Only for testing, send the user a notification"""

    if not current_app.debug:
        return api.abort(404)
    
    notify = Notification(_notify=uid)
    res = dgraph.mutation(notify.as_dict())
    print(res)
    return jsonify(res.uids[notify.as_dict()['uid']])


""" External APIs """

from meteor.add.external import (instagram, twitter, get_wikidata, telegram, vkontakte,
                                         parse_meta, siterankdata, find_sitemaps, find_feeds,
                                         build_url, cran)

from meteor.api.responses import PublicationLike

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

from meteor.api.responses import SocialMediaProfile
      
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

