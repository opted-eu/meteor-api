from flask_wtf import FlaskForm
from wtforms.fields import HiddenField, SubmitField, SelectField
from wtforms.validators import DataRequired


class ReviewFilter(FlaskForm):
    entity = SelectField('Filter by Entity Type',
                         choices=[
                             ('all', 'All'),
                             ('NewsSource', 'News Source'),
                             ('Organization', 'Organization'),
                             ('Subnational', 'Subnational'),
                             ('Archive', 'Data Archive'),
                             ('Dataset', 'Dataset'),
                             ('Tool', 'Tool'),
                             ('ScientificPublication', 'Scientific Publication'),
                             ('Operation', 'Operation'),
                             ('FileFormat', 'File Format'),
                             ('MetaVariable', 'Meta Variable'),
                             ('ConceptVariable', 'Concept Variables'),
                             ('UnitOfAnalysis', 'Unit of Analysis')], validators=[DataRequired()]
                         )

    country = SelectField('Filter by Country')


class ReviewActions(FlaskForm):

    uid = HiddenField(label='UID', validators=[DataRequired()])
    accept = SubmitField('Accept')
    reject = SubmitField('Reject')
