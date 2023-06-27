from flask_wtf import FlaskForm
from wtforms import (StringField, SelectField, SubmitField)
from wtforms.validators import DataRequired


class NewEntry(FlaskForm):
    name = StringField('Name of New Entity',
                       validators=[DataRequired()])

    entity = SelectField('Entity Type',
                         choices=[
                             ('Collection', 'Collection'),
                             ('Archive', 'Data Archive'),
                             ('Dataset', 'Dataset'),
                             ('Tool', 'Tool'),
                             ('JournalisticBrand', 'Journalistic Brand'),
                             ('NewsSource', 'News Source'),
                             ('Person', 'Person'),
                             ('PoliticalParty', 'Political Party'),
                             ('Government', 'Government'),
                             ('Parliament', 'Parliament'),
                             ('Organization', 'Organization')
                         ],
                         validators=[DataRequired()])


class AutoFill(FlaskForm):
    platform = SelectField('Autofill from',
                            choices=[('arxiv', 'arXiv'),
                                      ('doi', 'DOI'),
                                     ('cran', 'CRAN')],
                            validators=[DataRequired()])

    identifier = StringField('Identifier',
                       validators=[DataRequired()])

    submit = SubmitField('Magic!')
