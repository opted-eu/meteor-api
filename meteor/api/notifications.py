import typing as t
from meteor import dgraph
from meteor.flaskdgraph.utils import validate_uid
from meteor.main.model import Notification, User

def get_unread_notifications(user: User) -> t.List[dict]:
    
    query_string = '''query getNotifications($user : string) {
        q(func: type("Notification"), orderasc: _notification_date) 
            @filter(uid_in(_notify, $user) AND (eq(_read, "false"))) {
                uid _notification_date _read _title _content _linked { uid dgraph.type _unique_name name }
            }
        }  
    '''
    data = dgraph.query(query_string, variables={'$user': user.uid})

    return data['q']


def get_all_notifications(user: User) -> t.List[dict]:
    
    query_string = '''query getNotifications($user : string) {
        q(func: type("Notification"), orderasc: _notification_date) 
            @filter(uid_in(_notify, $user)) {
                uid _notification_date _read _title _content _linked { uid dgraph.type _unique_name name }
            }
        }  
    '''
    data = dgraph.query(query_string, variables={'$user': user.uid})

    return data['q']


def mark_notifications_as_read(uids: t.List[str], 
                               user: User) -> dict:

    for uid in uids:
        uid = validate_uid(uid)
        if not uid:
            raise ValueError
    uids = ', '.join(uids)
    query_string = f"{{ v as var(func: uid({uids})) @filter(type(Notification) AND uid_in(_notify, {user.uid})) }} "
    notifications = dgraph.upsert(query_string, set_obj={'uid': 'uid(v)',
                                                         '_read': True})

    if not notifications:
        raise ValueError
    return notifications    