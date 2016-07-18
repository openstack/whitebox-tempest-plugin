import unittest


class SampleTest(unittest.TestCase):

    def test_success(self):
        self.assertTrue(True)

    def test_fail(self):
        self.assertTrue(False)
