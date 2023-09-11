import unittest

if __name__ == "__main__":
    from sys import path
    from os.path import dirname
    from requests import HTTPError
    import unittest

    path.append(dirname(path[0]))

from flaskinventory.flaskdgraph.utils import restore_sequence, recursive_restore_sequence

class TestUtils(unittest.TestCase):
    
    def test_restore_sequence(self):
        d = {'_authors_fallback': ['Author B', 'Author D', 'Author A', 'Author C'],
             '_authors_fallback|sequence':
                {'0': 1,
                 '1': 3,
                 '2': 0,
                 '3': 2}}
    
        solution = ['Author A', 'Author B', 'Author C', 'Author D']
        
        restore_sequence(d)

        self.assertListEqual(d['_authors_fallback'], solution)

    def test_recursive_restore_sequence(self):
        l = [{
                '_authors_fallback': ['Author B', 'Author D', 'Author A', 'Author C'],
                '_authors_fallback|sequence': {
                    '0': 1,
                    '1': 3,
                    '2': 0,
                    '3': 2}
                },
                {
                '_authors_fallback': ['Author D', 'Author B', 'Author C', 'Author A'],
                '_authors_fallback|sequence': {
                    '0': 3,
                    '1': 1,
                    '2': 2,
                    '3': 0}
                },
                {
                '_authors_fallback': ['Author A'],
                '_authors_fallback|sequence': {
                    '0': 0}
                },
                {
                '_authors_fallback': ['Author A']
                }
            ]
    
        solution = ['Author A', 'Author B', 'Author C', 'Author D']
        recursive_restore_sequence(l)

        self.assertListEqual(l[0]['_authors_fallback'], solution)
        self.assertListEqual(l[1]['_authors_fallback'], solution)
        self.assertListEqual(l[2]['_authors_fallback'], ['Author A'])



if __name__ == "__main__":
    unittest.main(verbosity=2)
