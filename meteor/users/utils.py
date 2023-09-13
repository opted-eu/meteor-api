import secrets
import os
from functools import wraps
from PIL import Image
from flask import current_app, flash, abort
from flask_login import current_user


# custom decorator @requires_access_level()
# access level is integer
def requires_access_level(access_level):
    def decorator(func):
        @wraps(func)
        def decorated_view(*args, **kwargs):
            if current_user._role < access_level:
                flash(f'You are not allowed to view this page!', 'warning')
                # return redirect(url_for('main.home'))
                return abort(403)
            return func(*args, **kwargs)
        return decorated_view
    return decorator


# unused utility function for saving picture files to static folder
def save_picture(form_picture):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(
        current_app.root_path, 'static', 'profile_pics', picture_fn)

    output_size = (300, 300)
    i = Image.open(form_picture)
    i.thumbnail(output_size)
    i.save(picture_path)

    return picture_fn

