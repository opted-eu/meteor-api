from flask import current_app
import typing
import requests
from thefuzz import fuzz

class ORCID:

    api = "https://pub.orcid.org/"
    

    def __init__(self, token:str = None) -> None:
        headers = {
                "Authorization type": "Bearer",
                "Content-type": "application/json",
                "scope": "/read-public"
                }

        if token:
            headers["Access token"] = token
        else:
            headers["Access token"] = current_app.config['ORCID_ACCESS_TOKEN']

        self.headers = headers

    def search_authors(self, name: str = None, 
                      given_name: str = None, 
                      family_name: str = None, 
                      affiliation: str = None,
                      doi: str = None) -> dict:
        """ 
            Search Authors by different parameters 
            Returns raw API results    
        """
        
        query = []
        if name:
            query.append('given-and-family-names:' + name)
        if given_name:
            query.append('given-names:' + given_name)
        if family_name:
            query.append('family-name:' + family_name)
        if affiliation:
            query.append('affiliation-org-name:' + affiliation)
        if doi:
            query.append('doi-self:' + f'"{doi}"')

        params = {'q': " AND ".join(query)}       

        r = requests.get(self.api + 'v3.0/expanded-search/', 
                         params=params, 
                         headers=self.headers)
        
        r.raise_for_status()

        return r.json()
    
    def resolve_author(self, name: str = None, 
                      given_name: str = None, 
                      family_name: str = None, 
                      affiliation: str = None,
                      doi: str = None) -> typing.Union[dict, None]:
        """ 
            Query API and find the best match given some author details.
            Returns a single author
        """
        if not name:
            _name = given_name + ' ' + family_name
        else:
            _name = name

        if doi:
            r = self.search_authors(name=name, given_name=given_name, doi=doi)
            if r['num-found'] == 1:
                return r['expanded-result'][0]
            elif r['num-found'] > 1:
                return self._find_best_match(r['expanded-result'][:10], _name)
        
        if affiliation:
            r = self.search_authors(name=name, given_name=given_name, affiliation=affiliation)
            if r['num-found'] == 1:
                return r['expanded-result'][0]
            elif r['num-found'] > 1:
                return self._find_best_match(r['expanded-result'][:10], _name, affiliation=affiliation)
        
        # if there are no hints / or the previous hints yielded no results
        # we always try matching by name
        r = self.search_authors(name=name, given_name=given_name, family_name=family_name)
        if r['num-found'] == 1:
            return r['expanded-result'][0]
        elif r['num-found'] > 1:
                return self._find_best_match(r['expanded-result'][:10], _name)

    def _find_best_match(self, 
                         candidates: typing.List[dict], 
                         author: str,
                         affiliation: str = None) -> typing.Union[dict, None]:
        
        for c in candidates:
            name = c['given-names'] + ' ' + c['family-names']
            score = fuzz.partial_token_sort_ratio(name, author)
            if affiliation:
                for institution in c['institution-name']:
                    if fuzz.partial_token_sort_ratio(institution, affiliation) > 80:
                        score += 10
            c['name'] = name
            c['score'] = score

        highest_score = max(candidates, key=lambda x: x['score'])

        # check if there are other candidates with same score
        other_candidates = [c for c in candidates if c['score'] == highest_score['score']]
        if len(other_candidates) > 1:
            return None 
        else:
            return highest_score
