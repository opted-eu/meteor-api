from flaskinventory import dgraph
from flask_login import current_user
from flaskinventory.users.constants import USER_ROLES
from flask import flash
from flaskinventory.auxiliary import icu_codes_list
from pydgraph import Txn
import json


async def generate_fieldoptions():

    query_channel = '''channel(func: type("Channel"), orderasc: name) { uid expand(_all_) }'''
    query_country = '''country(func: type("Country"), orderasc: name) @filter(eq(opted_scope, true)) { uid _unique_name name  }'''
    query_dataset = '''dataset(func: type("Dataset"), orderasc: name) { uid _unique_name name  }'''
    query_archive = '''archive(func: type("Archive"), orderasc: name) { uid _unique_name name  }'''
    query_subunit = '''subunit(func: type("Subnational"), orderasc: name) { uid _unique_name name alternate_names country{ name } }'''
    query_multinational = '''multinational(func: type("Multinational"), orderasc: name) { uid _unique_name name alternate_names country{ name } }'''

    query_string = '{ ' + query_channel + query_country + \
        query_dataset + query_archive + query_subunit + query_multinational + ' }'

    # Use async query here because a lot of data is retrieved
    query_future = dgraph.connection.txn().async_query(query_string)
    res = Txn.handle_query_future(query_future)

    # data = dgraph.query(query_string)

    res = dgraph.connection.txn(read_only=True).query(query_string)
    data = json.loads(res.json, object_hook=dgraph.datetime_hook)

    data['language'] = icu_codes_list

    return data


def check_draft(draft, form):
    query_string = f"""
        query check_draft($draft: string) {{
            q(func: uid($draft))  @filter(eq(entry_review_status, "draft")) {{ 
                uid expand(_all_) {{ 
                    name _unique_name uid 
                    }}
                }} 
            }}"""
    draft = dgraph.query(query_string, variables={'$draft': draft})
    if len(draft['q']) > 0:
        draft = draft['q'][0]
        _added_by = draft.pop('_added_by')
        for key, value in draft['q'][0].items():
            if not hasattr(form, key):
                continue
            if type(value) is list:
                if type(value[0]) is str:
                    value = ",".join(value)
                else:
                    choices = [(subval['uid'], subval['name'])
                               for subval in value]
                    value = [subval['uid'] for subval in value]
                    setattr(getattr(form, key),
                            'choices', choices)

            setattr(getattr(form, key), 'data', value)
        # check permissions
        if current_user.uid != _added_by['uid']:
            if current_user._role >= USER_ROLES.Reviewer:
                flash("You are editing another user's draft", category='info')
            else:
                draft = None
                flash('You can only edit your own drafts!', category='warning')
    else:
        draft = None
    return draft


def get_draft(uid):
    query_string = f"""
    query get_draft($draft: string) {{
        q(func: uid($draft)) @filter(eq(entry_review_status, "draft")) {{ 
            uid expand(_all_) {{ 
                uid _unique_name name dgraph.type channel {{ name }}
                }}
            publishes_org: ~publishes {{
                uid _unique_name name ownership_kind country {{ name }} 
                }}
            archives: ~sources_included @facets @filter(type("Archive")) {{ 
                uid _unique_name name 
                }} 
            datasets: ~sources_included @facets @filter(type("Dataset")) {{ 
                uid _unique_name name 
                }} 
            }} 
        }}"""
    draft = dgraph.query(query_string, variables={'$draft': uid})
    if len(draft['q']) > 0:
        draft = draft['q'][0]
        _added_by = draft.pop('_added_by')
        draft = json.dumps(draft, default=str)
        # check permissions
        if current_user.uid != _added_by['uid']:
            if current_user._role >= USER_ROLES.Reviewer:
                flash("You are editing another user's draft", category='info')
            else:
                draft = None
                flash('You can only edit your own drafts!',
                      category='warning')
    else:
        draft = None
    return draft


def get_existing(uid):
    query_string = f"""
    query get_existing($existing: string) {{
        q(func: uid($existing)) @filter(type(NewsSource)) {{ 
            uid expand(_all_) {{
                uid _unique_name name dgraph.type channel {{ name }} 
                }}
            publishes_org: ~publishes {{
                uid _unique_name name ownership_kind country {{ name }} 
                }}
            archives: ~sources_included @facets @filter(type("Archive")) {{ 
                uid _unique_name name 
                }} 
            datasets: ~sources_included @facets @filter(type("Dataset")) {{ 
                uid _unique_name name 
                }} 
            }} 
        }}"""
    existing = dgraph.query(query_string, variables={'$existing': uid})
    if len(existing['q']) > 0:
        existing = existing['q'][0]
        related_news_sources = {'uid': existing.pop('uid'), '_unique_name': existing.pop(
            '_unique_name'), 'channel': existing.pop('channel'), 'name': existing['name']}
        if 'related_news_sources' not in existing.keys():
            existing['related_news_sources'] = [related_news_sources]
        else:
            existing['related_news_sources'].append(related_news_sources)
        existing.pop('publication_cycle', None)
        existing.pop('publication_cycle_weekday', None)
        existing.pop('date_founded', None)
        existing.pop('channel_epaper', None)
        existing.pop('payment_model', None)
        existing = json.dumps(existing, default=str)
    else:
        existing = None
    return existing
