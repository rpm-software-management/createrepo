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
        self.files = {}

    def __addFile(self, dir, ext):
        f = tempfile.NamedTemporaryFile(suffix=ext, dir=dir)
        self.files[f.name] = f

    def tearDown(self):
        self.mdgen = None
        for fname, fobj in self.files.items():
            fobj.close()
            del(self.files[fname])
        if self.tempdir:
            shutil.rmtree(self.tempdir)

    def testEmptyFileList(self):
        """Test when target directory empty of files"""
        results = self.mdgen.getFileList(self.basepath, self.directory, ".test")
        self.assertEquals(results, [], msg="Expected no files")

    def testSingleMatchingFile(self):
        """Test single file matching extension"""
        self.__addFile(self.tempdir, ".test")
        results = self.mdgen.getFileList(self.basepath, self.directory, ".test")
        self.assertEquals(len(results), 1, msg="Expected one file")

    def testSingleNonMatchingFile(self):
        """Test single file not matching extension"""
        self.__addFile(self.tempdir, ".notme")
        results = self.mdgen.getFileList(self.basepath, self.directory, ".test")
        self.assertEquals(results, [], msg="Expected no matching files")

    def testReturnMatchedDirectory(self):
        """Test matching file referenced by directory passed in"""
        self.__addFile(self.tempdir, ".test")
        results = self.mdgen.getFileList(self.basepath, self.directory, ".test")
        filedir = os.path.dirname(results[0])
        self.assertEquals(filedir, self.directory, msg="Returned directory "
                          "should be passed in directory")

    def testMultipleMixedFiles(self):
        """Test right number of files returned with both matches and non"""
        self.__addFile(self.tempdir, ".test")
        self.__addFile(self.tempdir, ".test")
        self.__addFile(self.tempdir, ".notme")
        results = self.mdgen.getFileList(self.basepath, self.directory, ".test")
        self.assertEquals(len(results), 2, msg="Expected one file")

def suite():
    suite = unittest.TestSuite()
    suite.addTest(MetaDataGeneratorTestCase("testEmptyFileList"))
    suite.addTest(MetaDataGeneratorTestCase("testSingleMatchingFile"))
    suite.addTest(MetaDataGeneratorTestCase("testSingleNonMatchingFile"))
    suite.addTest(MetaDataGeneratorTestCase("testReturnMatchedDirectory"))
    suite.addTest(MetaDataGeneratorTestCase("testMultipleMixedFiles"))
    return suite

if __name__ == "__main__":
    testrunner = unittest.TextTestRunner()
    testrunner.run(suite())

