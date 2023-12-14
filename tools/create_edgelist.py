from meteor.main.model import Schema
import pandas as pd

edge_list = []

exclude = ['User', 'Entry', 'File', 'Rejected', 'Comment', 'Notification']

for dgraph_type in Schema.get_types():
    if dgraph_type in exclude: continue
    for label, predicate in Schema.get_relationships(dgraph_type).items():
        for target in predicate.relationship_constraint:
            if target in exclude: continue
            edge = {'source': dgraph_type,
                    'target': target,
                    'type': 'directed',
                    'label': label}
            edge_list.append(edge)


pd.DataFrame(edge_list).to_csv('edge_list.csv', index=False)