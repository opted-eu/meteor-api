# Ugly hack to allow absolute import from the root folder
# whatever its name is. Please forgive the heresy.

if __name__ == "__main__":
    from sys import path
    from os.path import dirname
    from flask import request, url_for
    import unittest

    path.append(dirname(path[0]))
    from test_setup import BasicTestSetup
    from flaskinventory import dgraph
    from flaskinventory.main.model import Schema, Entry, NewsSource


class TestSchema(BasicTestSetup):

    def test_schema_generation(self):
        Schema.generate_dgraph_schema()

    def test_predicates(self):
        # Test string predicates
        self.assertEqual(Entry.name.predicate, 'name')
        # test boolean predicate
        self.assertEqual(NewsSource.verified_account.predicate, 'verified_account')

        # test inherited predicate
        self.assertEqual(NewsSource.name.predicate, 'name')

        # test query_filter
        self.assertEqual(NewsSource.name.query_filter('some name'), 'eq(name, "some name")')
        self.assertEqual(NewsSource.verified_account.query_filter(True), 'eq(verified_account, "true")')

if __name__ == "__main__":
    unittest.main(verbosity=1)
