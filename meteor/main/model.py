from meteor import login_manager
import datetime

from meteor.flaskdgraph.dgraph_types import *

from meteor.main.custom_types import *

from meteor.users.constants import USER_ROLES
from meteor.users.dgraph import UserLogin, generate_random_username
from meteor.flaskdgraph import Schema


"""
    Users
"""


class User(Schema, UserLogin):
    """Meteor User (private)"""

    __permission_new__ = USER_ROLES.Admin
    __permission_edit__ = USER_ROLES.Admin
    # prevent any kind of editing
    __private__ = True

    uid = UIDPredicate()
    email = String(
        label="Email",
        read_only=True,
        edit=False,
        required=True,
        directives=["@index(hash)", "@upsert"],
        overwrite=False,
    )
    display_name = String(
        "Username",
        default=generate_random_username,
        description="Your publicly visible username",
        required=True,
        overwrite=False,
    )
    _pw = Password(label="Password", required=True)
    _pw_reset = String(hidden=True, edit=False, facets=[Facet("used", dtype=bool)])

    orcid = String(label="ORCID", directives=["@index(hash)"])
    _date_joined = DateTime(
        label="Date joined",
        description="Date when this account was created",
        read_only=True,
        edit=False,
        directives=["@index(hour)"],
    )
    role = SingleChoiceInt(
        label="User Role",
        edit=False,
        read_only=True,
        default=USER_ROLES.Contributor,
        choices=USER_ROLES.dict_reverse,
    )

    affiliation = String()
    _account_status = SingleChoice(
        choices={"pending": "Pending", "active": "Active"},
        hidden=True,
        edit=False,
        default="pending",
    )

    preference_emails = Boolean("Receive Email notifications", default=True)
    follows_entities = ListRelationship(
        "Following", autoload_choices=False, edit=False, relationship_constraint="Entry"
    )
    follows_types = ListString(
        "Following types", directives=["@index(hash)"], edit=False
    )


@login_manager.user_loader
def load_user(user_id):
    if not user_id.startswith("0x"):
        return
    if not UserLogin.check_user(user_id):
        return
    return User(uid=user_id)


"""
    Entry
"""


class Entry(Schema):
    """Base Entry Type that all user generated types inherit from"""

    __permission_new__ = USER_ROLES.Contributor
    __permission_edit__ = USER_ROLES.Contributor

    uid = UIDPredicate()

    _unique_name = UniqueName()

    _date_created = DateTime(
        new=False,
        edit=False,
        read_only=True,
        hidden=True,
        default=datetime.datetime.now,
        directives=["@index(day)"],
    )

    _date_modified = DateTime(
        new=False, edit=False, read_only=True, hidden=True, directives=["@index(day)"]
    )

    _added_by = SingleRelationship(
        label="Added by",
        relationship_constraint="User",
        new=False,
        edit=False,
        read_only=True,
        hidden=True,
        facets=[Facet("ip"), Facet("timestamp", dtype=datetime.datetime)],
    )

    _reviewed_by = SingleRelationship(
        label="Reviewed by",
        relationship_constraint="User",
        new=False,
        edit=False,
        read_only=True,
        hidden=True,
        facets=[Facet("ip"), Facet("timestamp", dtype=datetime.datetime)],
    )

    _edited_by = ListRelationship(
        label="Edited by",
        relationship_constraint="User",
        new=False,
        edit=False,
        read_only=True,
        hidden=True,
        facets=[Facet("ip"), Facet("timestamp", dtype=datetime.datetime)],
    )

    entry_review_status = SingleChoice(
        choices={
            "draft": "Draft",
            "pending": "Pending",
            "accepted": "Accepted",
            "rejected": "Rejected",
        },
        default="pending",
        required=True,
        new=False,
        permission=USER_ROLES.Reviewer,
    )

    name = String(
        required=True, directives=["@index(term, trigram)", "@lang"], overwrite=False
    )

    alternate_names = ListString(directives=["@index(term, trigram)"])

    description = String(
        large_textfield=True, directives=["@index(fulltext, trigram, term)"]
    )

    wikidata_id = String(
        label="WikiData ID",
        description="ID as used by WikiData",
        new=False,
        directives=["@index(hash)"],
    )

    hdl = String(
        label="HDL",
        description="handle.net external identifier",
        directives=["@index(hash)"],
        hidden=True,
    )

    _legacy_id = ListString(
        directives=["@index(hash)"],
        label="Legacy ID",
        description="Old ID used by OPTED Workpackages. Preserved for backwards compatibility.",
        new=False,
        edit=False,
        read_only=True,
        hidden=True,
    )


class PoliticalParty(Entry):
    """Political parties as legally registered"""

    name_abbrev = String(
        label="Abbreviated Name",
        description="Abbreviation/Acronym of the party name.",
        directives=["@index(term, trigram)", "@lang"],
        queryable=True,
    )

    parlgov_id = String(
        label="ParlGov ID",
        description="ID of party in ParlGov Dataset",
        directives=["@index(hash)"],
    )

    partyfacts_id = String(
        label="Party Facts ID",
        description="ID of party in Party Facts Dataset",
        directives=["@index(hash)"],
    )

    country = SingleRelationship(
        relationship_constraint=["Country", "Multinational"],
        autoload_choices=True,
        required=True,
        queryable=True,
        description="In which country is the political party registered?",
        render_kw={"placeholder": "Select a country..."},
        predicate_alias=["countries"],
    )

    url = String(
        label="URL",
        description="Official website of party",
        directives=["@index(hash)"],
    )

    color_hex = String()

    publishes = ListRelationship(
        relationship_constraint="NewsSource",
        overwrite=True,
        description="Which news sources publishes the political party?",
        render_kw={
            "placeholder": "Type to search existing news sources and add multiple..."
        },
    )


