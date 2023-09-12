import flask_jwt_extended as jwtx
from flask import current_app
from flaskinventory.users.dgraph import UserLogin
from flaskinventory.main.model import User
from flaskinventory import dgraph

jwt = jwtx.JWTManager()


# Register a callback function that takes whatever object is passed in as the
# identity when creating JWTs and converts it to a JSON serializable format.
@jwt.user_identity_loader
def user_identity_lookup(user):
    try:
        return user.id
    except:
        return user


# Register a callback function that loads a user from your database whenever
# a protected route is accessed. This should return any python object on a
# successful lookup, or None if the lookup failed for any reason (for example
# if the user has been deleted from the database).
@jwt.user_lookup_loader
def user_lookup_callback(_jwt_header, jwt_data):
    identity = jwt_data["sub"]
    user = User(uid=identity)
    return user

@jwt.token_in_blocklist_loader
def check_if_token_is_revoked(jwt_header, jwt_payload: dict):
    jti = jwt_payload["jti"]
    token_in_redis = dgraph.get_uid(field="_jti", value=jti)
    return token_in_redis is not None