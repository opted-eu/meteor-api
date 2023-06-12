const doi_regex = new RegExp("^10.\\d{4,9}\/[-._;()/:A-Z0-9]+$", "i")


function fetchMetaData(button) {

    document.getElementById('magic-platform').classList.remove('is-invalid')
    document.getElementById('magic-identifier').classList.remove('is-invalid')

    var platform = document.getElementById('magic-platform').value

    if (!platform || platform == 'choose...') {
        document.getElementById('magic-platform').classList.add('is-invalid')
        buttonWarning(button, message = "Magic")
        return false
    }

    var identifier = document.getElementById('magic-identifier').value.trim()

    if (!identifier) {
        document.getElementById('magic-identifier').classList.add('is-invalid')
        return false
    }

    // clear form
    document.getElementById('form-add-new').reset()
    for (e of document.getElementsByTagName('input')) { if (e.tomselect) { e.tomselect.clear() } }
    for (e of document.getElementsByTagName('select')) { if (e.tomselect) { e.tomselect.clear() } }

    showSpinner(button)
    let container = document.getElementById('magic-warning-container')
    container.hidden = true

    if (platform == 'doi') {

        // sanitize identifier string

        doi = identifier.replace("https://doi.org/", "")
        doi = doi.replace("http://doi.org/", "")
        doi = doi.replace("doi.org/", "")

        if (!doi_regex.test(doi)) {
            hideSpinner(button)
            buttonWarning(button, message = "DOI Invalid!")
            return false
        }

        // check if already in inventory
        fetch($SCRIPT_ROOT + '/endpoint/lookup?predicate=doi&query=' + doi)
            .then(response => response.json())
            .then(result => checkInventory(result))

        let api = "https://api.openalex.org/works/doi:"

        fetch(api + doi)
            .then(response => response.json())
            .then(json => parseDOI(json))
            .then(result => fillForm(result))
            .then(_ => hideSpinner(button), buttonSuccess(button))
            .catch(error => handleError(error, button))

    } else if (platform == 'arxiv') {

        // sanitize identifier string
        arxiv = identifier.replace('https://arxiv.org/abs/', '')
        arxiv = arxiv.replace('http://arxiv.org/abs/', '')
        arxiv = arxiv.replace('arxiv.org/abs/', '')
        arxiv = arxiv.replace('abs/', '')

        // check if already in inventory
        fetch($SCRIPT_ROOT + '/endpoint/identifier/lookup?arxiv=' + arxiv)
            .then(response => response.json())
            .then(result => checkInventory(result))

        let api = "https://export.arxiv.org/api/query?id_list="

        fetch(api + arxiv)
            .then(response => response.text())
            .then(xml => parseArXiv(xml))
            .then(result => fillForm(result))
            .then(_ => hideSpinner(button), buttonSuccess(button))
            .catch(error => handleError(error, button))

    } else if (platform == 'cran') {

        // sanitize identifier string
        cran = identifier.replace('https://cran.r-project.org/web/packages/', '')
        cran = cran.replace('http://cran.r-project.org/web/packages/', '')
        cran = cran.replace('/index.html', '')
        cran = cran.replace('https://CRAN.R-project.org/package=', '')
        cran = cran.replace('https://cran.r-project.org/package=', '')

        // check if already in inventory
        fetch($SCRIPT_ROOT + '/endpoint/identifier/lookup?cran=' + cran)
            .then(response => response.json())
            .then(result => checkInventory(result))

        let api = $SCRIPT_ROOT + '/endpoint/cran?package='

        fetch(api + cran)
            .then(response => response.json())
            .then(result => fillForm(result))
            .then(_ => hideSpinner(button), buttonSuccess(button))
            .catch(error => handleError(error, button))

    } else if (platform == 'python') {

        pypi = identifier.replace("https://pypi.org/project/", "")
        pypi = pypi.replace('http://pypi.org/project/', '')
        pypi = pypi.replace('pypi.org/project/', '')
        pypi = pypi.replace('project/', '')

        // check if already in inventory
        fetch($SCRIPT_ROOT + '/endpoint/identifier/lookup?pypi=' + pypi)
            .then(response => response.json())
            .then(result => checkInventory(result))

        let api = "https://pypi.org/pypi/"

        fetch(api + pypi + '/json')
            .then(response => response.json())
            .then(json => parsePyPi(json))
            .then(result => fillForm(result))
            .then(_ => hideSpinner(button), buttonSuccess(button))
            .catch(error => handleError(error, button))

    } else if (platform == 'github') {
        let api = "https://api.github.com/repos/"

        // sanitize identifier string
        github = identifier.replace('https://www.github.com/', '')
        github = github.replace('http://www.github.com/', '')
        github = github.replace('www.github.com/', '')
        github = github.replace('https://github.com/', '')
        github = github.replace('http://github.com/', '')
        github = github.replace('github.com/', '')

        // check if already in inventory
        fetch($SCRIPT_ROOT + '/endpoint/identifier/lookup?github=' + github)
            .then(response => response.json())
            .then(result => checkInventory(result))

        fetch(api + github)
            .then(response => response.json())
            .then(json => parseGithub(json))
            .then(result => fillForm(result))
            .then(_ => hideSpinner(button), buttonSuccess(button))
            .catch(error => handleError(error, button))
    }

};

