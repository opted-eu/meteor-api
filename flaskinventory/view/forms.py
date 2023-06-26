from flask import current_app
from flask_wtf import FlaskForm
from wtforms import SelectField, SubmitField
from wtforms.validators import DataRequired
from flaskinventory.flaskdgraph.customformfields import TomSelectMultipleField

class SimpleQuery(FlaskForm):

    entity = SelectField('Entity Type',
                         choices=[
                             ('PoliticalParty', 'Political Party'),
                             ('Dataset', 'Dataset'),
                             ('Archive', 'Data Archive'),
                             ('JournalisticBrand', 'Journalistic Brand'),
                             ('Tool', 'Tool'),
                             ('Collection', 'Collection'),
                             ('Government', 'Government'),
                             ('Parliament', 'Parliament'),
                             ('Person', 'Person'),
                             ('Organization', 'Organization')
                             ],
                            validators=[DataRequired()],
                            name='dgraph.type')
    
    country = TomSelectMultipleField('Filter by Country')

    submit = SubmitField('Query')

    def get_field(self, field):
        return getattr(self, field, None)