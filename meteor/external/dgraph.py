from meteor.external.doi import resolve_doi, resolve_authors
from meteor import dgraph
from meteor.flaskdgraph import dql

def dgraph_resolve_doi(doi: str) -> dict:
    publication = resolve_doi(doi)
    authors_tmp = publication.pop('_authors_tmp')
    authors = resolve_authors(authors_tmp)

    query = dql.DQLQuery(func=dql.type_('Author'), query_filter=[
        dql.eq(openalex=dql.GraphQLVariable(openalex='openalex')),
        dql.eq(orcid=dql.GraphQLVariable(orcid='orcid'))], 
        filter_connector='OR',
        fetch=['uid', 'orcid', 'openalex']
        )

    for author in authors:
        query.set_graphql_variables(orcid=author.get('orcid', 'None'))
        if 'openalex' in author:
            assert type(author['openalex']) == list, doi
            openalex = ", ".join(author['openalex'])
            openalex = f'"[{openalex}]"'
            query.set_graphql_variables(openalex=openalex)
        else:
            query.set_graphql_variables(openalex='None')
        res = dgraph.query(query)
        if len(res['q']) > 0:
            author['uid'] = res['q'][0]['uid']
    
    publication['authors'] = authors
    return publication
    



