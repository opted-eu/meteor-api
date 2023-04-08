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


from flaskinventory.view.utils import InternalURLCol
from flask_table import create_table, Col, DateCol, LinkCol
from flask_table.html import element

# generate table for user admin view
# lists all users and links to edit permissions
def make_users_table(table_data):
    cols = sorted(list(table_data[0].keys()))
    TableCls = create_table('Table')
    TableCls.allow_empty = True
    TableCls.classes = ['table']

    TableCls.add_column('_date_joined', DateCol('Joined Date'))
    TableCls.add_column('email', Col('Email'))
    TableCls.add_column('uid', LinkCol('UID', 'users.edit_user', url_kwargs=dict(uid='uid'), attr_list='uid'))
    TableCls.add_column('_role', Col('User Level'))
    return TableCls(table_data)


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

