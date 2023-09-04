from flaskinventory import dgraph
from flaskinventory.flaskdgraph import Schema
from flaskinventory.main.model import *

import typing as t
from flaskinventory.flaskdgraph.utils import recursive_restore_sequence, validate_uid

import logging

logger = logging.getLogger(__name__)

"""
    Inventory Detail View Functions
"""

def get_entry(unique_name: str = None, uid: str = None, dgraph_type: t.Union[str, Schema] = None) -> t.Union[dict, None]:
    query_var = 'query get_entry($value: string) '
    if unique_name:
        uid = dgraph.get_uid("_unique_name", unique_name)

    uid = validate_uid(uid)
    if not uid:
        return None

    query_func = f'{{ entry(func: uid($value))'
    var = uid

    if dgraph_type:
        try:
            dgraph_type = Schema.get_type(dgraph_type)
        except TypeError:
            pass
        query_func += f'@filter(type({dgraph_type}))'
    else:
        query_func += f'@filter(has(dgraph.type))'

    query_fields = '''{ uid dgraph.type 
                        expand(_all_) { 
                            uid _unique_name name entry_review_status display_name 
                            authors @facets(orderasc: sequence) { uid _unique_name name } 
                            _authors_fallback @facets(orderasc: sequence) title 
                            channel { uid name _unique_name }
                            }
                        '''

    if dgraph_type == 'NewsSource':
        query_fields += '''published_by: ~publishes @facets(orderasc: _unique_name) { name _unique_name uid entry_review_status dgraph.type } 
                            archives: ~sources_included @facets @filter(type("Archive")) (orderasc: _unique_name) { name _unique_name uid entry_review_status } 
                            datasets: ~sources_included @facets @filter(type("Dataset")) (orderasc: _unique_name) (orderasc: _unique_name){ name _unique_name uid entry_review_status @facets(orderasc: sequence) { uid _unique_name name } _authors_fallback @facets(orderasc: sequence) }
                            papers: ~sources_included @facets @filter(type("ScientificPublication")) (orderasc: date_published) { uid name title date_published entry_review_status @facets(orderasc: sequence) { uid _unique_name name } _authors_fallback @facets(orderasc: sequence) } 
                        } }'''

    elif dgraph_type == 'Organization':
        query_fields += 'owned_by: ~owns @filter(type(Organization)) (orderasc: _unique_name) { uid name _unique_name entry_review_status } } }'

    elif dgraph_type == 'Dataset':
        query_fields += '''
                        papers: ~datasets_used @facets @filter(type("ScientificPublication")) (orderasc: name) { uid title date_published name entry_review_status authors @facets(orderasc: sequence) { uid _unique_name name } _authors_fallback @facets(orderasc: sequence) } 
                        } }
                        '''

    elif dgraph_type == 'PoliticalParty':
        query_fields += '''archives: ~sources_included @facets @filter(type("Archive")) (orderasc: _unique_name) { name _unique_name uid entry_review_status fulltext_available authors @facets(orderasc: sequence) { uid _unique_name name } _authors_fallback @facets(orderasc: sequence) temporal_coverage_start temporal_coverage_end } 
                           datasets: ~sources_included @facets @filter(type("Dataset")) (orderasc: _unique_name) (orderasc: _unique_name) { name _unique_name uid entry_review_status fulltext_available authors @facets(orderasc: sequence) { uid _unique_name name } _authors_fallback @facets(orderasc: sequence) temporal_coverage_start temporal_coverage_end }
                           papers: ~sources_included @facets @filter(type("ScientificPublication")) (orderasc: date_published) { uid name title date_published entry_review_status fulltext_available authors @facets(orderasc: sequence) { uid _unique_name name } _authors_fallback @facets(orderasc: sequence) temporal_coverage_start temporal_coverage_end } 
                        } }'''
        
    elif dgraph_type == 'Author':
        query_fields += '''tools: ~authors @filter(type("Tool")) (orderasc: _unique_name) { uid name _unique_name entry_review_status authors @facets(orderasc: sequence) { uid _unique_name name } _authors_fallback @facets(orderasc: sequence) date_published programming_languages platform } 
                           archives: ~authors @filter(type("Archive")) (orderasc: _unique_name) { name _unique_name uid entry_review_status } 
                           datasets: ~authors @filter(type("Dataset")) (orderasc: _unique_name) (orderasc: _unique_name){ name _unique_name uid entry_review_status authors @facets(orderasc: sequence) { uid _unique_name name } _authors_fallback @facets(orderasc: sequence) }
                           publications: ~authors @filter(type("ScientificPublication")) (orderasc: date_published) { uid name title date_published entry_review_status authors @facets(orderasc: sequence) { uid _unique_name name } _authors_fallback @facets(orderasc: sequence) } 
                        } }'''

    elif dgraph_type == 'Operation':
        query_fields += '''
                        tools: ~used_for @filter(type("Tool")) (orderasc: _unique_name) { uid name _unique_name entry_review_status authors @facets(orderasc: sequence) { uid _unique_name name } _authors_fallback @facets(orderasc: sequence) date_published programming_languages platform } } }
                        '''

    elif dgraph_type == 'FileFormat':
        query_fields += '''
                        tools_input: ~input_file_format @filter(type("Tool")) (orderasc: _unique_name) { uid name _unique_name entry_review_status authors @facets(orderasc: sequence) { uid _unique_name name } _authors_fallback @facets(orderasc: sequence) date_published programming_languages platform } 
                        tools_output: ~output_file_format @filter(type("Tool")) (orderasc: _unique_name) { uid name _unique_name entry_review_status authors @facets(orderasc: sequence) { uid _unique_name name } _authors_fallback @facets(orderasc: sequence) date_published programming_languages platform }
                        datasets: ~file_formats @filter(type("Dataset")) (orderasc: _unique_name) { uid name _unique_name entry_review_status authors @facets(orderasc: sequence) { uid _unique_name name } _authors_fallback @facets(orderasc: sequence) date_published }
                        } }
                        '''

    elif dgraph_type == 'MetaVariable':
        query_fields += '''
                        datasets: ~meta_variables @filter(type("Dataset")) (orderasc: _unique_name) { uid name _unique_name entry_review_status authors @facets(orderasc: sequence) { uid _unique_name name } _authors_fallback @facets(orderasc: sequence) date_published }
                        } }
                        '''
    
    elif dgraph_type == 'ConceptVariable':
        query_fields += '''
                        datasets: ~concept_variables @filter(type("Dataset")) (orderasc: _unique_name) { uid name _unique_name entry_review_status authors @facets(orderasc: sequence) { uid _unique_name name } _authors_fallback @facets(orderasc: sequence) date_published }
                        tools: ~concept_variables @filter(type("Tool")) (orderasc: _unique_name) { uid name _unique_name entry_review_status authors @facets(orderasc: sequence) { uid _unique_name name } _authors_fallback @facets(orderasc: sequence) date_published programming_languages platform }
                        } }
                        '''

    elif dgraph_type == 'UnitOfAnalysis':
        query_fields += '''
                        dataset: ~text_units @filter(type("Dataset")) (orderasc: _unique_name) { uid name _unique_name entry_review_status authors @facets(orderasc: sequence) { uid _unique_name name } _authors_fallback @facets(orderasc: sequence) date_published }
                        } }
                        '''
    elif dgraph_type == 'TextType':
        query_fields += '''
                        datasets: ~text_types @filter(type("Dataset")) (orderasc: _unique_name) { uid name _unique_name entry_review_status authors @facets(orderasc: sequence) { uid _unique_name name } _authors_fallback @facets(orderasc: sequence) date_published }
                        archives: ~text_types @filter(type("Archive")) (orderasc: _unique_name) { uid name _unique_name entry_review_status authors @facets(orderasc: sequence) { uid _unique_name name } _authors_fallback @facets(orderasc: sequence) date_published }
                        publications: ~text_types @filter(type("ScientificPublication")) (orderasc: _unique_name) { uid name _unique_name entry_review_status authors @facets(orderasc: sequence) { uid _unique_name name } _authors_fallback @facets(orderasc: sequence) date_published }
                        } }
                        '''
    else:
        query_fields += '} }'
    
    query_string = query_var + query_func + query_fields

    data = dgraph.query(query_string, variables={'$value': var})

    if len(data['entry']) == 0:
        return None

    recursive_restore_sequence(data['entry'])
    data = data['entry'][0]

    # Get authors again, in right order
    if 'authors' in data:
        authors_query = """query get_entry($value: string) { 
            q(func: uid($value)) { 
                uid dgraph.type
                authors @facets(orderasc: sequence) { uid _unique_name name  }
                } 
            }
        """
        authors = dgraph.query(authors_query, variables={'$value': var})
        try:
            data['authors'] = authors['q'][0]['authors']
        except Exception as e:
            logger.debug(f'Could not append authors: {e}')

    if dgraph_type == 'Channel':
        num_sources = dgraph.query(NewsSource.channel.count(uid, _reverse=True, entry_review_status="accepted"))
        data['num_sources'] = num_sources['channel'][0]['count']

    elif dgraph_type == 'Archive':
        num_sources = dgraph.query(Archive.sources_included.count(uid, entry_review_status="accepted"))
        data['num_sources'] = num_sources['sources_included'][0]['count(sources_included)']

    elif dgraph_type == 'Dataset':
        num_sources = dgraph.query(Dataset.sources_included.count(uid, entry_review_status="accepted"))
        data['num_sources'] = num_sources['sources_included'][0]['count(sources_included)']

    elif dgraph_type == 'Country':
        num_sources = dgraph.query(NewsSource.countries.count(uid, _reverse=True, entry_review_status="accepted"))
        data['num_sources'] = num_sources['countries'][0]['count']
        num_orgs = dgraph.query(Organization.country.count(uid, _reverse=True, entry_review_status="accepted"))
        data['num_orgs'] = num_orgs['country'][0]['count']
    
    elif dgraph_type == 'Multinational':
        num_sources = dgraph.query(NewsSource.countries.count(uid, _reverse=True, entry_review_status="accepted"))
        data['num_sources'] = num_sources['countries'][0]['count']

    elif dgraph_type == 'Subnational':
        num_sources = dgraph.query(NewsSource.subnational_scope.count(uid, _reverse=True, entry_review_status="accepted"))
        data['num_sources'] = num_sources['subnational_scope'][0]['count']

    return data

