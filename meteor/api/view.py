from meteor import dgraph
from meteor.flaskdgraph import Schema
from meteor.main.model import *
from meteor.errors import *

import typing as t
from meteor.flaskdgraph.utils import recursive_restore_sequence, validate_uid

import logging

logger = logging.getLogger(__name__)

"""
    Inventory Detail View Functions
"""

def get_preview(unique_name: str = None, uid: str = None) -> dict:
    """ 
        Get only most important predicates, used for checking permissions
    """
    if unique_name:
        uid = dgraph.get_uid("_unique_name", unique_name)

    uid = validate_uid(uid)
    if not uid:
        raise InventoryValidationError(f'Invalid UID <{uid}>')

    var = uid

    query_string = '''query get_entry($value: string) {
                        entry(func: uid($value)) @filter(has(dgraph.type)) { 
                            uid dgraph.type entry_review_status 
                            _added_by { uid display_name }
                       } 
                    }'''
    

    data = dgraph.query(query_string, variables={'$value': var})

    if len(data['entry']) == 0:
        raise InventoryDatabaseError('Entry not found!')
    
    return data['entry'][0]


def get_entry(unique_name: str = None, uid: str = None, dgraph_type: t.Union[str, Schema] = None) -> t.Union[dict, None]:
    if unique_name:
        uid = dgraph.get_uid("_unique_name", unique_name)

    uid = validate_uid(uid)
    if not uid:
        return None

    var = uid

    if dgraph_type:
        try:
            dgraph_type = Schema.get_type(dgraph_type)
        except TypeError:
            dgraph_type = None

    if not dgraph_type:
        dgraph_type = dgraph.get_dgraphtype(uid)

    query_string = '''query get_entry($value: string, $dtype: string) {
        entry(func: uid($value)) @filter(type($dtype)) { 
            uid dgraph.type expand(_all_) { 
                            uid _unique_name name title entry_review_status display_name 
                            authors @facets(orderasc: sequence) { uid _unique_name name } 
                            _authors_fallback @facets(orderasc: sequence) 
                            channel { uid name _unique_name }
                            }
                        }
                    }'''

    
    data = dgraph.query(query_string, variables={'$value': var, '$dtype': dgraph_type})

    if len(data['entry']) == 0:
        return None
    
    data = data['entry'][0]

    recursive_restore_sequence(data)
    # data = data['entry'][0]
    
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


def get_reverse_relationships(uid: str) -> dict:
    query_var = 'query get_entry($value: string) { '
    
    uid = validate_uid(uid)
    if not uid:
        raise ValueError

    dgraph_type = dgraph.get_dgraphtype(uid)

    reverse_relationships = Schema.get_reverse_relationships(dgraph_type)
    query_relationships = []
    for predicate, dtype in reverse_relationships:
        subquery = f"""{predicate}__{dtype.lower()}s(func: type({dtype}), orderasc: _unique_name) @filter(uid_in({predicate}, $value)) {{
                        uid name title date_published entry_review_status dgraph.type
                        channel {{ _unique_name name uid entry_review_status }}
                        authors @facets(orderasc: sequence) {{ _unique_name uid name entry_review_status }}
                        _authors_fallback @facets(orderasc: sequence)
                        }}"""
        
        query_relationships.append(subquery)

    
    query_string = query_var + "\n".join(query_relationships) + ' }'

    data = dgraph.query(query_string, variables={'$value': uid})

    for v in data.values():
        try:
            recursive_restore_sequence(v)
        except:
            continue

    return data


    # reverse_relationships = Schema.get_reverse_relationships(dgraph_type)

    # query_string = "query reverseRelationships($uid: string) { q(func: uid($uid)) {\n"

    # for p, dtype in reverse_relationships:
    #     query_string += f'''{p}__{dtype.lower()}: ~{p} @filter(type({dtype}) AND eq(entry_review_status, ["accepted", "pending"])) @facets (orderasc: _unique_name) {{ 
    #         name _unique_name uid entry_review_status dgraph.type title
    #         authors @facets(orderasc: sequence) {{ uid _unique_name name }} 
    #         _authors_fallback @facets(orderasc: sequence) 
    #     }} \n'''  

    # query_string += '} }'

    # result = dgraph.query(query_string, variables={'$uid': uid})
    # return jsonify(result)


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