class Organization(Entry):
    """companies, NGOs, businesses, media organizations"""

    name = String(
        label="Organization Name",
        required=True,
        description="What is the legal or official name of the media organisation?",
        render_kw={"placeholder": "e.g. The Big Media Corp."},
        overwrite=False,
    )

    alternate_names = ListString(
        description="Does the organisation have any other names or common abbreviations?",
        render_kw={"placeholder": "Separate by comma"},
    )

    ownership_kind = SingleChoice(
        choices={
            "NA": "Don't know / NA",
            "private ownership": "Mainly private Ownership",
            "public ownership": "Mainly public ownership",
            "unknown": "Unknown Ownership",
        },
        description="Is the organization mainly privately owned or publicly owned?",
        queryable=True,
    )

    country = SingleRelationship(
        relationship_constraint="Country",
        autoload_choices=True,
        queryable=True,
        description="In which country is the organisation located?",
        render_kw={"placeholder": "Select a country..."},
        predicate_alias=["countries"],
        overwrite=True,
    )

    publishes = ListRelationship(
        relationship_constraint="NewsSource",
        overwrite=True,
        description="Which news sources publishes the organisation (or person)?",
        render_kw={
            "placeholder": "Type to search existing news sources and add multiple..."
        },
    )

    owns = ListRelationship(
        allow_new=True,
        relationship_constraint="Organization",
        overwrite=True,
        description="Which other media organisations are owned by this new organisation (or person)?",
        render_kw={
            "placeholder": "Type to search existing organisations and add multiple..."
        },
    )

    is_ngo = Boolean("Is NGO", description="Is the organisation an NGO?")

    party_affiliated = SingleChoice(
        choices={"NA": "Don't know / NA", "yes": "Yes", "no": "No"},
        new=False,
        queryable=True,
    )

    address = AddressAutocode(
        new=False, render_kw={"placeholder": "Main address of the organization."}
    )

    employees = String(
        description="How many employees does the news organization have?",
        render_kw={"placeholder": "Most recent figure as plain number"},
        new=False,
    )

    date_founded = DateTime(
        new=False, overwrite=True, queryable=True, directives=["@index(day)"]
    )


class JournalisticBrand(Entry):
    """A journalistic brand that encompasses different projects for distributing news"""

    sources_included = ListRelationship(
        description="Journalistic News Sources distributed under this brand",
        queryable=True,
        relationship_constraint="NewsSource",
    )

    countries = SourceCountrySelection(
        label="Countries",
        description="Which countries are in the geographic scope?",
        required=True,
        queryable=True,
        predicate_alias=["country"],
    )

    subnational_scope = SubunitAutocode(
        label="Subunits",
        description="What is the subnational scope?",
        tom_select=True,
        queryable=True,
    )


class NewsSource(Entry):
    """
    A single journalistic project;
    a social media channel of a political party / person / government institution, etc
    """

    channel = SingleRelationship(
        description="Through which channel is the news source distributed?",
        edit=False,
        autoload_choices=True,
        relationship_constraint="Channel",
        read_only=True,
        required=True,
        queryable=True,
        predicate_alias=["channels"],
    )

    name = String(
        label="Name of the News Source",
        required=True,
        description="What is the name of the news source?",
        render_kw={"placeholder": "e.g. 'The Royal Gazette'"},
        overwrite=False,
    )

    journalistic_brand = ReverseRelationship(
        "news_sources_included", relationship_constraint="JournalisticBrand"
    )

    identifier = String(
        label="URL of Channel",
        description="What is the url or social media handle of the news source?",
        facets=[Facet("kind")],
        directives=["@index(hash)"],
    )

    verified_account = Boolean(new=False, edit=False, queryable=True)

    alternate_names = ListString(
        description="Is the news source known by alternative names (e.g. Krone, Die Kronen Zeitung)?",
        render_kw={"placeholder": "Separate by comma"},
    )

    transcript_kind = SingleChoice(
        description="What kind of show is transcribed?",
        choices={
            "tv": "TV (broadcast, cable, satellite, etc)",
            "radio": "Radio",
            "podcast": "Podcast",
            "NA": "Don't know / NA",
        },
        queryable=True,
    )

    website_allows_comments = SingleChoice(
        description="Does the online news source have user comments below individual news articles?",
        choices={"yes": "Yes", "no": "No", "NA": "Don't know / NA"},
        queryable=True,
    )

    website_comments_registration_required = SingleChoice(
        label="Registraion required for posting comments",
        description="Is a registration or an account required to leave comments?",
        choices={"yes": "Yes", "no": "No", "NA": "Don't know / NA"},
    )

    date_founded = Year(
        description="What year was the news source date_founded?",
        overwrite=True,
        queryable=True,
    )

    publication_kind = MultipleChoice(
        description="What label or labels describe the main source?",
        choices={
            "newspaper": "Newspaper",
            "news site": "News Site",
            "news agency": "News Agency",
            "magazine": "Magazine",
            "tv show": "TV Show / TV Channel",
            "radio show": "Radio Show / Radio Channel",
            "podcast": "Podcast",
            "news blog": "News Blog",
            "alternative media": "Alternative Media",
            "organizational communication": "Organizational Communication",
        },
        tom_select=True,
        required=True,
        queryable=True,
    )

    special_interest = Boolean(
        description="Does the news source have one main topical focus?",
        label="Yes, is a special interest publication",
        queryable=True,
        query_label="Special Interest Publication",
    )

    topical_focus = MultipleChoice(
        description="What is the main topical focus of the news source?",
        choices={
            "economy": "Business, Economy, Finance & Stocks",
            "education": "Education",
            "environment": "Environment",
            "health": "Health",
            "media": "Media",
            "politics": "Politics",
            "religion": "Religion",
            "society": "Society & Panorama",
            "science": "Science & Technology",
            "youth": "Youth",
            "NA": "Don't Know / NA",
        },
        tom_select=True,
        queryable=True,
    )

    publication_cycle = SingleChoice(
        description="What is the publication cycle of the source?",
        choices={
            "continuous": "Continuous",
            "daily": "Daily (7 times a week)",
            "multiple times per week": "Multiple times per week",
            "weekly": "Weekly",
            "twice a month": "Twice a month",
            "monthly": "Monthly",
            "less than monthly": "Less frequent than monthly",
            "NA": "Don't Know / NA",
        },
        required=True,
        queryable=True,
    )

    publication_cycle_weekday = MultipleChoiceInt(
        description="Please indicate the specific day(s) when the news source publishes.",
        choices={
            "1": "Monday",
            "2": "Tuesday",
            "3": "Wednesday",
            "4": "Thursday",
            "5": "Friday",
            "6": "Saturday",
            "7": "Sunday",
        },
        tom_select=True,
    )

    geographic_scope = SingleChoice(
        description="What is the geographic scope of the news source?",
        choices={
            "multinational": "Multinational",
            "national": "National",
            "subnational": "Subnational",
        },
        required=True,
        radio_field=True,
        queryable=True,
    )

    countries = SourceCountrySelection(
        label="Countries",
        description="Which countries are in the geographic scope?",
        required=True,
        queryable=True,
        predicate_alias=["country"],
    )

    subnational_scope = SubunitAutocode(
        label="Subunits",
        description="What is the subnational scope?",
        tom_select=True,
        queryable=True,
    )

    languages = ListRelationship(
        description="In which language(s) does the news source publish its news texts?",
        relationship_constraint="Language",
        required=True,
        tom_select=True,
        queryable=True,
        autoload_choices=True,
    )

    payment_model = SingleChoice(
        description="Is the content produced by the news source accessible free of charge?",
        choices={
            "free": "All content is free of charge",
            "partly free": "Some content is free of charge",
            "not free": "Paid content only",
            "NA": "Don't Know / NA",
        },
        required=True,
        radio_field=True,
        queryable=True,
    )

    contains_ads = SingleChoice(
        description="Does the news source contain advertisements?",
        choices={
            "yes": "Yes",
            "no": "No",
            "non subscribers": "Only for non-subscribers",
            "NA": "Don't Know / NA",
        },
        required=True,
        radio_field=True,
        queryable=True,
    )

    audience_size = ListDatetime(
        facets=[
            Facet(
                "unit",
                queryable=True,
                choices=[
                    "followers",
                    "subscribers",
                    "copies sold",
                    "likes",
                    "daily visitors",
                ],
            ),
            Facet(
                "count",
                dtype=int,
                queryable=True,
                comparison_operators={"gt": "greater", "lt": "less"},
            ),
            Facet("data_from"),
        ],
    )

    audience_size_recent = Integer(
        facets=[
            Facet(
                "unit",
                queryable=True,
                choices=[
                    "followers",
                    "subscribers",
                    "copies sold",
                    "likes",
                    "daily visitors",
                ],
            ),
            Facet("data_from"),
            Facet("timestamp", dtype=datetime.datetime),
        ]
    )

    published_by = ReverseListRelationship(
        "publishes",
        label="Published by",
        relationship_constraint=[
            "Organization",
            "Political Party",
            "Person",
            "Government",
            "Parliament",
        ],
    )

    channel_epaper = SingleChoice(
        description="Does the print news source have an e-paper version?",
        choices={"yes": "Yes", "no": "No", "NA": "Don't know / NA"},
        queryable=True,
        query_label="E-Paper Available",
    )

    sources_included = ReverseListRelationship(
        "sources_included",
        relationship_constraint=["Archive", "Dataset", "ScientificPublication"],
        query_label="News source included in these resources",
        queryable=True,
        new=False,
        edit=False,
    )

    archive_sources_included = ReverseListRelationship(
        "sources_included",
        relationship_constraint="Archive",
        description="Are texts from the news source available for download in one or several of the following data archives?",
        label="News source included in these archives",
    )

    dataset_sources_included = ReverseListRelationship(
        "sources_included",
        relationship_constraint="Dataset",
        description="Is the news source included in one or several of the following annotated media text data sets?",
        label="News source included in these datasets",
    )

    party_affiliated = SingleChoice(
        description="Is the news source close to a political party?",
        choices={
            "NA": "Don't know / NA",
            "yes": "Yes",
            "no": "No",
        },
        queryable=True,
    )

    defunct = Boolean(
        description="Is the news source defunct or out of business?", queryable=True
    )

    related_news_sources = MutualListRelationship(
        allow_new=True, autoload_choices=False, relationship_constraint="NewsSource"
    )


