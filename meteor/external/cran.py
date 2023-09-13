import requests
import re

import typing

GITHUB_REGEX = re.compile(r"https?://github\.com/(.*)")

def parse_authors_at_R(expression: str) -> typing.Union[dict, list]:
    """
        First we clean the raw R expression, then we evaluate it
        as if it was an Python expression. This is possible because
        the two built-in R functions `c` and `person` can be easily emulated. 
    """

    expression = expression.replace('\n', ' ')
    expression = re.sub(r',\s+,', ', None,', expression)
    return eval(expression)

def person(*args, **kwargs) -> dict:
    """
        Crude conversion of R's `person()` function

        R allows function arguments to be unnamed as long as they are
        in the correct order. We try to emulate that behaviour here,
    """
    _person = {"given": None, "family": None, "middle": None,
                "email": None, "role": None, "comment": None,
                "first": None, "last": None}
    for arg, key in zip(args, _person.keys()):
        _person[key] = arg

    for key, val in kwargs.items():
        _person[key] = val

    return {k: v for k, v in _person.items() if v is not None}

def c(*args, **kwargs) -> typing.Union[list, dict]:
    """ 
        Very crude conversion of R's `c` (=combine) function to python expression 

        Caveat: Does not work for mixed-named vectors. E.g., c(foo="bar", "baz")
    """
    if len(kwargs) == 0:
        return list(args)
    else:
        return {k: v for k, v in kwargs.items() if v is not None}


def cran(pkg) -> dict:

    api = 'https://crandb.r-pkg.org/'

    r = requests.get(api + pkg)

    r.raise_for_status()

    if not 'json' in r.headers['Content-Type']:
        raise requests.HTTPError(f'Cannot parse to JSON: {r.headers}')

    data = r.json()

    result = {'programming_languages': ['r'],
                'platform': ['windows','linux','macos'],
                'conditions_of_access': 'free',
                'open_source': 'yes'}

    if 'Package' in data.keys():
        result['name'] = data['Package']
        result['cran'] = data['Package']

    if 'Description' in data.keys():
        result['description'] = data['Description']

    if 'Title' in data.keys():
        result['alternate_names'] = data['Title']

    if 'URL' in data.keys():
        url = data['URL']
        if GITHUB_REGEX.search(url):
            result['github'] = GITHUB_REGEX.search(url)[1]

        result['url'] = url.split(',')[0].strip()
        
    if 'License' in data.keys():
        result['license'] = data['License']

    # try extracting Author information

    authors_fallback = []
    authors_tmp = []
    if "Authors@R" in data.keys():
        authors_r = parse_authors_at_R(data['Authors@R'])

        if type(authors_r) == dict:
            authors_r = [authors_r]

        for i, a in enumerate(authors_r):
            try:
                a['given_name'] = a.pop('given')
            except:
                pass
            try:
                a['family_name'] = a.pop('family')
            except:
                # if there is no family name, we skip the author, because
                # it is very unlikely that the author only has a 
                # given name, but no family name 
                continue
            try:
                _ = a.pop('role')
            except:
                pass

            if type(a['given_name']) == list:
                a['given_name'] = " ".join(a['given_name'])

            if a['given_name'].lower() in ['rstudio', 'r core team']:
                continue

            if type(a['family_name']) == list:
                a['family_name'] = " ".join(a['family_name'])

            try:
                comment = a.pop('comment')
                orcid = comment.pop('ORCID')
                a['orcid'] = orcid
            except:
                pass

            a['authors|sequence'] = i

            try:
                _middle = a.pop('middle')
                a['name'] = a['given_name'] + " " + _middle + " " + a['family_name']
            except:
                a['name'] = a['given_name'] + " " + a['family_name']
            authors_tmp.append(a)

        result['_authors_tmp'] = authors_tmp
    
    elif "Author" in data.keys():
        authors_raw = data['Author']
        authors_raw = re.sub(r"\[.*?\]", "", authors_raw)
        authors_raw = re.sub(r"\(.*?\)", "", authors_raw)
        authors_raw = authors_raw.replace("\n", " ")
        if ' and ' in authors_raw:
            authors_split = authors_raw.split("and")
        else:
            authors_split = authors_raw.split(',')
        authors_fallback = [a.strip() for a in authors_split]

    result['_authors_fallback'] = authors_fallback
    result['_authors_fallback|sequence'] = {str(i): str(i) for i in range(len(authors_fallback))}

    return result