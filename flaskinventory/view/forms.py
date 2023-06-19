from flask import current_app
from flask_wtf import FlaskForm
from wtforms import SelectField, SubmitField
from wtforms.validators import DataRequired
from flaskinventory.flaskdgraph.customformfields import TomSelectMultipleField

class SimpleQuery(FlaskForm):

    entity = SelectField('Entity Type',
                         choices=[
                             ('PoliticalParty', 'Political Party'),
                             ('JournalisticBrand', 'Journalistic Brand'),
                             ('Government', 'Government'),
                             ('Parliament', 'Parliament'),
                             ('Person', 'Person'),
                             ('Organization', 'Organization'),
                             ('Archive', 'Data Archive'),
                             ('Dataset', 'Dataset'),
                             ('Tool', 'Tool'),
                             ('Collection', 'Collection')
                             ],
                            validators=[DataRequired()],
                            name='dgraph.type')
    
    country = TomSelectMultipleField('Filter by Country')

    submit = SubmitField('Query')

    def get_field(self, field):
        return getattr(self, field, None)