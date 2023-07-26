from flaskinventory import dgraph
from flaskinventory.flaskdgraph.utils import validate_uid
import typing as t

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

from flaskinventory.main.model import Comment
from flask_login import current_user
from flaskinventory.flaskdgraph import dql

def post_comment(uid: str, message: str) -> dict:

    uid = validate_uid(uid)
    if not uid:
        raise ValueError
    
    # assert that comment is on an Entry
    dgraph_type = dgraph.get_dgraphtype(uid, clean=[])
    if not 'Entry' in dgraph_type:
        raise ValueError
    
    if current_user._role < Comment.__permission_new__:
        raise PermissionError

    comment = Comment(_creator=current_user.id, 
                      content=message,
                      _comment_on=uid)
    
    result = dgraph.mutation(comment.as_dict())

    return dict(result.uids)