class Government(Entry):
    """National, supranational or subnational executives"""

    country = SingleRelationship(
        relationship_constraint=["Country", "Multinational"],
        required=True,
        queryable=True,
        predicate_alias=["countries"],
    )

    languages = ListRelationship(
        relationship_constraint=["Language"], queryable=True, autoload_choices=True
    )

    geographic_scope = SingleChoice(
        description="What is the geographic scope of this government?",
        choices={
            "multinational": "Multinational",
            "national": "National",
            "subnational": "Subnational",
        },
        default="national",
        required=True,
        radio_field=True,
        queryable=True,
    )

    subnational = SingleRelationship(
        relationship_constraint="Subnational", queryable=True
    )

    url = String(
        label="URL",
        description="Official website of the government",
        directives=["@index(hash)"],
    )


class Parliament(Entry):
    """National, supranational or subnational legislative bodies"""

    country = SingleRelationship(
        relationship_constraint=["Country", "Multinational"],
        required=True,
        queryable=True,
        predicate_alias=["countries"],
    )

    languages = ListRelationship(
        relationship_constraint=["Language"], queryable=True, autoload_choices=True
    )

    geographic_scope = SingleChoice(
        description="What is the geographic scope of this parliament?",
        choices={
            "multinational": "Multinational",
            "national": "National",
            "subnational": "Subnational",
        },
        default="national",
        required=True,
        radio_field=True,
        queryable=True,
    )

    url = String(
        label="URL",
        description="Official website of the parliament",
        directives=["@index(hash)"],
    )


class Person(Entry):
    """
    Individual (e.g., politician, business owner) to whom
    a resource can be attributed
    """

    is_politician = Boolean(
        label="Politician", description="Is the person a politician?", queryable=True
    )

    country = SingleRelationship(
        relationship_constraint=["Country"],
        queryable=True,
        predicate_alias=["countries"],
    )

    url = String(
        label="URL",
        description="Website related_news_sources to the person",
        directives=["@index(hash)"],
    )

    publishes = ListRelationship(
        relationship_constraint="NewsSource",
        overwrite=True,
        description="Which news sources does this person publish?",
        render_kw={
            "placeholder": "Type to search existing news sources and add multiple..."
        },
    )

    owns = ListRelationship(
        allow_new=True,
        relationship_constraint="Organization",
        overwrite=True,
        description="Which organisations are owned by this person?",
        render_kw={
            "placeholder": "Type to search existing organisations and add multiple..."
        },
    )


class Channel(Entry):
    """Technology used to distribute texts"""

    __permission_new__ = USER_ROLES.Admin
    __permission_edit__ = USER_ROLES.Admin


