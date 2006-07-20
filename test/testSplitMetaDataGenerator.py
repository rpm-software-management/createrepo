#!/usr/bin/python

import os
import shutil
import sys
import tempfile
import unittest

sys.path.append("..")

from genpkgmetadata import SplitMetaDataGenerator

class SplitMetaDataGeneratorTestCase(unittest.TestCase):

    def setUp(self):
        self.tempdir = tempfile.mkdtemp(prefix="generate")
        self.mdgen = SplitMetaDataGenerator({})
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

    def testNoFiles(self):
        """Test when target directory empty of files"""
        results = self.mdgen.getFileList(self.basepath, self.directory, ".test")
        self.assertEquals(results, [], msg="Expected no files")

    def testMatch(self):
        """Test single file matching extension"""
        self.__addFile(self.tempdir, ".test")
        results = self.mdgen.getFileList(self.basepath, self.directory, ".test")
        self.assertEquals(len(results), 1, msg="Expected one file")

    def testMatches(self):
        """Test right number of files returned with both matches and non"""
        self.__addFile(self.tempdir, ".test")
        self.__addFile(self.tempdir, ".test")
        self.__addFile(self.tempdir, ".notme")
        results = self.mdgen.getFileList(self.basepath, self.directory, ".test")
        self.assertEquals(len(results), 2, msg="Expected one file")

    def testNoMatches(self):
        """Test single file not matching extension"""
        self.__addFile(self.tempdir, ".notme")
        results = self.mdgen.getFileList(self.basepath, self.directory, ".test")
        self.assertEquals(results, [], msg="Expected no matching files")

    def testReturnPath(self):
        """Test matching file referenced by directory passed in"""
        self.__addFile(self.tempdir, ".test")
        results = self.mdgen.getFileList(self.basepath, self.directory, ".test")
        filedir = os.path.dirname(results[0])
        self.assertEquals(filedir, self.directory, msg="Returned directory "
                          "should be passed in directory")

    def testCurrentDirectoryNoMatches(self):
        """Test when target directory child of cwd no matches"""
        oldwd = os.getcwd()
        os.chdir(self.basepath)
        results = self.mdgen.getFileList(".", self.directory, ".test")
        os.chdir(oldwd)
        self.assertEquals(results, [], msg="Expected no files")

    def testCurrentDirectoryMatches(self):
        """Test when target directory child of cwd matches"""
        self.__addFile(self.tempdir, ".test")
        oldwd = os.getcwd()
        os.chdir(self.basepath)
        results = self.mdgen.getFileList(".", self.directory, ".test")
        os.chdir(oldwd)
        self.assertEquals(len(results), 1, msg="Expected one file")

    def testCurrentDirectoryReturnPath(self):
        self.__addFile(self.tempdir, ".test")
        oldwd = os.getcwd()
        os.chdir(self.basepath)
        results = self.mdgen.getFileList(".", self.directory, ".test")
        filedir = os.path.dirname(results[0])
        os.chdir(oldwd)
        self.assertEquals(filedir, self.directory, msg="Returned directory "
                          "should be passed in directory")

    def testParallelDirectoryNoMatches(self):
        """Test when target directory parallel to cwd no matches"""
        oldwd = os.getcwd()
        paralleldir = tempfile.mkdtemp(prefix="parallel")
        os.chdir(paralleldir)
        results = self.mdgen.getFileList("..", self.directory, ".test")
        os.chdir(oldwd)
        self.assertEquals(results, [], msg="Expected no files")

    def testParallelDirectoryMatches(self):
        """Test when target directory parallel to cwd matches"""
        self.__addFile(self.tempdir, ".test")
        oldwd = os.getcwd()
        paralleldir = tempfile.mkdtemp(prefix="parallel")
        os.chdir(paralleldir)
        results = self.mdgen.getFileList("..", self.directory, ".test")
        os.chdir(oldwd)
        self.assertEquals(len(results), 1, msg="Expected no files")

    def testParallelDirectoryReturnPath(self):
        self.__addFile(self.tempdir, ".test")
        oldwd = os.getcwd()
        paralleldir = tempfile.mkdtemp(prefix="parallel")
        os.chdir(paralleldir)
        results = self.mdgen.getFileList("..", self.directory, ".test")
        filedir = os.path.dirname(results[0])
        os.chdir(oldwd)
        self.assertEquals(filedir, self.directory, msg="Returned directory "
                          "should be passed in directory")



def suite():
    suite = unittest.TestSuite()
    suite.addTest(SplitMetaDataGeneratorTestCase("testNoFiles"))
    suite.addTest(SplitMetaDataGeneratorTestCase("testMatch"))
    suite.addTest(SplitMetaDataGeneratorTestCase("testNoMatches"))
    suite.addTest(SplitMetaDataGeneratorTestCase("testMatches"))
    suite.addTest(SplitMetaDataGeneratorTestCase("testReturnPath"))
    suite.addTest(SplitMetaDataGeneratorTestCase("testCurrentDirectoryNoMatches"))
    suite.addTest(SplitMetaDataGeneratorTestCase("testCurrentDirectoryMatches"))
    suite.addTest(SplitMetaDataGeneratorTestCase("testCurrentDirectoryReturnPath"))
    suite.addTest(SplitMetaDataGeneratorTestCase("testParallelDirectoryNoMatches"))
    suite.addTest(SplitMetaDataGeneratorTestCase("testParallelDirectoryMatches"))
    suite.addTest(SplitMetaDataGeneratorTestCase("testParallelDirectoryReturnPath"))
    return suite

if __name__ == "__main__":
    testrunner = unittest.TextTestRunner()
    testrunner.run(suite())

