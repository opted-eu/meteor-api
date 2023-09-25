
from flask import (current_app, Blueprint, render_template, url_for,
                   flash, redirect, request, abort, jsonify)
from flask_login import current_user, login_required
from meteor import dgraph
from meteor.flaskdgraph.schema import Schema
from meteor.add.forms import NewEntry, AutoFill
from meteor.add.dgraph import check_draft, get_draft, get_existing
from meteor.main.sanitizer import Sanitizer
from meteor.users.utils import requires_access_level
from meteor.users.dgraph import UserLogin
from meteor.flaskdgraph.utils import strip_query, validate_uid
from meteor.misc.utils import IMD2dict

add = Blueprint('add', __name__)


@add.route("/add", methods=['GET', 'POST'])
@login_required
def new_entry():
    form = NewEntry()
    if form.validate_on_submit():
        query = form.name.data.replace('https://', '').replace('http://', '').replace('www.', '')
        query = strip_query(query)
        identifier = form.name.data.strip()
        query_string = f'''
                query database_check($query: string, $identifier: string)
                {{
                    field1 as a(func: regexp(name, /$query/i)) @filter(type("{form.entity.data}"))
                    field2 as b(func: allofterms(name, $query)) @filter(type("{form.entity.data}"))
                    field3 as c(func: allofterms(alternate_names, $query)) @filter(type("{form.entity.data}"))
                    field4 as d(func: match(name, $query, 3)) @filter(type("{form.entity.data}"))
                    field5 as e(func: allofterms(title, $query)) @filter(type("{form.entity.data}"))
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
        if len(result['check']) > 0:
            return render_template('add/database_check.html', query=form.name.data, result=result['check'], entity=form.entity.data)
        else:
            if form.entity.data == 'NewsSource':
                return redirect(url_for('add.new_source', entry_name=form.name.data))
            else:
                return redirect(url_for('add.new', dgraph_type=form.entity.data))

    drafts = current_user.my_entries(entry_review_status="draft")
    if drafts:
        drafts = drafts[0]['drafts']
    return render_template('add/newentry.html', form=form, drafts=drafts)


@add.route("/add/source")
@login_required
def new_source():
    draft = request.args.get('draft')
    existing = request.args.get('existing')

    draft = validate_uid(draft)
    existing = validate_uid(existing)
    if draft:
        draft = get_draft(draft)
    elif existing:
        existing = get_existing(existing)

    return render_template("add/newsource.html", draft=draft, existing=existing)


@login_required
@add.route("/add/draft/<string:entity>/<string:uid>")
@add.route("/add/draft/")
def from_draft(entity=None, uid=None):
    if entity and uid:
        if entity == 'NewsSource':
            return redirect(url_for('add.new_source', draft=uid))
        else:
            return render_template("not_implemented.html")

    query_string = f"""
    query user_drafts($user: string){{
        q(func: uid($user)) {{
                display_name
                uid
                drafts: ~_added_by @filter(type(NewsSource) and eq(entry_review_status, "draft")) 
                @facets(orderdesc: timestamp) (first: 1) {{ uid }}
            }} 
        }}"""

    result = dgraph.query(query_string, variables={'$user': current_user.uid})
    if result['q'][0].get('drafts'):
        return redirect(url_for('add.new_source', draft=result['q'][0]['drafts'][0]['uid']))
    else:
        return redirect(url_for('add.new_entry'))


@add.route("/add/<string:dgraph_type>", methods=['GET', 'POST'])
@add.route("/add/<string:dgraph_type>/draft/<string:draft>", methods=['GET', 'POST'])
@login_required
def new(dgraph_type=None, draft=None, populate_form: dict = None):
    try:
        dgraph_type = Schema.get_type(dgraph_type)
    except:
        return abort(404)

    if not dgraph_type:
        return abort(404)
    
    if Schema.is_private(dgraph_type):
        flash('You cannot add new entries of this type', category="warning")
        return abort(403)

    form = Schema.generate_new_entry_form(
        dgraph_type=dgraph_type, populate_obj=populate_form)

    if draft is None:
        draft = request.args.get('draft')
    if draft:
        draft = check_draft(draft, form)

    if form.validate_on_submit():
        # Note that we are getting the raw post data from request.form
        # Instead of using form.data
        # This allows to get arbitrary form field data generated by JavaScript
        data = form.data.copy()
        additional_fields = IMD2dict(request.form)
        for k, v in additional_fields.items():
            if k not in data.keys():
                data[k] = v
        if draft:
            try:
                sanitizer = Sanitizer.edit(data, dgraph_type=dgraph_type)
            except Exception as e:
                if current_app.debug:
                    current_app.logger.debug(f'{dgraph_type} could not be updated: {e}', exc_info=True)
                flash(f'{dgraph_type} could not be updated: {e}', 'danger')
                return redirect(url_for('add.new', dgraph_type=dgraph_type, draft=form.data))
        else:
            try:
                sanitizer = Sanitizer(data, dgraph_type=dgraph_type)
            except Exception as e:
                if current_app.debug:
                    current_app.logger.debug(f'{dgraph_type} could not be added: {e}', exc_info=True)
                flash(f'{dgraph_type} could not be added: {e}', 'danger')
                return redirect(url_for('add.new', dgraph_type=dgraph_type))

        try:
            if sanitizer.is_upsert:
                result = dgraph.upsert(
                    sanitizer.upsert_query, del_nquads=sanitizer.delete_nquads, set_nquads=sanitizer.set_nquads)
            else:
                result = dgraph.upsert(None, set_nquads=sanitizer.set_nquads)
            flash(f'{dgraph_type} has been added!', 'success')
            if sanitizer.is_upsert:
                uid = str(sanitizer.entry_uid)
            else:
                newuids = dict(result.uids)
                uid = newuids[str(sanitizer.entry_uid).replace('_:', '')]
            return redirect(url_for('view.view_uid', uid=uid))
        except Exception as e:
            if current_app.debug:
                current_app.logger.debug(f'{dgraph_type} could not be added: {e}', exc_info=True)
            flash(f'{dgraph_type} could not be added: {e}', 'danger')
            return redirect(url_for('add.new', dgraph_type=dgraph_type))

    fields = list(form.data.keys())
    fields.remove('submit')
    try:
        fields.remove('csrf_token')
    except:
        pass

    if dgraph_type in ['Tool', 'ScientificPublication', 'Dataset', 'Corpus']:
        show_sidebar = True
        sidebar_items = {'autofill': AutoFill()}
    else:
        show_sidebar = False
        sidebar_items = {}

    return render_template('add/generic.html', title=f'Add {dgraph_type}', form=form, fields=fields, show_sidebar=show_sidebar, sidebar_items=sidebar_items)
