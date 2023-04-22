import sys
import json
import pydgraph
from colorama import init, deinit, Fore, Style

def main():
    init()
    print(Fore.RED + 'WARNING!' + Style.RESET_ALL + " You are about to bulk insert test data.")
    user_warning = input('Are you sure you want to proceed? (y/n): ')
    
    if user_warning.lower() != 'y':
        print('Aborted')
        sys.exit()
    
    # load sample_data
    with open('./data/sample_data.rdf', 'r') as f:
        sample_data = [line.strip() for line in f]

    # skip first two lines and last line
    sample_data = sample_data[2:]
    sample_data = sample_data[:-3]
    sample_data = "\n".join(sample_data)

    with open('./data/countries_sample.json', 'r') as f:
        countries = json.load(f)
    
    with open('./data/countries_nonopted.json', 'r') as f:
        non_optedcountries = json.load(f)

    with open('./data/languages.json', 'r') as f:
        languages = json.load(f)

    with open('./data/programming_languages.json', 'r') as f:
        programming_languages = json.load(f)

    client_stub = pydgraph.DgraphClientStub('localhost:9080')
    client = pydgraph.DgraphClient(client_stub)
    
    # create transaction
    txn = client.txn()

    try:
        txn.mutate(set_nquads=sample_data)
        txn.commit()
    finally:
        txn.discard()
    
    txn = client.txn()

    try:
        txn.mutate(set_obj=countries)
        txn.commit()
    finally:
        txn.discard()

    txn = client.txn()

    try:
        txn.mutate(set_obj={'set': non_optedcountries})
        txn.commit()
    finally:
        txn.discard()

    txn = client.txn()

    try:
        txn.mutate(set_obj=languages)
        txn.commit()
    finally:
        txn.discard()

    txn = client.txn()
    try:
        txn.mutate(set_obj=programming_languages)
        txn.commit()
    finally:
        txn.discard()

    # change all object's entry_review_status to "accepted"
    txn = client.txn()

    query = """{
        q(func: has(dgraph.type)) @filter(NOT type(User) AND NOT type(dgraph.graphql) AND NOT type(Rejected) AND NOT has(entry_review_status)) { v as uid } }"""
    nquad = """
        uid(v) <entry_review_status> "accepted" .
        uid(v) <dgraph.type> "Entry" .
        """
    mutation = txn.create_mutation(set_nquads=nquad)
    request = txn.create_request(query=query, mutations=[mutation], commit_now=True)
    txn.do_request(request)    

    # change all _added_by to Admin
    txn = client.txn()

    query = """{
        q(func: eq(email, "wp3@opted.eu")) { v as uid }
        s(func: has(dgraph.type)) @filter(NOT type(User) AND NOT type(dgraph.graphql) AND NOT has(_added_by)) { u as uid } }"""
    nquad = """
        uid(u) <_added_by> uid(v) .
        """
    mutation = txn.create_mutation(set_nquads=nquad)
    request = txn.create_request(query=query, mutations=[mutation], commit_now=True)
    txn.do_request(request)    

    # fine tune some entries
    txn = client.txn()

    query = """{
        amcat(func: eq(_unique_name, "tool_amcat")) { am as uid }
        python(func: eq(_unique_name, "programming_language_python")) { py as uid }
        paper1(func: eq(_unique_name, "10.1080_1461670X.2020.1745667")) { paper as uid }
        news(func: type(NewsSource)) { news as uid }
        globalvoices(func: eq(_unique_name, "globalvoices_org_website")) { gvoices as uid }
        german(func: eq(_unique_name, "language_german")) { ger as uid }
        english(func: eq(_unique_name, "language_english")) {eng as uid }
        }"""
    nquad = """
        uid(am) <programming_languages> uid(py) .
        uid(paper) <languages> uid(ger) .
        uid(news) <languages> uid(ger) .
        uid(gvoices) <languages> uid(eng) .
        """
    mutation = txn.create_mutation(set_nquads=nquad)
    request = txn.create_request(query=query, mutations=[mutation], commit_now=True)
    txn.do_request(request)    

    print(Fore.GREEN + 'DONE!' + Style.RESET_ALL)
    deinit()

if __name__ == '__main__':
    main()