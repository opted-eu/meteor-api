from typing import Union, Any
from flaskinventory import login_manager
from flask import current_app
from flask_login import UserMixin
from flaskinventory import dgraph
import jwt
from flaskinventory.users.constants import USER_ROLES
import datetime
import secrets
from flaskinventory.flaskdgraph.dgraph_types import _PrimitivePredicate


def generate_random_username() -> str:
    return secrets.token_urlsafe(6)


class UserLogin(UserMixin):

    id = None

    # Need more consistent ORM syntax
    # Currently load users like:
    # user = User(email="email")
    # but would be better to query like:
    # user = dgraph.query(User.email == "email")
    def __init__(self, **kwargs) -> None:
        if 'uid' or 'email' in kwargs.keys():
            self.get_user(**kwargs)
        else:
            raise ValueError

    def __repr__(self):
        return f'<DGraph Helper Class UserLogin.uid {self.id}>'

    """
        Helper Methods for __init__
    """

    def get_user(self, **kwargs):
        user_data = self.get_user_data(**kwargs)
        if user_data:
            for k, v in user_data.items():
                if k == 'uid':
                    self.id = v
                if '|' in k:
                    k = k.replace('|', '_')
                setattr(self, k, v)
            # Overwrite DGraph Predicates
            # Maye find a more elegant solution later
            for attr in dir(self):
                if isinstance(getattr(self, attr), _PrimitivePredicate):
                    setattr(self, attr, None)
            
            # Declare User Role as additional private field
            # `User.role` represents the DGraph Predicate
            # `User._role` represents the role for internal handling
            try:
                self._role = self.role
            except:
                raise AttributeError(
                    'User does not have a role! Please contact your administrator')
        else:
            return None

    def get_user_data(self, email=None, uid=None) -> Union[dict, None]:

        if email:
            data = dgraph.query(self.email == email)
        else:
            data = dgraph.query(self.uid == uid)

        if len(data['q']) == 0:
            return None
        data = data['q'][0]
        return data

    """
        Class Methods: 
            Login users
            verify tokens and return instance of User
    """

    @classmethod
    def login(cls, email: str, password: str):
        if not current_app.debug:
            query_string = f"""query login_attempt($email: string)
                            {{login_attempt(func: eq(email, $email)) {{ _account_status }} }}"""
            userstatus = dgraph.query(
                query_string, variables={"$email": email})
            if len(userstatus['login_attempt']) == 0:
                return False
            if userstatus['login_attempt'][0]['_account_status'] != 'active':
                return False

        query_string = f"""query login_attempt($email: string, $pw: string)
                        {{login_attempt(func: eq(email, $email)) {{ checkpwd(_pw, $pw) }} }}"""
        result = dgraph.query(query_string, variables={
                              "$email": email, "$pw": password})
        if len(result['login_attempt']) == 0:
            return False
        else:
            if result['login_attempt'][0]['checkpwd(_pw)']:
                return cls(email=email)
            else:
                return False

    @classmethod
    def verify_reset_token(cls, token: str) -> Union[bool, Any]:
        try:
            data = jwt.decode(
                token,
                current_app.config['SECRET_KEY'],
                leeway=datetime.timedelta(seconds=10),
                algorithms=["HS256"]
            )
        except:
            return False

        user_id = data.get('confirm')

        user = cls(uid=user_id)
        if user.pw_reset_used:
            return False
        elif user.pw_reset != token:
            return False
        else:
            dgraph.update_entry({'pw_reset|used': True}, uid=user_id)
            return user

    @classmethod
    def verify_email_token(cls, token: str) -> Union[bool, Any]:
        try:
            data = jwt.decode(
                token,
                current_app.config['SECRET_KEY'],
                algorithms=["HS256"]
            )
        except:
            return False

        user_id = data.get('confirm')
        user = cls(uid=user_id)
        if user:
            dgraph.update_entry({'_account_status': 'active'}, uid=user_id)
            return user
        else:
            return False

    def update_profile(self, form_data: dict) -> bool:
        user_data = {}
        for k, v in form_data.data.items():
            if k in ['submit', 'csrf_token']:
                continue
            else:
                user_data[k] = v
        result = dgraph.update_entry(user_data, uid=self.id)
        if result:
            for k, v in user_data.items():
                setattr(self, k, v)
            return True
        else:
            return False

    def change_password(self, form_data: dict) -> bool:
        user_data = {'pw': form_data.data.get('new_password')}
        result = dgraph.update_entry(user_data, uid=self.id)
        if result:
            return True
        else:
            return False

    def get_reset_token(self, expires_sec=1800) -> str:
        reset_token = jwt.encode(
            {
                "confirm": self.id,
                "exp": datetime.datetime.now(tz=datetime.timezone.utc)
                + datetime.timedelta(seconds=expires_sec)
            },
            current_app.config['SECRET_KEY'],
            algorithm="HS256"
        )

        dgraph.update_entry({'pw_reset': reset_token,
                             'pw_reset|used': False}, uid=self.id)
        return reset_token

    def get_invite_token(self, expires_days=7) -> str:
        expires_sec = expires_days * 24 * 60 * 60
        reset_token = jwt.encode(
            {
                "confirm": self.id,
                "exp": datetime.datetime.now(tz=datetime.timezone.utc)
                + datetime.timedelta(seconds=expires_sec)
            },
            current_app.config['SECRET_KEY'],
            algorithm="HS256"
        )
        return reset_token

    def my_entries(self, onlydrafts=False) -> list:
        return self.list_entries(self.uid, onlydrafts=onlydrafts)

    """
        Static Methods
    """

    @staticmethod
    def user_verify(uid, pw):
        query_string = f'''query login_attempt($pw: string)
                {{login_attempt(func: uid({uid})) {{ checkpwd(_pw, $pw) }} }}'''
        result = dgraph.query(query_string, variables={'$pw': pw})
        if len(result['login_attempt']) == 0:
            return False
        else:
            return result['login_attempt'][0]['checkpwd(_pw)']

    @staticmethod
    def check_user(uid: str) -> str:

        query_string = f'''{{ user(func: uid({uid})) @filter(type("User")) {{ uid }} }}'''
        data = dgraph.query(query_string)
        if len(data['user']) == 0:
            return None
        return data['user'][0]['uid']

    @staticmethod
    def check_user_by_email(email: str) -> str:
        query_string = f'''{{ user(func: eq(email, "{email}")) @filter(type("User")) {{ uid }} }}'''
        data = dgraph.query(query_string)
        if len(data['user']) == 0:
            return None
        return data['user'][0]['uid']

    @staticmethod
    def create_user(user_data: dict, invited_by=None) -> Union[bool, str]:
        if type(user_data) is not dict:
            raise TypeError()

        user_data['uid'] = '_:newuser'
        user_data['dgraph.type'] = 'User'
        user_data['role'] = USER_ROLES.Contributor
        user_data['display_name'] = secrets.token_urlsafe(6)
        user_data['preference_emails'] = True
        user_data['_date_joined'] = datetime.datetime.now(
            datetime.timezone.utc).isoformat()
        if not current_app.debug:
            user_data['_account_status'] = 'pending'
        else:
            user_data['_account_status'] = 'active'

        if invited_by:
            user_data['_invited_by'] = {'uid': invited_by,
                                        '_invited_by|date': datetime.datetime.now(datetime.timezone.utc).isoformat()}
            user_data['_account_status'] = 'invited'

        response = dgraph.mutation(user_data)

        if response:
            return response.uids['newuser']
        else:
            return False

    @staticmethod
    def list_entries(user, onlydrafts=False) -> Union[bool, list]:
        query_string = f"""{{ q(func: uid({user})) {{
            drafts: ~_added_by @facets(orderdesc: timestamp) @filter(eq(entry_review_status, "draft"))
            {{ uid _unique_name name dgraph.type entry_review_status channel {{ name }} }} 
            """

        if onlydrafts:
            query_string += '} }'
        else:
            query_string += f"""
                pending: ~_added_by @facets(orderdesc: timestamp) @filter(eq(entry_review_status, "pending"))
                {{ uid _unique_name name dgraph.type entry_review_status channel {{ name }} }} 
                accepted: ~_added_by @facets(orderdesc: timestamp) @filter(eq(entry_review_status, "accepted"))
                {{ uid _unique_name name dgraph.type entry_review_status channel {{ name }} }}
                rejected: ~_added_by  @facets(orderdesc: timestamp) @filter(eq(entry_review_status, "rejected")) 
                {{ uid name entry_review_status channel {{ name }} }}
                }}
                }}
                """

        data = dgraph.query(query_string)

        if len(data['q']) == 0:
            return False

        for item in data['q'][0].keys():
            for entry in data['q'][0][item]:
                if entry.get('dgraph.type'):
                    if 'Entry' in entry['dgraph.type']:
                        entry['dgraph.type'].remove('Entry')
                    if 'Resource' in entry['dgraph.type']:
                        entry['dgraph.type'].remove('Resource')

        return data['q']

    @staticmethod
    def list_users() -> list:
        data = dgraph.query('{ q(func: type("User")) { uid expand(_all_) } }')
        if len(data['q']) == 0:
            return False
        return data['q']