class Country(Entry):
    """Geographic / Political Entity"""

    __permission_new__ = USER_ROLES.Admin
    __permission_edit__ = USER_ROLES.Admin

    iso_3166_1_2 = String(permission=USER_ROLES.Admin, directives=["@index(exact)"])
    iso_3166_1_3 = String(permission=USER_ROLES.Admin, directives=["@index(exact)"])
    opted_scope = Boolean(
        description="Is country in the scope of OPTED?", label="Yes, in scope of OPTED"
    )


class Multinational(Entry):
    """Bundle of Geographic / Political Entities"""

    __permission_new__ = USER_ROLES.Admin
    __permission_edit__ = USER_ROLES.Admin

    iso_3166_1_2 = String(permission=USER_ROLES.Admin, directives=["@index(exact)"])
    iso_3166_1_3 = String(permission=USER_ROLES.Admin, directives=["@index(exact)"])
    opted_scope = Boolean(
        description="Is country in the scope of OPTED?", label="Yes, in scope of OPTED"
    )

    membership = ListRelationship(
        description="Which countries are part of this multinational construct?",
        relationship_constraint=["Country"],
    )


class Subnational(Entry):
    """Subunits of Country"""

    __permission_new__ = USER_ROLES.Reviewer
    __permission_edit__ = USER_ROLES.Reviewer

    country = SingleRelationship(
        required=True,
        queryable=True,
        tom_select=True,
        autoload_choices=True,
        overwrite=True,
        relationship_constraint="Country",
        predicate_alias=["countries"],
    )

    iso_3166_1_2 = String(
        description="ISO 3166-1 Alpha 2 code of the country this subunit belongs to",
        directives=["@index(exact)"],
    )

    iso_3166_1_3 = String(
        description="ISO 3166-1 Alpha 3 code of the country this subunit belongs to",
        directives=["@index(exact)"],
    )

    location_point = Geo(edit=False, new=False)


class Archive(Entry):
    """
    Digital storages for full-text data
    that are regularly updated and can be queried on demand
    """

    name = String(
        description="What is the name of the archive?", required=True, overwrite=False
    )

    alternate_names = ListString(
        description="Does the archive have other names?",
        render_kw={"placeholder": 'Separate by comma ","'},
    )

    description = String(large_textfield=True)

    url = String(directives=["@index(hash)"])

    authors = AuthorList(allow_new=True, relationship_constraint="Author")

    _authors_fallback = OrderedListString(
        delimiter=";", directives=["@index(term)"], edit=False, tom_select=True
    )

    doi = String(label="DOI", directives=["@index(hash)"])
    arxiv = String(label="arXiv", directives=["@index(hash)"])

    conditions_of_access = SingleChoice(
        description="How can the user access the archive?",
        choices={
            "NA": "NA / Unknown",
            "free": "Free",
            "registration": "Registration Required",
            "request": "Upon Request",
            "purchase": "Purchase",
        },
        queryable=True,
    )

    sources_included = ListRelationship(
        relationship_constraint=[
            "NewsSource",
            "Organization",
            "PoliticalParty",
            "Government",
            "Parliament",
        ],
        queryable=True,
    )

    geographic_scope = MultipleChoice(
        description="What is the geographic scope of the archive?",
        choices={
            "multinational": "Multinational",
            "national": "National",
            "subnational": "Subnational",
        },
        required=True,
        tom_select=True,
        # radio_field=True,
        queryable=True,
    )

    fulltext_available = Boolean(description="Archive contains fulltext")

    countries = ListRelationship(
        relationship_constraint=["Country", "Multinational"],
        autoload_choices=True,
        queryable=True,
        predicate_alias=["country"],
    )

    text_types = ListRelationship(
        description="Text Genres covered by archive",
        relationship_constraint="TextType",
        required=True,
        autoload_choices=True,
        queryable=True,
    )

    text_units = ListRelationship(
        description="List of text units available in the data archive (e.g., sentences, paragraphs, tweets, news articles, summaries, headlines)",
        relationship_constraint="UnitOfAnalysis",
        render_kw={"placeholder": "Select multiple..."},
        autoload_choices=True,
        allow_new=True,
        queryable=True,
    )

    modalities = ListRelationship(
        description="What type of content is included in the archive?",
        relationship_constraint="Modality",
        autoload_choices=True,
        allow_new=True,
        queryable=True,
    )

    languages = ListRelationship(
        description="Which languages are covered in the archive?",
        tom_select=True,
        relationship_constraint="Language",
        render_kw={"placeholder": "Select multiple..."},
        autoload_choices=True,
        queryable=True,
    )

    file_formats = ListRelationship(
        description="In which file format(s) can text data be retrieved from this Archive?",
        autoload_choices=True,
        allow_new=True,
        relationship_constraint="FileFormat",
        render_kw={"placeholder": "Select multiple..."},
    )

    date_modified = DateTime(
        description="Last known date when archive was updated.",
        directives=["@index(day)"],
        new=False,
    )

    meta_variables = ListRelationship(
        description="List of meta data included in the archive (e.g., date, language, source, medium)",
        relationship_constraint="MetaVariable",
        render_kw={"placeholder": "Select multiple..."},
        autoload_choices=True,
        queryable=True,
    )

    concept_variables = ListRelationship(
        description="List of variables based on concepts (e.g. sentiment, frames, etc)",
        relationship_constraint="ConceptVariable",
        render_kw={"placeholder": "Select multiple..."},
        autoload_choices=True,
        queryable=True,
    )