"""
    Recommender System
"""

def get_similar(uid: str, predicates: t.List[str], first=10) -> t.List[dict]:
    """
        Get similar entries by a list of predicates.

        Calculates Jaccard Similarity for each predicate and then returns an similarity score.

        Can take an arbitrary number of predicates (at least 1) for computing similarity.
        Returns the top 10 nearest.
    """
    uid = validate_uid(uid)
    if not uid:
        raise ValueError('Invalid UID provided')
    
    # DQL Query has three blocks:
    # 1. get all other nodes that have the same predicates and count how many edges they have
    # 2. For the node of interest (node1) and each predicate, do:
    #       - get a count of all edges, 
    #       - find the intersection with all other nodes
    #       - calculate the count for the union (ensure is not zero)
    #       - compute the jaccard similarity
    #   then sum all similarity values
    # 3. Return the first 10 nodes (default value) that have the highest similarity
    #       (make sure: does not return node1, and entries are accepted) 
    
    # Declare GraphQL variable: only need UID
    query_head = "query JaccardSimilarity($uid: string, $first: int) {\n"

    # node2 are all other nodes       
    query_count_node2 = ""
    
    # head for node1 (node of interest) and initialize a normalization value
    query_node1 = "var(func: uid($uid)) { \n norm as math(1) \n"

    # head for 3rd block, with filters
    query_similar = f"""similar(func: uid(sum_similarity), orderdesc: val(sum_similarity), first: $first) 
            @filter(NOT uid($uid) AND eq(entry_review_status, "accepted") ) {{"""
    # query_similar += " AND ".join([f"has({p})" for p in predicates]) + ") {"
    query_similar += """
                uid
                _unique_name
                name
                title
                aggregated_similarity: val(sum_similarity)
                dgraph.type
                entry_review_status
                countries { name uid _unique_name }
                country { name uid _unique_name }
                channel { name uid _unique_name }
                authors @facets(orderasc: sequence) { name uid _unique_name }
                _authors_fallback @facets
            """
    
    # go through each specified predicate and add the Jaccard similarity calculation
    for predicate in predicates:
        query_count_node2 += f"""var(func: has({predicate})) {{
            node2_num_{predicate} as count({predicate}) 
            }}\n
            """
    
        query_node1 += f"node1_num_{predicate} as count({predicate}) \n"
        query_node1 += f"""v_{predicate} as {predicate} {{
            ~{predicate} {{
                node1_norm_{predicate} as math(node1_num_{predicate} / norm)
                intersection_{predicate} as count({predicate}, @filter(uid(v_{predicate})))
                union_{predicate} as math(1.0 * (node1_norm_{predicate} + node2_num_{predicate} - intersection_{predicate}))
                similarity_{predicate} as math( ( intersection_{predicate} * 1.0 / (union_{predicate} * 1.0) ) )
            }}
        }}\n"""

        # give some verbose output, so we also return the distances for each predicate
        query_similar += f"common_{predicate}: val(intersection_{predicate})\n"
        query_similar += f"similarity_{predicate}: val(similarity_{predicate})\n"


    # mean Jaccard Distance
    query_node1 += "sum_similarity as math( (" 
    query_node1 += " + ".join([f"similarity_{p}" for p in predicates]) + ' ) '
    # query_node1 += " + ".join([f"(distance_{p} / (distance_{p} + 0.0001) )" for p in predicates])
    query_node1 += ') \n}\n' 

    query_similar += " } }"
    
    # compose query
    query_string = query_head + query_count_node2 + query_node1 + query_similar
       
    result = dgraph.query(query_string, variables={'$uid': uid, '$first': str(first)})
    return result['similar']