def get_comments(uid: str) -> t.List[dict]:

    uid = validate_uid(uid)
    if not uid:
        raise ValueError
    
    query_string = '''query getComment($entry_uid : string) {
        q(func: type("Comment"), orderasc: _comment_date) 
            @filter(uid_in(_comment_on, $entry_uid)) {
                uid expand(_all_) { uid display_name }
            }
        }  
    '''
    data = dgraph.query(query_string, variables={'$entry_uid': uid})

    if len(data['q']) == 0:
        return []

    return data['q']


def get_rejected(uid):
    query_string = f'''{{ q(func: uid({uid})) @filter(type(Rejected)) 
                        {{ uid name _unique_name alternate_names 
                            _date_created _added_by {{ uid display_name }} 
                            entry_review_status _reviewed_by {{ uid display_name }}
                        }}
                        }}'''

    res = dgraph.query(query_string)

    if len(res['q']) > 0:
        return res['q'][0]
    else:
        return False


def get_orphan(query):
    q_string = '''{
                source(func: eq(dgraph.type, "NewsSource")) 
                @filter(not(has(~publishes))) {
                    uid
                    name
                    }
                }'''
    pass


""" 
    Query Related Functions 
"""

# List all entries of specified type, allows to pass in filters


def list_by_type(typename, filt=None, fields=None, normalize=False):
    query_head = f'{{ q(func: type("{typename}"), orderasc: name) '
    if filt:
        query_head += dgraph.build_filt_string(filt)

    query_fields = ''
    if fields == 'all':
        query_fields = " expand(_all_) "
    elif fields:
        query_fields = " ".join(fields)
    else:
        normalize = True
        if typename == 'NewsSource':
            query_fields = ''' uid _unique_name name date_founded alternate_names
                                channel { name }
                                '''
        if typename == 'Organization':
            query_fields = ''' uid _unique_name name date_founded alternate_names
                                publishes: count(publishes)
                                owns: count(owns)
                                '''
        if typename in ['Archive', 'Dataset', 'Corpus']:
            query_fields = ''' uid _unique_name name conditions_of_access alternate_names
                                sources_included: count(sources_included)
                                ''' 
        if typename == 'ScientificPublication':
            normalize = False   
            query_fields = ''' uid title authors @facets(orderasc: sequence) { uid _unique_name name } _authors_fallback @facets(orderasc: sequence) 
                                date_published venue
                                sources_included: count(sources_included)
                                '''
        if typename == 'Subnational':
            normalize = False
            query_fields = ''' uid name _unique_name alternate_names '''
        
        if typename == 'Tool':
            normalize = False
            query_fields = ''' uid name authors @facets(orderasc: sequence) { uid _unique_name name } _authors_fallback @facets(orderasc: sequence) 
                                date_published venue
                                '''

    query_fields += ''' country { name } '''

    if normalize:
        query_head += ''

    query_string = query_head + \
        ' { ' + query_fields + ' ' + ' } }'

    data = dgraph.query(query_string)

    if len(data['q']) == 0:
        return False

    data = data['q']
    recursive_restore_sequence(data)

    return data
