from meteor.users.constants import USER_ROLES

def can_edit(entry, user) -> bool:
    if "entry_review_status" in entry.keys():
        if entry.get('entry_review_status') in ['pending', 'accepted']:
            if user.is_authenticated:
                if user._role > USER_ROLES.Contributor or entry.get('_added_by').get('uid') == user.id:
                    return True
                else:
                    return False
            else: 
                return False
        elif entry.get('entry_review_status') == 'draft':
            if user.is_authenticated:
                if user._role > USER_ROLES.Reviewer or entry.get('_added_by').get('uid') == user.id:
                    return True
                else: 
                    return False
            else: 
                return False
        else:
            return False
    else:
        return True


def can_delete(entry) -> bool:
    from flask_login import current_user
    if "entry_review_status" in entry.keys():
        if entry['entry_review_status'] == 'draft':
            if current_user.is_authenticated:
                if current_user._role > USER_ROLES.Reviewer or entry['_added_by']['uid'] == current_user.id:
                    return True
                else: 
                    return False
            else: 
                return False
        else:
            return False
    else:
        return True

def channel_filter(channel: str) -> list:
    if channel == 'print':
        return ['identifier', 
                'transcript_kind',
                'website_allows_comments', 
                'website_comments_registration_required']
    elif channel == 'website':
        return ['transcript_kind',
                'channel_epaper']
    elif channel == 'transcript':
        return ['website_allows_comments', 
                'website_comments_registration_required',
                'channel_epaper']
    elif channel in ['facebook', 'instagram', 'vkontakte']:
        return ['transcript_kind',
                'website_allows_comments', 
                'website_comments_registration_required',
                'channel_epaper',
                'payment_model']
    elif channel in ['telegram', 'twitter']:
        return ['transcript_kind',
                'website_allows_comments', 
                'website_comments_registration_required',
                'channel_epaper',
                'payment_model',
                'date_founded']
    else: return []
