"""
    Defines Response Bodies of API routes
    We use python's built-in type hinting system
    for the self documentation of the API routes.
    To keep things less messy, complex response types are declared here 
"""

import typing

SocialMediaProfile = typing.TypedDict('SocialMediaProfile', {
    "name": str,
    "identifier": str,
    "alternate_names": list,
    "description": str,
    "audience_size": str,
    "audience_size|count": int,
    "audience_size|unit": str,
    "verified_account": bool,
    "date_founded": str,
    "channel_feeds": list
})

PublicationLike = typing.TypedDict('PublicationLike', {
    "cran": str,
    "name": str,
    "alternate_names": list,
    "authors": list,
    "_authors_fallback": list,
    "_authors_fallback|sequence": dict,
    "description": str,
    "conditions_of_access": str,
    "github": str,
    "license": str,
    "doi": str,
    "arxiv": str,
    "open_source": str,
    "platform": list,
    "programming_languages": list,
    "url": str,
    "openalex": str
}
)

SuccessfulAPIOperation = typing.TypedDict('SuccessfulAPIOperation', {
    "status": int,
    "message": str,
    "redirect": str,
    "uid": str
})

LoginToken = typing.TypedDict('LoginToken', {
    "status": str,
    "access_token": str,
    "refresh_token": str,
    "access_token_valid_until": str,
    "refresh_token_valid_until": str
})

AccessToken = typing.TypedDict('AccessToken', {
    "status": str,
    "access_token": str,
    "access_token_valid_until": str,
})

DGraphTypeDescription = typing.TypedDict('DGraphTypeDescription', {
    "name": str,
    "description": str
})

ReverseRelationships = typing.TypedDict('ReverseRelationships', {
    "predicate__dgraphtype": list
})