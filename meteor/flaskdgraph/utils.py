import re
from typing import Any, Union

def strip_query(query: str) -> str:
    # Dgraph query strings have some weaknesses 
    # towards certain special characters
    # for term matching and regex these characters
    # can simply be removed
    return re.sub(r'"|/|\\|\(|\)|<|>|\{|\}|\[|\]|\$|&|#|\+|\^|\?|\*', '', query)

def escape_query(query: str) -> str:
    return re.sub(r'("|/|\\|\(|\)|<|>|\{|\}|\[|\]|\$|&|#|\+|\^|\?|\*)', r'\\\1', query)

def validate_uid(uid: Any) -> Union[str, bool]:
    """
        Utility function for validating if object is a UID
        Tries to coerce object to a str (uid)
        If fails, will return False
    """
    if not isinstance(uid, (str, int)):
        uid = str(uid)

    if type(uid) == str:
        uid = uid.lower().strip()
        if not uid.startswith('0x'):
            uid = '0x' + uid
        try:
            int(uid, 16)
        except ValueError:
            return False
        if int(uid, 16) <= 0:
            return False
        return uid
    elif type(uid) == int:
        if uid <= 0:
            return False
        return str(hex(uid))
    else:
        return False

def restore_sequence(d: dict, sortkey = 'sequence') -> None:
    sortable_keys = list(filter(lambda x: x.endswith('|' + sortkey), d.keys()))
    for facet in sortable_keys:
        predicate = facet.replace('|' + sortkey, '')
        if predicate not in d:
            # skip over edge attributes
            continue
        correct_sequence = list(range(len(d[predicate])))
        for k, v in d[facet].items():
            correct_sequence[int(v)] = d[predicate][int(k)]
        d[predicate] = correct_sequence

def recursive_restore_sequence(l: list, sortkey = 'sequence') -> None:
    for item in l:
        if type(item) == list:
            recursive_restore_sequence(item, sortkey=sortkey)
        if type(item) == dict:
            restore_sequence(item, sortkey=sortkey)