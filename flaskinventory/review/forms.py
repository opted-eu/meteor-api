from wtforms.fields.simple import HiddenField, SubmitField
from flask_wtf import FlaskForm
from wtforms import SelectField
from wtforms.validators import DataRequired

class ReviewFilter(FlaskForm):
    entity = SelectField('Filter by Entity Type',
                         choices=[
                             ('all', 'All'),
                             ('Source', 'News Source'),
                             ('Organization', 'Media Organization'),
                             ('Subunit', 'Subunit'),
                             ('Archive', 'Data Archive'),
                             ('Dataset', 'Dataset'),
                             ('ResearchPaper', 'Research Paper')], validators=[DataRequired()]
                            )
    
    country = SelectField('Filter by Country')

    submit = SubmitField('Filter')


class ReviewActions(FlaskForm):

    uid = HiddenField(label='UID', validators=[DataRequired()])
    accept = SubmitField('Accept')
    reject = SubmitField('Reject')
    edit = SubmitField('Edit')

