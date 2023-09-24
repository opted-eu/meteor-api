from typing import Union, Any
from meteor import login_manager
from flask import current_app
from flask_login import UserMixin
from meteor import dgraph
import jwt
from meteor.users.constants import USER_ROLES
import datetime
import secrets
from meteor.flaskdgraph.dgraph_types import _PrimitivePredicate


def generate_random_username() -> str:
    return secrets.token_urlsafe(6)


class AnonymousUser:
    _role = 0
    uid = None
    is_authenticated = False
    is_active = False
    is_anonymous = True

    def get_id(self):
        return


class UserLogin(UserMixin):

    id = None
    json = {}

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
    
    @classmethod
    def predicates(cls):
        raise NotImplementedError

    """
        Helper Methods for __init__
    """

    def get_user(self, **kwargs):
        user_data = self.get_user_data(**kwargs)
        if user_data:
            self.json = user_data
            for k, v in user_data.items():
                if k == 'uid':
                    self.id = v
                if '|' in k:
                    k = k.replace('|', '_')
                setattr(self, k, v)
            # Overwrite DGraph Predicates
            # Maybe find a more elegant solution later
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
            raise ValueError('User not found!')

    def get_user_data(self, email=None, uid=None) -> Union[dict, None]:

        if email:
            data = dgraph.query(self.email == email)
        else:
            data = dgraph.query(self.uid == uid)

        if len(data['q']) == 0:
            raise ValueError('User not found!')
        data = data['q'][0]
        return data

    """
        Class Methods: 
            Login users
            verify tokens and return instance of User
    """

    @classmethod
    def login(cls, email: str, password: str):
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
        if user._pw_reset_used:
            return False
        elif user._pw_reset != token:
            return False
        else:
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
            return user
        else:
            return False

    def update_profile(self, form_data: dict) -> bool:
        user_data = {}
        delete_data = {}

        editable_predicates = [k for k, v in self.predicates().items() if v.edit]
    
        try:
            data = form_data.data
        except:
            data = form_data
        for k, v in data.items():
            if k not in editable_predicates:
                continue
            if v is None: 
                delete_data[k] = v
            else:
                user_data[k] = v
        result = dgraph.update_entry(user_data, uid=self.id)
        if len(delete_data.keys()) > 0:
            delete_data['uid'] = self.uid
            deleted = dgraph.delete(delete_data)
        if result:
            for k, v in user_data.items():
                setattr(self, k, v)
            return True
        else:
            return False

    def change_password(self, password: str) -> bool:
        user_data = {'pw': password}
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

        dgraph.update_entry({'_pw_reset': reset_token,
                             '_pw_reset|used': False}, uid=self.id)
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
    
    def my_entries(self, 
                   dgraph_type: str = None, 
                   entry_review_status: str = None,
                   page=0) -> list:
        """ 
            List all entries of the user, sorted by `_date_created (newest first).
            
        """
        offset = page * 100
        query_string = """query MyEntries($user: string, $offset: int)
            { q(func: has(_added_by), orderdesc: _date_created, first: 100, offset: $offset)
        """

        filters = ["uid_in(_added_by, $user)"]
        if dgraph_type:
            filters.append(f"type({dgraph_type})")
        if entry_review_status:
            filters.append(f"eq(entry_review_status, {entry_review_status})")
        
        query_string += "@filter(" + " AND ".join(filters) + ")"
        query_string += " { uid _unique_name name dgraph.type _date_created entry_review_status channel { name _unique_name uid }  } }"

        entries = dgraph.query(query_string, variables={'$user': self.uid, '$offset': str(offset)})
        return entries['q']

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
        if current_app.config.get('TESTING'):
            user_data['_account_status'] = 'active'
        else:
            user_data['_account_status'] = 'pending'

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
    def list_entries(user, 
                     onlydrafts=False) -> Union[bool, list]:
        """ 
            DEPRECATED
        
            use: `user.my_entries()` instead
        """
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

        return data['q'][0]

    @staticmethod
    def list_users() -> list:
        data = dgraph.query('{ q(func: type("User")) { uid expand(_all_) } }')
        if len(data['q']) == 0:
            return False
        return data['q']