class Dataset(Entry):
    """Results of text analysis; or static collections of full-text data"""

    name = String(
        description="What is the name of the dataset?", required=True, overwrite=False
    )

    alternate_names = ListString(
        description="Does the dataset have other names?",
        render_kw={"placeholder": 'Separate by comma ","'},
        overwrite=True,
    )

    authors = AuthorList(
        allow_new=True, relationship_constraint="Author", required=True
    )

    _authors_fallback = OrderedListString(
        delimiter=";", directives=["@index(term)"], edit=False, tom_select=True
    )

    date_published = Year(
        label="Year of publication",
        description="Which year was the dataset published?",
        directives=["@index(day)"],
    )

    date_modified = DateTime(
        description="When was the dataset last updated?",
        directives=["@index(day)"],
        new=False,
    )

    url = String(
        label="URL",
        description="Link to the dataset",
        required=True,
        directives=["@index(hash)"],
    )
    doi = String(label="DOI", directives=["@index(hash)"])
    arxiv = String(label="arXiv", directives=["@index(hash)"])
    github = GitHubAuto(
        label="Github",
        description="Github repository",
        render_kw={
            "placeholder": "If the dataset has a repository on Github you can add this here."
        },
        overwrite=True,
        directives=["@index(exact)"],
    )

    description = String(
        large_textfield=True,
        description="Please provide a short description for the dataset",
    )

    conditions_of_access = SingleChoice(
        description="How can the user access this dataset?",
        choices={
            "NA": "NA / Unknown",
            "free": "Free",
            "registration": "Registration Required",
            "request": "Upon Request",
            "purchase": "Purchase",
        },
        queryable=True,
    )

    fulltext_available = Boolean(
        description="does the dataset contain fulltext?", queryable=True
    )

    geographic_scope = MultipleChoice(
        description="What is the geographic scope of the dataset?",
        choices={
            "multinational": "Multinational",
            "national": "National",
            "subnational": "Subnational",
        },
        required=True,
        tom_select=True,
        # radio_field=True,
        queryable=True,
    )

    countries = ListRelationship(
        description="Does the dataset have a specific geographic coverage?",
        relationship_constraint=["Country", "Multinational", "Subnational"],
        autoload_choices=True,
        render_kw={"placeholder": "Select multiple countries..."},
        predicate_alias=["country"],
        queryable=True,
    )

    languages = ListRelationship(
        description="Which languages are covered in the dataset?",
        relationship_constraint=["Language"],
        # tom_select=True,
        render_kw={"placeholder": "Select multiple..."},
        autoload_choices=True,
        queryable=True,
    )

    temporal_coverage_start = DateTime(
        description="Start date of the dataset", directives=["@index(day)"]
    )

    temporal_coverage_end = DateTime(
        description="End date of the dataset", directives=["@index(day)"]
    )

    text_types = ListRelationship(
        description="Text Genres covered by dataset",
        relationship_constraint="TextType",
        # required=True,
        allow_new=True,
        autoload_choices=True,
        queryable=True,
    )

    modalities = ListRelationship(
        description="What type of content is included in the dataset?",
        relationship_constraint="Modality",
        autoload_choices=True,
        allow_new=True,
        queryable=True,
    )

    file_formats = ListRelationship(
        description="In which file format(s) is the dataset stored?",
        autoload_choices=True,
        allow_new=True,
        relationship_constraint="FileFormat",
        render_kw={"placeholder": "Select multiple..."},
    )

    sources_included = ListRelationship(
        relationship_constraint=[
            "NewsSource",
            "Organization",
            "PoliticalParty",
            "Government",
            "Parliament",
            "Person",
        ],
        render_kw={"placeholder": "Select multiple..."},
        queryable=True,
    )

    documentation = ListString(
        description="Is there additional documentation for the dataset? (e.g., codebook, documentation, etc)",
        tom_select=True,
        render_kw={"placeholder": "please paste the URLs to the documentation here!"},
    )

    initial_source = ListRelationship(
        description="If the dataset is derived from another corpus or dataset, the original source can be linked here",
        relationship_constraint=["Dataset"],
        render_kw={"placeholder": "Select multiple..."},
    )

    meta_variables = ListRelationship(
        description="List of meta data included in the dataset (e.g., date, language, source, medium)",
        relationship_constraint="MetaVariable",
        render_kw={"placeholder": "Select multiple..."},
        allow_new=True,
        autoload_choices=True,
        queryable=True,
    )

    concept_variables = ListRelationship(
        description="List of variables based on concepts (e.g. sentiment, frames, etc)",
        relationship_constraint="ConceptVariable",
        render_kw={"placeholder": "Select multiple..."},
        allow_new=True,
        autoload_choices=True,
        queryable=True,
    )

    text_units = ListRelationship(
        description="text segmentation in the resource, what level of text units are available",
        relationship_constraint="UnitOfAnalysis",
        allow_new=True,
        autoload_choices=True,
        queryable=True,
    )

    related_publications = ListRelationship(
        relationship_constraint="ScientificPublication"
    )