function checkInventory(data) {
    let container = document.getElementById('magic-warning-container')
    let button = document.getElementById('magic')
    if (data.status) {
        let identifier = data.data[0].doi
        if (!identifier) {
            identifier = data.data[0].arxiv
        }
        if (!identifier) {
            identifier = data.data[0].pypi
        }
        if (!identifier) {
            identifier = data.data[0].cran
        }
        container.getElementsByTagName('p')[0].innerHTML = `This entry is already in the inventory! 
            You can find it by entering the identifier "${identifier}" in the search box above`
        container.hidden = false
        buttonWarning(button, 'Warning!')
    } else {
        container.hidden = true
    }
}

function fillForm(data) {
    for (let key in data) {
        let field = document.getElementById(key)
        if (field) {
            if (field.multiple) {
                if (field.tomselect) {
                    field.tomselect.addOptions(data[key])
                    data[key].forEach(v => field.tomselect.addItem(v.uid))
                } else {
                for (let v of data[key]) {
                    if (document.querySelector(`#${field.id} option[value="${v}"]`)) {
                        document.querySelector(`#${field.id} option[value="${v}"]`).selected = true
                    } 
                }
                }
            } else {
                field.value = data[key]
            }
            if (field.tomselect) {
                field.tomselect.sync()
            };
        };
    };
};

function showSpinner(button) {
    button.classList = ['btn btn-primary w-100']
    button.getElementsByClassName('spinner-grow')[0].hidden = false
    button.getElementsByClassName('button-loading')[0].hidden = false
    button.getElementsByClassName('button-text')[0].hidden = true
    document.getElementById('magic-wand').hidden = true
}


function hideSpinner(button) {
    button.getElementsByClassName('spinner-grow')[0].hidden = true
    button.getElementsByClassName('button-loading')[0].hidden = true
    button.getElementsByClassName('button-text')[0].hidden = false
    document.getElementById('magic-wand').hidden = false
    document.getElementById('magic-error-container').hidden = true

}

function handleError(error, button) {
    button.classList = ['btn btn-danger w-100']
    button.getElementsByClassName('spinner-grow')[0].hidden = true
    button.getElementsByClassName('button-loading')[0].hidden = true
    button.getElementsByClassName('button-text')[0].hidden = false
    button.getElementsByClassName('button-text')[0].innerText = 'Error!'
    document.getElementById('magic-error-container').hidden = false
    console.error(error)
}

function buttonSuccess(button) {
    button.classList = ['btn btn-success w-100']
    button.getElementsByClassName('button-text')[0].innerText = 'Success!'
    document.getElementById('magic-error-container').hidden = true
}

function buttonWarning(button, message = "Invalid Identifier!") {
    button.classList = ['btn btn-warning w-100']
    button.getElementsByClassName('spinner-grow')[0].hidden = true
    button.getElementsByClassName('button-loading')[0].hidden = true
    button.getElementsByClassName('button-text')[0].hidden = false
    button.getElementsByClassName('button-text')[0].innerText = message
}

