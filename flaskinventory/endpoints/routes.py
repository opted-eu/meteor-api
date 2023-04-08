"""
Endpoints contains all routes that do not return rendered templates,
but some form of json or data.
Routes here are to interface with JavaScript components
Also for a potential API
"""

import traceback
from flask import (current_app, Blueprint, request, jsonify, url_for, abort)
from flask_login import current_user, login_required
from flaskinventory import dgraph
from flaskinventory.flaskdgraph.utils import strip_query, validate_uid
from flaskinventory.main.model import Source
from flaskinventory.main.sanitizer import Sanitizer
from flaskinventory.add.dgraph import generate_fieldoptions


endpoint = Blueprint('endpoint', __name__)


@endpoint.route('/endpoint/quicksearch')
def quicksearch():
    query = request.args.get('q')
    # query_string = f'{{ data(func: regexp(name, /{query}/i)) @normalize {{ uid _unique_name: _unique_name name: name type: dgraph.type channel {{ channel: name }}}} }}'
    query_regex = f'/^{strip_query(query)}/i'
    query_string = f'''
            query quicksearch($name: string, $name_regex: string)
            {{
            field1 as a(func: anyofterms(name, $name))
            field2 as b(func: anyofterms(alternate_names, $name))
            field3 as c(func: anyofterms(title, $name))
            field4 as d(func: eq(doi, $name))
            field5 as e(func: eq(arxiv, $name))
            field6 as g(func: regexp(name, $name_regex))
            field7 as h(func: regexp(_unique_name, $name_regex))
            
            data(func: uid(field1, field2, field3, field4, field5, field6, field7)) 
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
    result = dgraph.query(query_string, variables={'$name': query, '$name_regex': query_regex})
    for item in result['data']:
        if 'Entry' in item['type']:
            item['type'].remove('Entry')
    result['status'] = True
    return jsonify(result)

@endpoint.route('/endpoint/orglookup')
def orglookup():
    
    # TODO: change entire query logic here

    query = strip_query(request.args.get('q'))
    query_regex = f"/{query}/i"
    query_beginning = f'/^{query}/i'
    person = request.args.get('person')
    if person:
        person_filter = f'AND eq(is_person, {person})'
    else:
        person_filter = ''
    # query_string = f'{{ data(func: regexp(name, /{query}/i)) @normalize {{ uid _unique_name: _unique_name name: name type: dgraph.type channel {{ channel: name }}}} }}'
    query_string = f'''
            query orglookup($query_regex: string, $query_beginning: string)
            {{
                field1 as var(func: regexp(name, $query_regex)) @filter(type("Organization") {person_filter})
                field2 as var(func: regexp(alternate_names, $query_regex)) @filter(type("Organization") {person_filter})
                field3 as var(func: regexp(_unique_name, $query_beginning)) @filter(type("Organization") {person_filter})
    
                data(func: uid(field1, field2, field3)) {{
                    uid
                    _unique_name
                    name
                    dgraph.type
                    alternate_names
                    country {{ name }}
                    }}
            }}
    '''
    result = dgraph.query(query_string, variables={'$query_regex': query_regex, '$query_beginning': query_beginning})
    result['status'] = True
    return jsonify(result)


@endpoint.route('/endpoint/sourcelookup')
def sourcelookup():
    query = strip_query(request.args.get('q'))
    query_regex = f"/{query}/i"
    query_beginning = f'/^{query}/i'
    query_string = f'''
        query source($query_regex: string, $query_beginning: string)
        {{
            field1 as var(func: regexp(name, $query_regex)) @filter(type("Source"))
            field2 as var(func: regexp(alternate_names, $query_regex)) @filter(type("Source"))
            field3 as var(func: regexp(_unique_name, $query_beginning)) @filter(type("Source"))
  
	        data(func: uid(field1, field2, field3)) {{
                uid
                _unique_name
                name
                channel {{ name _unique_name }}
                country {{ name _unique_name }}
                }}
            }}
    '''
    try:
        result = dgraph.query(query_string, variables={'$query_regex': query_regex, '$query_beginning': query_beginning})
        result['status'] = True
        return jsonify(result)
    except Exception as e:
        current_app.logger.warning(f'could not lookup source with query "{query}". {e}')
        return jsonify({'status': False, 'error': f'e'})

# cache this route
@endpoint.route("/endpoint/new/fieldoptions")
async def fieldoptions():
    data = await generate_fieldoptions()
    return jsonify(data)

@endpoint.route('/endpoint/new/submit', methods=['POST'])
def submit():
    current_app.logger.debug(f'Received JSON: \n{request.json}')
    try:
        if 'uid' in request.json.keys():
            sanitizer = Sanitizer.edit(request.json, dgraph_type=Source)
        else:
            sanitizer = Sanitizer(request.json, dgraph_type=Source)
        current_app.logger.debug(f'Processed Entry: \n{sanitizer.entry}\n{sanitizer.related_entries}')
        current_app.logger.debug(f'Set Nquads: {sanitizer.set_nquads}')
        current_app.logger.debug(f'Delete Nquads: {sanitizer.delete_nquads}')
    except Exception as e:
        error = {'error': f'{e}'}
        tb_str = ''.join(traceback.format_exception(None, e, e.__traceback__))
        current_app.logger.error(tb_str)
        return jsonify(error)

    
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
        return jsonify(error)

    if result:
        if sanitizer.is_upsert:
            uid = str(sanitizer.entry_uid)
        else:
            newuids = dict(result.uids)
            uid = newuids[str(sanitizer.entry_uid).replace('_:', '')]
        response = {'redirect': url_for('view.view_generic', dgraph_type='Source', uid=uid)}

        return jsonify(response)
    else:
        current_app.logger.error(f'DGraph Error - Could not perform mutation: {sanitizer.set_nquads}')
        return jsonify({'error': 'DGraph Error - Could not perform mutation'})


@endpoint.route('/endpoint/cran')
def cran():
    package = request.args.get('package').strip()
    from flaskinventory.add.external import cran

    result = cran(package)
    if result:
        return jsonify(result)
    else:
        return abort(404)

@endpoint.route('/endpoint/identifier/lookup')
def identifier_lookup():
    if request.args.get('doi'):
        identifier = request.args.get('doi').strip()
        field = 'doi'
    elif request.args.get('arxiv'):
        identifier = request.args.get('arxiv').strip()
        field = 'arxiv'
    elif request.args.get('cran'):
        identifier = request.args.get('cran').strip()
        field = 'cran'
    elif request.args.get('pypi'):
        identifier = request.args.get('pypi').strip()
        field = 'pypi'
    elif request.args.get('github'):
        identifier = request.args.get('github').strip()
        field = 'github'
    else:
        return jsonify({'status': False})

    query_string = f'''
            query quicksearch($identifier: string) {{
                data(func: eq({field}, $identifier)) 
                    @filter(eq(entry_review_status, "draft") or 
                            eq(entry_review_status, "accepted") or 
                            eq(entry_review_status, "pending")) {{
                        uid 
                        _unique_name 
                        name 
                        dgraph.type 
                        title
                        doi
                        arxiv
                        cran
                        pypi
                    }}
                }}
        '''
    result = dgraph.query(query_string, variables={'$identifier': identifier})
    if len(result['data']) > 0:
        result['status'] = True
    else:
        result['status'] = False
    return jsonify(result)


@endpoint.route('/endpoint/ownership', methods=['POST'])
def ownership():
    current_app.logger.debug(f'Received JSON: \n{request.json}')
    try:
        if 'uid' in request.json:
            uid = validate_uid(request.json.get('uid'))
            if not uid:
                return abort(404)
            query_string = """query ownership($id: string) {
                                tmp(func: uid($id)) @recurse  {
                                    u as uid owns publishes ~owns ~publishes                                     
                                }
                                q(func: uid(uid(u))) 
                                    @filter(eq(entry_review_status, "accepted") AND 
                                        eq(dgraph.type,["Organization", "Source"]))  {
			                        name uid dgraph.type
                                    channel { _unique_name }
                                    publishes @filter(eq(entry_review_status, "accepted")) { uid }
                                    owns @filter(eq(entry_review_status, "accepted")) { uid }
                                }
                            }"""
            result = dgraph.query(query_string=query_string, variables={'$id': uid})
            return jsonify(result['q'])
        else:
            return abort(404)
    except Exception as e:
        error = {'error': f'{e}'}
        tb_str = ''.join(traceback.format_exception(None, e, e.__traceback__))
        current_app.logger.error(tb_str)
        return jsonify(error)