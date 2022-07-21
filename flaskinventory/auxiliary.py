icu_codes = {'af': 'Afrikaans',
             'ak': 'Akan',
             'sq': 'Albanian',
             'am': 'Amharic',
             'ar': 'Arabic',
             'hy': 'Armenian',
             'as': 'Assamese',
             'ast': 'Asturian', 
             'az': 'Azerbaijani',
             'ay': 'Aymara ',
             'bm': 'Bambara',
             'eu': 'Basque',
             'be': 'Belarusian',
             'bn': 'Bengali',
             'bs': 'Bosnian',
             'br': 'Breton',
             'bg': 'Bulgarian',
             'my': 'Burmese',
             'ca': 'Catalan',
             'zh_Hans': 'Chinese (Simplified)',
             'zh_Hant': 'Chinese (Traditional)',
             'kw': 'Cornish',
             'co': 'Corsican',
             'hr': 'Croatian',
             'cs': 'Czech',
             'da': 'Danish',
             'nl': 'Dutch',
             'dz': 'Dzongkha',
             'en': 'English',
             'eo': 'Esperanto',
             'et': 'Estonian',
             'ee': 'Ewe',
             'fo': 'Faroese',
             'fi': 'Finnish',
             'fr': 'French',
             'ff': 'Fulah',
             'gl': 'Galician',
             'lg': 'Ganda',
             'ka': 'Georgian',
             'de': 'German',
             'el': 'Greek',
             'grc': 'Greek (Ancient)',
             'gu': 'Gujarati',
             'ha': 'Hausa',
             'ht': 'Haitian',
             'he': 'Hebrew',
             'hi': 'Hindi',
             'hu': 'Hungarian',
             'is': 'Icelandic',
             'ig': 'Igbo',
             'ilo': 'Iloko',
             'id': 'Indonesian',
             'iu': 'Inuktitut',
             'ga': 'Irish',
             'it': 'Italian',
             'ja': 'Japanese',
             'jv': 'Javanese',
             'kl': 'Kalaallisut',
             'kn': 'Kannada',
             'ks': 'Kashmiri',
             'kk': 'Kazakh',
             'xnz': 'Kenzi (Nubian)',
             'km': 'Khmer',
             'ki': 'Kikuyu',
             'rw': 'Kinyarwanda',
             'ku': 'Kurdish',
             'ko': 'Korean',
             'ky': 'Kyrgyz',
             'la': 'Latin',
             'lo': 'Lao',
             'lv': 'Latvian',
             'ln': 'Lingala',
             'lt': 'Lithuanian',
             'lu': 'Luba-Katanga',
             'lb': 'Luxembourgish',
             'mi': 'Maori',
             'mk': 'Macedonian',
             'mg': 'Malagasy',
             'ms': 'Malay',
             'ml': 'Malayalam',
             'mt': 'Maltese',
             'gv': 'Manx',
             'mr': 'Marathi',
             'mn': 'Mongolian',
             'ne': 'Nepali',
             'nd': 'North Ndebele',
             'se': 'Northern Sami',
             'no': 'Norwegian',
             'nb': 'Norwegian Bokmål',
             'nn': 'Norwegian Nynorsk',
             'ny': 'Chichewa (Nyanja)',
             'oc': 'Occitan (post 1500)',
             'or': 'Oriya',
             'om': 'Oromo',
             'os': 'Ossetic',
             'pam': 'Pampanga',
             'ps': 'Pashto',
             'fa': 'Persian',
             'pl': 'Polish',
             'pt': 'Portuguese',
             'pa': 'Punjabi',
             'qu': 'Quechua',
             'ro': 'Romanian',
             'rm': 'Romansh',
             'rn': 'Rundi',
             'ru': 'Russian',
             'sg': 'Sango',
             'sa': 'Sanskrit',
             'sat': 'Santali',
             'sc': 'Sardinian',
             'sco': 'Scots',
             'gd': 'Scottish Gaelic',
             'sr': 'Serbian',
             'sh': 'Serbo-Croatian',
             'sn': 'Shona',
             'ii': 'Sichuan Yi',
             'scn': 'Sicilian',
             'sd': 'Sindhi',
             'si': 'Sinhala',
             'sk': 'Slovak',
             'sl': 'Slovenian',
             'so': 'Somali',
             'st': 'Sotho, Southern',
             'es': 'Spanish',
             'su': 'Sundanese',
             'sw': 'Swahili',
             'sv': 'Swedish',
             'tl': 'Tagalog',
             'tg': 'Tajik',
             'ta': 'Tamil',
             'tt': 'Tatar',
             'te': 'Telugu',
             'tdt': 'Tetum',
             'th': 'Thai',
             'bo': 'Tibetan',
             'ti': 'Tigrinya',
             'to': 'Tongan',
             'tr': 'Turkish',
             'tk': 'Turkmen',
             'tn': 'Setswana',
             'uk': 'Ukrainian',
             'hsb': 'Upper Sorbian',
             'ur': 'Urdu',
             'ug': 'Uyghur',
             'uz': 'Uzbek',
             'vi': 'Vietnamese',
             'war': 'Waray',	
             'wa': 'Walloon',
             'cy': 'Welsh',
             'fy': 'Western Frisian',
             'sah': 'Yakut',
             'yi': 'Yiddish',
             'yo': 'Yoruba',
             'zu': 'Zulu'}