class Tool(Entry):
    """Digital resource for implementing a research method (software packages, dictionaries, etc)"""

    name = String(
        description="What is the name of the tool?", required=True, overwrite=False
    )

    alternate_names = ListString(
        description="Does the tool have other names?",
        render_kw={"placeholder": 'Separate by comma ","'},
        overwrite=True,
    )

    authors = AuthorList(
        allow_new=True, relationship_constraint="Author", required=True
    )

    _authors_fallback = OrderedListString(
        delimiter=";", directives=["@index(term)"], edit=False, tom_select=True
    )

    date_published = Year(
        label="Year of publication",
        description="Which year was the tool published?",
        queryable=True,
        directives=["@index(day)"],
        comparison_operators={"ge": "after", "le": "before", "eq": "exact"},
    )

    date_modified = DateTime(
        description="When was the tool last updated?",
        directives=["@index(day)"],
        new=False,
    )

    last_activity = DateTime(
        description="Last time the repository for the tool was modified",
        directives=["@index(day)"],
        new=False,
    )

    version = String(description="Current version of the tool")

    url = String(
        label="URL",
        description="Link to the tool",
        required=True,
        directives=["@index(hash)"],
    )

    doi = String(label="DOI", directives=["@index(exact)"])

    arxiv = String(label="arXiv", directives=["@index(exact)"])

    cran = String(
        label="CRAN",
        description="CRAN Package name",
        render_kw={"placeholder": "usually this is filled in automatically..."},
        directives=["@index(exact)"],
    )

    pypi = String(
        label="PyPi",
        description="PyPi Project name",
        render_kw={"placeholder": "usually this is filled in automatically..."},
        directives=["@index(exact)"],
    )

    github = GitHubAuto(
        label="Github",
        description="Github repository",
        render_kw={
            "placeholder": "If the tool has a repository on Github you can add this here."
        },
        directives=["@index(exact)"],
    )

    description = String(
        large_textfield=True,
        description="Please provide a short description for the tool",
    )

    platforms = MultipleChoice(
        description="For which kind of operating systems is the tool available?",
        choices={"windows": "Windows", "linux": "Linux", "macos": "macOS"},
        tom_select=True,
        queryable=True,
        default=["windows", "linux", "macos"],
    )

    programming_languages = ListRelationship(
        label="Programming Languages",
        description="Which programming languages are used for the tool? \
                                            Please also include language that can directly interface with this tool.",
        required=False,
        relationship_constraint="ProgrammingLanguage",
        tom_select=True,
        queryable=True,
        autoload_choices=True,
    )

    open_source = SingleChoice(
        description="Is this tool open source?",
        choices={"NA": "NA / Unknown", "yes": "Yes", "no": "No, proprietary"},
        queryable=True,
    )

    license = String(description="What kind of license attached to the tool?")

    conditions_of_access = SingleChoice(
        description="How can the user access the tool?",
        choices={
            "NA": "NA / Unknown",
            "free": "Free",
            "registration": "Registration Required",
            "request": "Upon Request",
            "purchase": "Purchase",
        },
        queryable=True,
    )

    used_for = ListRelationship(
        description="Which operations can the tool perform?",
        relationship_constraint="Operation",
        autoload_choices=True,
        allow_new=True,
        required=True,
        predicate_alias=["methodologies"],
        queryable=True,
    )

    concept_variables = ListRelationship(
        description="Which concepts can the tool measure (e.g. sentiment, frames, etc)",
        relationship_constraint="ConceptVariable",
        autoload_choices=True,
        allow_new=True,
        queryable=True,
        query_label="Concept Variables",
    )

    modalities = ListRelationship(
        description="What type of content can be analyzed with the tool?",
        relationship_constraint="Modality",
        autoload_choices=True,
        allow_new=True,
        queryable=True,
    )

    graphical_user_interface = Boolean(
        description="Does the tool have a graphical user interface?",
        label="Yes, it does have a GUI",
        default=False,
        queryable=True,
    )

    designed_for = ListRelationship(
        description="Is the tool designed for a specific entity?",
        autoload_choices=False,
        queryable=True,
        relationship_constraint=[
            "Channel",
            "Dataset",
            "PoliticalParty",
            "Organization",
            "Government",
            "Parliament",
            "Person",
        ],
    )

    language_independent = Boolean(
        description="Is the tool language independent?", label="Yes", queryable=True
    )

    languages = ListRelationship(
        description="Which languages does the tool support?",
        tom_select=True,
        relationship_constraint="Language",
        queryable=True,
        autoload_choices=True,
    )

    input_file_format = ListRelationship(
        description="Which file formats does the tool take as input?",
        autoload_choices=True,
        relationship_constraint="FileFormat",
        allow_new=True,
        queryable=True,
    )

    output_file_format = ListRelationship(
        description="Which file formats does the tool output?",
        autoload_choices=True,
        relationship_constraint="FileFormat",
        allow_new=True,
        queryable=True,
    )

    author_validated = SingleChoice(
        description="Do the authors of the tool report any validation?",
        choices={"NA": "NA / Unknown", "yes": "Yes", "no": "No, not reported"},
        queryable=True,
    )

    validation_dataset = ListRelationship(
        description="Which corpus or dataset was used to validate the tool?",
        autoload_choices=True,
        relationship_constraint="Dataset",
        queryable=True,
    )

    documentation = ListString(
        description="Is there additional documentation for the tool? (e.g., FAQ, Tutorials, Website, etc)",
        tom_select=True,
        render_kw={"placeholder": "please paste the URLs to the documentation here!"},
    )

    materials = ReverseListRelationship(
        "tools", description="Learning materials related to the tool", tom_select=True
    )

    related_publications = ReverseListRelationship(
        "tools",
        description="Which research publications are using this tool?",
        autoload_choices=True,
        new=False,
        relationship_constraint="ScientificPublication",
    )

    defunct = Boolean(description="Is the tool defunct?", queryable=True)


class ScientificPublication(Entry):
    """Research output; scholarly documents like journal articles, books, and theses."""

    name = String(new=False, edit=False, hidden=True, overwrite=False)
    alternate_names = ListString(new=False, edit=False, hidden=True, required=False)

    title = String(
        description="What is the title of the publication?",
        required=True,
        directives=["@index(term)"],
    )

    authors = AuthorList(
        allow_new=True, relationship_constraint="Author", required=True
    )

    _authors_fallback = OrderedListString(
        delimiter=";", directives=["@index(term)"], edit=False, tom_select=True
    )

    date_published = Year(
        label="Year of publication",
        description="Which year was the publication published?",
        directives=["@index(day)"],
        required=True,
    )

    paper_kind = SingleChoice(
        description="What kind of publication is this?",
        required=True,
        choices={
            "journal-article": "Journal Article",
            "book": "Book",
            "dataset": "Dataset",
            "book-chapter": "Book Chapter",
            "book-part": "Part",
            "book-section": "Book Section",
            "book-series": "Book Series",
            "book-set": "Book Set",
            "book-track": "Book Track",
            "component": "Component",
            "database": "Database",
            "dissertation": "Dissertation",
            "edited-book": "Edited Book",
            "grant": "Grant",
            "journal": "Journal",
            "journal-issue": "Journal Issue",
            "journal-volume": "Journal Volume",
            "monograph": "Monograph",
            "peer-review": "Peer Review",
            "posted-content": "Posted Content",
            "proceedings": "Proceedings",
            "proceedings-article": "Proceedings Article",
            "proceedings-series": "Proceedings Series",
            "reference-book": "Reference Book",
            "reference-entry": "Reference Entry",
            "report": "Report",
            "report-component": "Report Component",
            "report-series": "Report Series",
            "standard": "Standard",
            "other": "Other",
        },
    )

    venue = String(
        description="In which journal/proceedings was it published?",
        directives=["@index(term, trigram)"],
    )

    url = String(
        label="URL",
        description="Link to the publication",
        required=True,
        directives=["@index(hash)"],
    )
    doi = String(label="DOI", directives=["@index(hash)"])
    openalex = ListString(label="OpenAlex ID", directives=["@index(hash)"])
    arxiv = String(label="arXiv", directives=["@index(hash)"])

    description = String(
        large_textfield=True,
        description="Abstract or a short description of the publication",
    )

    tools = ListRelationship(
        description="Which research tool(s) where used in the publication?",
        relationship_constraint="Tool",
    )

    methodologies = ListRelationship(
        description="Methodologies / Operations used in the publication",
        relationship_constraint="Operation",
        autoload_choices=True,
        queryable=True,
        predicate_alias=["used_for"],
        allow_new=True,
    )

    concept_variables = ListRelationship(
        description="concepts investigated in this publication",
        relationship_constraint="ConceptVariable",
        allow_new=True,
        queryable=True,
        autoload_choices=True,
    )

    sources_included = ListRelationship(
        description="Which entities are covered in the publication",
        autoload_choices=False,
        queryable=True,
        relationship_constraint=[
            "NewsSource",
            "Organization",
            "PoliticalParty",
            "Person",
            "Government",
            "Parliament",
        ],
    )

    modalities = ListRelationship(
        description="Does the publication focus on a specific modality?",
        relationship_constraint="Modality",
        autoload_choices=True,
        allow_new=True,
        queryable=True,
    )

    text_types = ListRelationship(
        description="Text Genres investigated in publication",
        relationship_constraint="TextType",
        #  required=True,
        autoload_choices=True,
        queryable=True,
    )

    text_units = ListRelationship(
        description="List of text units analysed in the publication (e.g., sentences, paragraphs, tweets, news articles, summaries, headlines)",
        relationship_constraint="UnitOfAnalysis",
        queryable=True,
        render_kw={"placeholder": "Select multiple..."},
        autoload_choices=True,
        allow_new=True,
    )

    datasets_used = ListRelationship(
        description="Which dataset(s) where used in the publication?",
        autoload_choices=True,
        queryable=True,
        relationship_constraint="Dataset",
    )

    countries = ListRelationship(
        description="Does the publication has some sort of countries that it focuses on?",
        autoload_choices=True,
        queryable=True,
        predicate_alias=["country"],
        relationship_constraint=["Country", "Multinational"],
    )

    channels = ListRelationship(
        description="Does the publication investigate specific channels?",
        autoload_choices=True,
        queryable=True,
        relationship_constraint="Channel",
    )

    geographic_scope = MultipleChoice(
        description="What is the geographic scope of the publication?",
        choices={
            "multinational": "Multinational",
            "national": "National",
            "subnational": "Subnational",
        },
        required=True,
        tom_select=True,
        # radio_field=True,
        queryable=True,
    )

    languages = ListRelationship(
        autoload_choices=True, queryable=True, relationship_constraint="Language"
    )


