from dateutil import parser as dateparser
from flask import url_for

"""
Helper function to evaluate viewing permissions
Entries with "draft" or "pending" status can only be
viewed by the user who created the item or reviewers/admins
"""
def can_view(entry, user):
    if "entry_review_status" in entry.keys():
        if entry.get('entry_review_status') in ['pending', 'rejected']:
            if user.is_authenticated:
                if user._role > 1 or entry.get('_added_by').get('uid') == user.id:
                    return True
                else:
                    return False
            else: 
                return False
        elif entry.get('entry_review_status') == 'draft':
            if user.is_authenticated:
                if user._role > 2 or entry.get('_added_by').get('uid') == user.id:
                    return True
                else: 
                    return False
            else: 
                return False
        else:
            return True
    else:
        return True
