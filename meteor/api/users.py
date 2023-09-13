from meteor import dgraph
from meteor.api.errors import ValidationError
from email_validator import validate_email as _validate_email, EmailNotValidError

def validate_email(email: str) -> str:
    """ 
        Soft wrapper around email_validator module
        
        Raises exception when email cannot be validated
    """
    try:
        emailinfo = _validate_email(email, check_deliverability=False)
        return emailinfo.normalized
    except EmailNotValidError:
        raise ValidationError('Are you sure the email is correct?')

def email_is_taken(email: str) -> None:
    """ 
        First validates the email address (if it is a valid email)
        Then checks whether the email is already in dgraph.

        Raises exception when email already in dgraph!
    """
    email = validate_email(email)
    if dgraph.get_uid('email', f'{email}'):
        raise ValidationError('That email is taken. Try to login!')

