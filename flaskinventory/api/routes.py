import typing as t
from functools import wraps

from flask import Blueprint, jsonify, current_app, request
from flask.views import MethodView
from flask.scaffold import F
from inspect import getdoc
from werkzeug.routing import parse_rule

from flaskinventory.flaskdgraph import build_query_string
from flaskinventory.flaskdgraph.utils import validate_uid, restore_sequence
from flaskinventory.view.dgraph import get_entry

from flaskinventory.main.model import *

import re

class API(Blueprint):

    routes = {}

    def route(self, rule: str, **options: t.Any) -> t.Callable[[F], F]:

        def decorator(f: F) -> F:
            """ Custom extension """
            self.routes[rule] = {}
            t_hints = t.get_type_hints(f)
            try:
                return_val = t_hints.pop('return')
                # if is Union
                return_val = [a for a in return_val.__args__]
            except:
                return_val = []
            self.routes[rule]['parameters'] = t_hints
            self.routes[rule]['methods'] = options.get('methods', ['GET'])
            self.routes[rule]['description'] = getdoc(f)
            self.routes[rule]['func'] = f.__name__
            self.routes[rule]['path'] = re.sub(r'<(?P<converter>[a-zA-Z_][a-zA-Z0-9_]*\:).*?>', '', rule).replace('<', '{').replace('>', '}')
            self.routes[rule]['responses'] = return_val

            """ Business as usual (see flask.Scaffolding) """
            endpoint = options.pop("endpoint", None)
            self.add_url_rule(rule, endpoint, f, **options)
            return f

        return decorator
    
    def url_parameters(self, **url_params):
        def decorator(f):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                return f(*args, **url_params, **kwargs)
            return decorated_function
        return decorator

api = API('api', __name__)


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
        return api.abort(404, "Invalid UID")

    data = get_entry(uid=uid)

    if not data:
        return api.abort(404, f'The requested entry <{uid}> could not be found!')

    # if not can_view(data, current_user):
    #     if current_user.is_authenticated:
    #         flash("You do not have the permissions to view this entry.", "warning")
    #         return abort(403)
    #     else:
    #         flash("You do not have the permissions to view this entry. Try to login?", "warning")
    #         return redirect(url_for('users.login'))
        
    return jsonify(data)

@api.route('/view/recent')
def view_recent(limit=5) -> t.List[Entry]:

    query_string = '''{
                        data(func: has(dgraph.type), orderdesc: _date_created, first: 5) 
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
    
    result = dgraph.query(query_string)
    for entry in result['data']:
        if 'Entry' in entry['dgraph.type']:
            entry['dgraph.type'].remove('Entry')
        if 'Resource' in entry['dgraph.type']:
            entry['dgraph.type'].remove('Resource')

    return jsonify(result)



    

# Schema API routes

#: Maps Flask/Werkzeug rooting types to Swagger ones
PATH_TYPES = {
    'int': 'integer',
    'float': 'number',
    'string': 'string',
    'default': 'string',
    str: 'string'
}

@api.route('/schema')
def schema_types():
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
            # "servers": [
            #     {
            #     "url": "https://petstore3.swagger.io/api/v3"
            #     }
            # ],
            }
    open_api['components'] = Schema.provide_types()

    print(API.routes)

    open_api['paths'] = {}

    for rule, details in API.routes.items():
        path = details['path']
        open_api['paths'][path] = {}
        parameters = []
        for param, param_type in details['parameters'].items():
            parameters.append(
                {'name': param,
                 'in': 'path',
                 'required': True,
                 'schema': {'type': PATH_TYPES[param_type]}
                 }
            )
    
        responses = {
            "description": "sucess", # dont know how to describe that in more detail
            "content": {
            "application/json": {
                "schema": {}
                }
            }       
        }

        if len(details['responses']) > 1:
            oneOf = []
            for r in details['responses']:
                if issubclass(r, Schema):
                    r_type = r.__name__
                else:
                    r_type = PATH_TYPES[r]
                oneOf.append({'$ref': "#/components/schemas/" + r_type})
            responses["content"]["application/json"]["schema"] = {'oneOf': oneOf}

        elif len(details['responses']) == 1:
            responses["content"]["application/json"]["schema"] = {'$ref': r.__name__}
        
        else:
            responses["content"]["application/json"]["schema"] = {}

        for method in details['methods']:
            open_api['paths'][path][method.lower()] = {
                'description': details['description'],
                # 'operationId': details['func'],
                'parameters': parameters,
                'responses': {'200': responses,
                              '404': {'description': 'Not found'}}
                }
            
    return jsonify(open_api)