function parseDOI(json) {

    result = new Array

    // if (headers.get('Content-Type').includes('csl+json')) {

    if (json.primary_location?.landing_page_url) {
        result['url'] = json.primary_location.landing_page_url
    } else {
        result['url'] = json.ids.doi
    }

    result['doi'] = json.ids.doi.replace('https://doi.org/', '')
    result['venue'] = json.primary_location?.source?.display_name

    result['name'] = json.title

    result['title'] = result['name']

    result['paper_kind'] = json['type']

    result['date_published'] = json.publication_year

    result['authors'] = []

    for (let author of json.authorships) {
        parsed_author = new Object
        parsed_author['openalex'] = author.author.id.replace('https://openalex.org/', '')
        parsed_author['uid'] = parsed_author['openalex']
        parsed_author['name'] = author.author.display_name

        result['authors'].push(parsed_author)
    }

    if (Object.keys(json).includes('abstract')) {
        result['description'] = json.abstract
    } else {
        result['description'] = Object.keys(json.abstract_inverted_index).join(" ")
    }

    console.debug(result)

    // }
    // other parser here

    return result

}


function parseArXiv(xml) {

    
    let parser = new DOMParser()
    
    let publication = parser.parseFromString(xml, 'text/xml')

    let total_result = publication.getElementsByTagName('opensearch:totalResults')[0].innerHTML
    if (!total_result) {
        total_result = publication.getElementsByTagName('opensearch:totalresults')[0].innerHTML
    }

    if (parseInt(total_result) < 1) {
        return false
    }

    publication = publication.getElementsByTagName('entry')[0]

    let result = new Array()

    result['arxiv'] = publication.getElementsByTagName('id')[0].innerHTML

    result['url'] = result['arxiv']

    result['arxiv'] = result['arxiv'].replace('http://arxiv.org/abs/', '').replace('https://arxiv.org/abs/', '')

    fetch($SCRIPT_ROOT + '/endpoint/identifier/lookup?arxiv=' + result['arxiv'])
        .then(response => response.json())
        .then(result => checkInventory(result))

    result['name'] = publication.getElementsByTagName('title')[0].innerHTML

    result['title'] = result['name']

    let authors = []

    for (author of publication.getElementsByTagName('author')) {
        let author_raw = author.getElementsByTagName('name')[0].innerHTML
        author_raw = author_raw.split(' ')
        author_name = author_raw.pop() + ', ' + author_raw.join(" ")
        authors.push(author_name)
    }
    result['authors'] = authors.join(';')

    result['date_published'] = publication.getElementsByTagName('published')[0].innerHTML.split('-')[0]

    result['description'] = publication.getElementsByTagName('summary')[0].innerHTML.trim()

    return result
}

function parsePyPi(package) {

    let github_regex = new RegExp("https?://github\.com/(.*)")

    result = new Array()

    result['name'] = package.info['name']
    result['pypi'] = package.info['name']
    result['title'] = package.info['name']
    result['alternate_names'] = package.info['summary']
    result['description'] = package.info['description']
    result['url'] = package.info['home_page']
    result['authors'] = package.info['author']
    result['license'] = package.info['license']
    result['documentation'] = []
    for (url in package.info['project_urls']) {
        let material_url = package.info.project_urls[url]
        if (material_url.match(github_regex)) {
            let github = material_url.match(github_regex)[1]
            if (github.endsWith('/issues')) {
                github.replace('/issues', '')
            }
            result['github'] = github
        } else {
            result['documentation'].push(material_url)
        }
    }

    result['programming_languages'] = ['python']
    result['platform'] = ['windows', 'linux', 'macos']
    result['open_source'] = ['yes']
    result['conditions_of_access'] = ['free']
    return result
}


function parseGithub(package) {

    result = new Array()

    result['name'] = package['name']
    result['github'] = package['full_name']
    result['title'] = package['name']
    if ('home_page' in package) {
        result['url'] = package['home_page']
    } else {
        result['url'] = 'https://github.com/' + package['full_name']
    }
    if (package.license != null) {
        result['license'] = package.license['name']
    }
    if ('created_at' in package) {
        let year = package.created_at.split('-')[0]
        if (parseInt(year)) {
            result['date_published'] = year
        }
    }

    if ('language' in package) {
        result['programming_languages'] = [package.language.toLowerCase()]
    }
    result['open_source'] = ['yes']
    result['conditions_of_access'] = ['free']
    return result
}