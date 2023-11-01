import typing as t
from meteor import dgraph
from meteor.flaskdgraph.utils import validate_uid
from meteor.main.model import Notification, User

from logging import getLogger

logger = getLogger()

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

def dispatch_notification(user: User, 
                          title: str,
                          content: str,
                          linked: str) -> str:
    """ Send a notification to a user """

    notify = Notification(_notify=user.uid,
                          _title=title,
                          _content=content,
                          _linked=linked)
    res = dgraph.mutation(notify.as_dict())
    return res.uids[notify.as_dict()['uid'].replace('_:', '')]

def notify_new_type(dgraph_type: str, new_uid: str) -> None:
    # get all users who follow this type
    query_string = """query UsersFollow($type: string) {
        q(func: eq(follows_types, $type) {
            uid
        }
    }"""

    res = dgraph.query(query_string, variables={'$type': dgraph_type})
    users = [u['uid'] for u in res['q']]
    notifications = [Notification(_notify=user, 
                                  _title=f"New {dgraph_type}",
                                  _content=f"A new entry for the type {dgraph_type} was added",
                                  _linked=new_uid).as_dict() for user in users]
    res = dgraph.mutation(notifications)
    logger.debug(f'Dispatched notifications: {res.uids}')
    logger.debug(res)

from meteor.users.emails import send_accept_email

def send_review_notification(uid: str, status: t.Literal['accepted', 'revise', 'rejected']):
    # assummes uid is safe and exists
    query_string = """query get_entry($query: string) {
                        q(func: uid($query)) { 
                            uid name 
                            dgraph.type
                            _date_created
                            channel { name }
                            _added_by { uid display_name email preference_emails } 
                        } 
                    }"""
    
    entry = dgraph.query(query_string=query_string, variables={'$query': uid})['q'][0]
    user = entry['_added_by']['uid']
    
    if status == 'accepted':
        title = "New Entry was accepted"
        message = f"Your entry <{entry['name']}> ({entry['dgraph.type']}) was reviewed and accepted!"
    elif status == 'revise':
        title = "Your entry needs revision"
        message = f"Your entry <{entry['name']}> ({entry['dgraph.type']}) was reviewed and needs some improvements!"
    else:
        title = "New Entry was rejected"
        message = f"Your entry <{entry['name']}> ({entry['dgraph.type']}) was reviewed and rejected."

    notify = Notification(_notify=user,
                          _title=title,
                          _content=message,
                          _linked=uid)
    res = dgraph.mutation(notify.as_dict())