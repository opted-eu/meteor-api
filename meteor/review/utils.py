
from meteor.users.constants import USER_ROLES
from meteor.review.forms import ReviewActions

def create_review_actions(user, uid, review_status):
    if review_status.lower() != 'pending': return None
    if user._role > USER_ROLES.Contributor:
            review_actions = ReviewActions()
            review_actions.uid.data = uid
    else:
        review_actions = None
    
    return review_actions