icu_codes_list = [{'code': key, 'name': val} for key, val in icu_codes.items()]

icu_codes_list_tuples = [(key, val) for key, val in icu_codes.items()]

programming_languages = {'apl': 'APL',
                         'assembly': 'Assembly',
                         'bash_shell': 'Bash/Shell',
                         'c': 'C',
                         'c_sharp': 'C#',
                         'c_plusplus': 'C++',
                         'cobol': 'COBOL',
                         'clojure': 'Clojure',
                         'crystal': 'Crystal',
                         'dart': 'Dart',
                         'delphi': 'Delphi',
                         'elixir': 'Elixir',
                         'erlang': 'Erlang',
                         'f_sharp': 'F#',
                         'golang': 'Go',
                         'groovy': 'Groovy',
                         'haskell': 'Haskell',
                         'java': 'Java',
                         'javascript': 'JavaScript',
                         'julia': 'Julia',
                         'kotlin': 'Kotlin',
                         'lisp': 'LISP',
                         'matlab': 'Matlab',
                         'node_js': 'Node.js',
                         'objective_c': 'Objective-C',
                         'php': 'PHP',
                         'perl': 'Perl',
                         'powershell': 'PowerShell',
                         'python': 'Python',
                         'r': 'R',
                         'ruby': 'Ruby',
                         'rust': 'Rust',
                         'sql': 'SQL',
                         'scala': 'Scala',
                         'swift': 'Swift',
                         'stata': 'Stata Script (Ado)',
                         'typescript': 'TypeScript',
                         'vba': 'VBA'}

licenses = {'proprietary': 'Proprietary (any kind of non-free EULA)',
            'afl-3.0': 'Academic Free License v3.0', 
            'apache-2.0': 'Apache license 2.0', 
            'artistic-2.0': 'Artistic license 2.0', 
            'bsl-1.0': 'Boost Software License 1.0', 
            'bsd-2-clause': 'BSD 2-clause "Simplified" license', 
            'bsd-3-clause': 'BSD 3-clause "New" or "Revised" license', 
            'bsd-3-clause-clear': 'BSD 3-clause Clear license', 
            'cc': 'Creative Commons license family', 
            'cc0-1.0': 'Creative Commons Zero v1.0 Universal', 
            'cc-by-4.0': 'Creative Commons Attribution 4.0', 
            'cc-by-sa-4.0': 'Creative Commons Attribution Share Alike 4.0', 
            'wtfpl': 'Do What The F*ck You Want To Public License', 
            'ecl-2.0': 'Educational Community License v2.0', 
            'epl-1.0': 'Eclipse Public License 1.0', 
            'epl-2.0': 'Eclipse Public License 2.0', 
            'eupl-1.1': 'European Union Public License 1.1', 
            'agpl-3.0': 'GNU Affero General Public License v3.0', 
            'gpl': 'GNU General Public License family', 
            'gpl-2.0': 'GNU General Public License v2.0', 
            'gpl-3.0': 'GNU General Public License v3.0', 
            'lgpl': 'GNU Lesser General Public License family', 
            'lgpl-2.1': 'GNU Lesser General Public License v2.1', 
            'lgpl-3.0': 'GNU Lesser General Public License v3.0', 
            'isc': 'ISC', 
            'lppl-1.3c': 'LaTeX Project Public License v1.3c', 
            'ms-pl': 'Microsoft Public License', 
            'mit': 'MIT', 
            'mpl-2.0': 'Mozilla Public License 2.0', 
            'osl-3.0': 'Open Software License 3.0', 
            'postgresql': 'PostgreSQL License', 
            'ofl-1.1': 'SIL Open Font License 1.1', 
            'ncsa': 'University of Illinois/NCSA Open Source License', 
            'unlicense': 'The Unlicense', 
            'zlib': 'zLib License',
            'na': 'NA (license not specified)'
    }
