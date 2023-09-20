import pandas as pd
import json

from pathlib import Path

p = Path.cwd()

with open(p / 'data' / 'tools_documentation.json') as f:
    dump = json.load(f)


df = pd.DataFrame(dump['data']['q'])

df['documentation_kind'] = df['documentation|kind'].apply(lambda x: list(x.values()))

df = df.explode(['documentation', 'documentation_kind'])

df.to_excel('blub.xlsx')