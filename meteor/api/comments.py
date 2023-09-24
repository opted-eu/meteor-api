import typing as t
from meteor import dgraph
from meteor.flaskdgraph.utils import validate_uid
from meteor.main.model import Comment, User
from meteor.users.constants import USER_ROLES

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

    return data['q']


def post_comment(uid: str, 
                 message: str,
                 user: User) -> dict:

    uid = validate_uid(uid)
    if not uid:
        raise ValueError
    
    # assert that comment is on an Entry
    dgraph_type = dgraph.get_dgraphtype(uid, clean=[])
    if not 'Entry' in dgraph_type:
        raise ValueError
    
    if user._role < Comment.__permission_new__:
        raise PermissionError

    comment = Comment(_creator=user.uid, 
                      content=message,
                      _comment_on=uid)
    
    result = dgraph.mutation(comment.as_dict())

    return dict(result.uids)

def remove_comment(uid: str,
                   user: User) -> bool:
    
    uid = validate_uid(uid)
    if not uid:
        raise ValueError
    
    query = Comment.uid == uid
    query.fetch(['uid', 'dgraph.type', 'expand(Comment) { uid }'])
    comment = dgraph.query(query)['q'][0]

    if not 'Comment' in comment['dgraph.type']:
        raise PermissionError
    
    if user.uid == comment['_creator']['uid'] or user.role >= USER_ROLES.Admin:
        return dgraph.delete({'uid': uid})
    
    raise PermissionError
    