"""
    Authors
"""


class Author(Entry):
    """Authors are people who create datasets, archives, tools or scientific publications."""

    orcid = ORCID(label="ORCID", directives=["@index(hash)"])
    url = String(
        label="URL", description="Website of author", directives=["@index(hash)"]
    )
    openalex = ListString(
        label="OpenAlex ID", description="ID(s) of the author on OpenAlex"
    )

    # last_known_institution = String(description="Affiliation of author")
    affiliations = ListString(description="Affiliations of author")

    given_name = String(new=False)
    family_name = String(new=False)


"""
    Meta Predicates / Tag Like Types
"""


class Language(Entry):
    """Written Language"""

    iso_639_2 = String(
        label="ISO-639-2 Code",
        description="ISO code with 2 characters (e.g. 'en')",
        directives=["@index(exact)"],
    )

    iso_639_3 = String(
        label="ISO-639-3 Code",
        description="ISO code with 3 characters (e.g. 'eng')",
        directives=["@index(exact)"],
    )

    icu_code = String(
        label="ICU Locale Code",
        description="ICU locale for scripts (e.g. 'en_GB', 'zh_Hans')",
        directives=["@index(exact)"],
    )


class ProgrammingLanguage(Entry):
    """a system of notation for writing computer programs"""

    pass


class Operation(Entry):
    """
    Methodology, technique or action that is used/presented in a Scientific Publication,
    or that has been used to produce a Dataset, or that can be performed with a Tool.
    Operations cover both actual text analysis methodologies (as abstract as
    supervised classification) and techniques (like random forests or clustering),
    and more specific actions often conducted as preparation or alongside scietific
    analyses (e.g., stop word removal, n-gram extraction or key-word in context).
    """

    pass


class FileFormat(Entry):
    """File type and format used to store a resource"""

    mime_type = String(label="MIME type")


class MetaVariable(Entry):
    """
    Meta variables as provided in resources, they are exogenous:
    e.g., party, publication date, page number, or section.
    """

    pass


class ConceptVariable(Entry):
    """
    Concept variables are measurements of theoretical constructs,
    such as sentiment, populism, or toxic language.
    Unlike meta variables, concept variables may not be directly compatible with each other.
    """

    pass


class TextType(Entry):
    """
    Genre of text such as parliamentary debates,
    speeches, Tweets, news articles, manifestos
    """

    pass


class UnitOfAnalysis(Entry):
    """
    "Decontextualized but information-bearing textual wholes that
    are distinguished within an otherwise undifferentiated continuum
    and thereafter considered separate from their context and independent
    of each other" (Krippendorff, 2018).
    E.g., pargarphs, sentences, images, tweets
    """

    pass


class Modality(Entry):
    """
    Modality refers to the interdisciplinary study of how people communicate and interact in
    social settings by analyzing various semiotic resources beyond traditional language,
    such as text, images, sound, video (or even typography, color, gesture, and more).
    It encompasses both a theoretical framework in social semiotics and a broader exploration
    of the ways in which individuals create meaning through the combination of different modes of
    communication in various contexts. (see: Poulsen, 2015)
    """


"""
    Collections / User Curated Entries
"""


