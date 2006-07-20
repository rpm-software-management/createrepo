#!/usr/bin/python

import os
import shutil
import sys
import tempfile
import unittest

sys.path.append("..")

from genpkgmetadata import MetaDataGenerator

class MetaDataGeneratorTestCase(unittest.TestCase):

    def setUp(self):
        self.tempdir = tempfile.mkdtemp(prefix="generate")
        self.mdgen = MetaDataGenerator({})
        self.basepath = os.path.dirname(self.tempdir)
        self.directory = os.path.basename(self.tempdir)

    def tearDown(self):
        self.mdgen = None
        if self.tempdir:
            shutil.rmtree(self.tempdir)
        self.tempdir = None

    def testEmptyFileList(self):
        results = self.mdgen.getFileList(self.basepath, self.directory, ".test")
        self.assertEquals(results, [], msg="Expected no files")

    def testSingleFile(self):
        f = tempfile.NamedTemporaryFile(suffix=".test", dir=self.tempdir)
        results = self.mdgen.getFileList(self.basepath, self.directory, ".test")
        self.assertEquals(len(results), 1, msg="Expected one file")
        f.close()

def suite():
    suite = unittest.TestSuite()
    suite.addTest(MetaDataGeneratorTestCase("testEmptyFileList"))
    suite.addTest(MetaDataGeneratorTestCase("testSingleFile"))
    return suite

if __name__ == "__main__":
    testrunner = unittest.TextTestRunner()
    testrunner.run(suite())

