from flask_wtf import FlaskForm
from wtforms import (StringField, SelectField, SubmitField)
from wtforms.validators import DataRequired


class NewEntry(FlaskForm):
    name = StringField('Name of New Entity',
                       validators=[DataRequired()])

    entity = SelectField('Entity Type',
                         choices=[
                             ('NewsSource', 'News Source'),
                             ('Organization', 'Media Organization'),
                             ('Archive', 'Data Archive'),
                             ('Dataset', 'Dataset'),
                             ('Tool', 'Tool'),
                             ('Corpus', 'Corpus'),
                              ('ScientificPublication', 'Scientific Publication')
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