class Collection(Entry):
    """
    A user created collection of entries.
    """

    name = String(
        required=True, description="How do you want to call your new collection?"
    )

    alternate_names = ListString(description="Other names for your collection?")

    description = String(
        large_textfield=True,
        description="Please provide a brief description for your collection",
    )

    entries_included = ListRelationship(
        description="What are the entries that you want to include in this collection?",
        autoload_choices=False,
        queryable=True,
        relationship_constraint=[
            "Dataset",
            "Archive",
            "NewsSource",
            "JournalisticBrand",
            "Government",
            "Parliament",
            "Person",
            "PoliticalParty",
            "Organization",
        ],
    )

    languages = ListRelationship(
        description="Which languages are related to this collection?",
        relationship_constraint=["Language"],
        queryable=True,
        autoload_choices=True,
    )

    countries = ListRelationship(
        description="Which countries, or multinational constructs are related to this collection?",
        queryable=True,
        predicate_alias=["country"],
        relationship_constraint=["Country", "Multinational"],
    )

    subnational_scope = SubunitAutocode(
        label="Subunits",
        description="Which subnational entities are related to this collection?",
        tom_select=True,
        queryable=True,
    )

    tools = ListRelationship(
        description="Which tools are related to this collection?",
        relationship_constraint=["Tool"],
    )

    references = ListRelationship(
        description="Is the collection is directly related to a paper, or derived from a series of papers / publications?",
        relationship_constraint=["ScientificPublication"],
    )

    materials = ListRelationship(
        description="Are there any learning materials related to this collection?",
        relationship_constraint=["LearningMaterial"],
    )

    concept_variables = ListRelationship(
        description="Is this collection about concepts or related to theoretical constructs?",
        relationship_constraint=["ConceptVariable"],
        autoload_choices=True,
        allow_new=True,
    )

    modalities = ListRelationship(
        description="Does the collection for any specific modality?",
        relationship_constraint="Modality",
        autoload_choices=True,
        allow_new=True,
        queryable=True,
    )


class LearningMaterial(Entry):
    """
    A reference to a learning resource. Teaches how to perform text analysis,
    work with specific datasets, deal with specific languages and so forth.
    """

    urls = ListString(required=True, directives=["@index(hash)"])

    authors = AuthorList(
        allow_new=True, queryable=True, relationship_constraint="Author"
    )

    concept_variables = ListRelationship(
        description="Is this learning material about concepts or related to theoretical constructs?",
        queryable=True,
        relationship_constraint=["ConceptVariable"],
        autoload_choices=True,
        allow_new=True,
    )

    methodologies = ListRelationship(
        description="Methodologies / Operations discussed in the learning material",
        queryable=True,
        relationship_constraint="Operation",
        allow_new=True,
        predicate_alias=["used_for"],
        autoload_choices=True,
    )

    tools = ListRelationship(
        description="Which tools are related to this learning material?",
        relationship_constraint=["Tool"],
    )

    datasets_used = ListRelationship(
        description="Does the learning material use a specific dataset?",
        relationship_constraint="Dataset",
    )

    languages = ListRelationship(
        description="Does the learning material focus on a specific language?",
        relationship_constraint="Language",
        tom_select=True,
        queryable=True,
        autoload_choices=True,
    )

    programming_languages = ListRelationship(
        label="Programming Languages",
        description="Is the learning material for a specific programming language?",
        required=False,
        relationship_constraint="ProgrammingLanguage",
        tom_select=True,
        queryable=True,
        autoload_choices=True,
    )

    channels = ListRelationship(
        description="Is the learning material covering specific channels?",
        autoload_choices=True,
        queryable=True,
        relationship_constraint="Channel",
    )

    text_types = ListRelationship(
        description="Text Genres covered by this learning material",
        relationship_constraint="TextType",
        autoload_choices=True,
        queryable=True,
    )

    modalities = ListRelationship(
        description="Does the learning material cover specific modalities?",
        relationship_constraint="Modality",
        autoload_choices=True,
        queryable=True,
    )


"""
    System Types
"""


class File(Schema):
    __permission_new__ = 99
    __permission_edit__ = 99
    __private__ = True

    uid = UIDPredicate()

    _download_url = String(
        description="location of the resource", edit=False, directives=["@index(hash)"]
    )
    _path = String(
        description="location on local disk", edit=False, directives=["@index(hash)"]
    )
    file_formats = SingleRelationship(relationship_constraint="FileFormat", edit=False)


class Notification(Schema):
    __permission_new__ = 99
    __permission_edit__ = 99
    __private__ = True

    uid = UIDPredicate()

    _notification_date = DateTime(
        default=datetime.datetime.now, directives=["@index(hour)"], edit=False
    )
    _read = Boolean(default=False, edit=False)
    _notify = SingleRelationship(
        relationship_constraint="User", required=True, edit=False
    )

    _title = String(default="Notification", edit=False)
    _content = String(edit=False)
    _linked = SingleRelationship(
        edit=False,
        description="Entries that are linked to this notification",
        relationship_constraint=["Entry"],
    )
    _email_dispatched = Boolean(default=False, edit=False)


class Comment(Schema):
    __permission_new__ = USER_ROLES.Contributor
    __permission_edit__ = USER_ROLES.Contributor
    __private__ = True

    uid = UIDPredicate()

    _creator = SingleRelationship(
        relationship_constraint="User", required=True, edit=False
    )

    _comment_date = DateTime(
        default=datetime.datetime.now, directives=["@index(hour)"], edit=False
    )

    _comment_edited = DateTime(
        default=datetime.datetime.now, directives=["@index(hour)"], edit=False
    )

    _comment_on = SingleRelationship(
        relationship_constraint="Entry", required=True, edit=False
    )
    content = String()


class Rejected(Schema):
    """Represent entries that were rejected by reviewers"""

    __permission_new__ = 99
    __permission_edit__ = 99
    __private__ = True

    uid = UIDPredicate()

    _date_created = DateTime(directives=["@index(hour)"])
    _date_modified = DateTime(directives=["@index(hour)"])

    _added_by = SingleRelationship(
        label="Added by",
        relationship_constraint="User",
        new=False,
        edit=False,
        read_only=True,
        hidden=True,
    )

    _reviewed_by = SingleRelationship(
        label="Reviewed by",
        relationship_constraint="User",
        new=False,
        edit=False,
        read_only=True,
        hidden=True,
    )

    _edited_by = SingleRelationship(
        label="Edited by",
        relationship_constraint="User",
        new=False,
        edit=False,
        read_only=True,
        hidden=True,
    )

    _former_types = ListString(edit=False)

    entry_review_status = String(default="rejected")


class _JWT(Schema):
    """Block List of revoked tokens"""

    __permission_new__ = 99
    __permission_edit__ = 99
    __private__ = True

    uid = UIDPredicate()
    _jti = String(directives=["@index(hash)"], overwrite=False)
    _token_type = String(directives=["@index(hash)"], overwrite=False)
    _revoked_timestamp = DateTime(directives=["@index(hour)"])
