__version__ = "2.0.0"

import logging
import json

from flask import Flask
from .config import create_filehandler, create_slackhandler
from meteor.config import Config

#### Load Extensions ####
# Login Extension
from flask_login import LoginManager, AnonymousUserMixin

# E-Mail Extension
from flask_mail import Mail
# Forms Extension
# from flask_wtf.csrf import CSRFProtect

# Markdown Rendering
from flaskext.markdown import Markdown
from markdown.extensions.toc import TocExtension

# Custom Dgraph Extension
from meteor.flaskdgraph import DGraph

dgraph = DGraph()

class AnonymousUser(AnonymousUserMixin):
    _role = 0
    uid = None

login_manager = LoginManager()
login_manager.login_view = 'users.login'
login_manager.login_message_category = 'info'
login_manager.anonymous_user = AnonymousUser


mail = Mail()

# JWT Extension
from meteor.users.authentication import jwt

from flask.json.provider import DefaultJSONProvider
import datetime

class UpdatedJSONProvider(DefaultJSONProvider):
    def default(self, o):
        if isinstance(o, (datetime.date, datetime.datetime)):
            return o.isoformat()
        return super().default(o)


def create_app(config_class=Config, config_json=None):
    # assert versions
    import wtforms
    assert wtforms.__version__.startswith('3.'), 'WTForms Version 3.X.X is required!'

    app = Flask(__name__)
    app.json = UpdatedJSONProvider(app)

    app.logger.addHandler(create_filehandler())

    if config_json:
        app.config.from_file(config_json, json.load)
    else:
        app.config.from_object(config_class)

    if 'TESTING' not in app.config:
        app.config['TESTING'] = False

    if app.config.get('DEBUG_MODE'):
        app.debug = True
        try:
            with open('.git/HEAD') as f:
                git = f.read()
            branch =  git.split('/')[-1].strip()
            with open('.git/' + git[5:-1]) as f:
                commit = f.read()
            global __version__ 
            __version__ += '-' + branch + '-' + commit[:7]
        except:
            pass 
    
    if app.debug:
        app.logger.setLevel(logging.DEBUG)
    
    if app.config.get('SLACK_LOGGING_ENABLED'):
        try:
            slack_handler = create_slackhandler(app.config.get('SLACK_WEBHOOK'))
            app.logger.addHandler(slack_handler)
            app.logger.error('Initialized Slack Logging!')
        except Exception as e:
            app.logger.error(f'Slack Logging not working: {e}')

    app.config['APP_VERSION'] = __version__

    from meteor.users.routes import users
    from meteor.view.routes import view
    from meteor.add.routes import add
    from meteor.edit.routes import edit
    from meteor.review.routes import review
    from meteor.endpoints.routes import endpoint
    from meteor.main.routes import main
    from meteor.errors.handlers import errors
    app.register_blueprint(users)
    app.register_blueprint(view)
    app.register_blueprint(add)
    app.register_blueprint(edit)
    app.register_blueprint(review)
    app.register_blueprint(endpoint)
    app.register_blueprint(main)
    app.register_blueprint(errors)

    jwt.init_app(app)

    dgraph.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)

    # csrf = CSRFProtect(app)

    from meteor.api.routes import api
    app.register_blueprint(api, url_prefix='/api')

    Markdown(app, extensions=[TocExtension(baselevel=3, anchorlink=True), 'fenced_code'])

    return app
