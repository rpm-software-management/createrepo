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
        self.basepath = tempfile.mkdtemp(prefix="generate")
        self.directories = []
        for i in range(0,3):
            mydir = tempfile.mkdtemp(prefix="split", suffix=str(i))
            self.directories.append(mydir)
        self.mdgen = SplitMetaDataGenerator({})
        self.files = {}

    def __addFile(self, dir, ext):
        f = tempfile.NamedTemporaryFile(suffix=ext, dir=dir)
        self.files[f.name] = f
        return f.name

    def tearDown(self):
        self.mdgen = None
        for fname, fobj in self.files.items():
            fobj.close()
            del(self.files[fname])
        if self.basepath:
            shutil.rmtree(self.basepath)

    def testNoFiles(self):
        """Test when target directories empty of files"""
        results = []
        for splitdir in self.directories:
            results = self.mdgen.getFileList(self.basepath, self.directories[0], ".test")
            self.assertEquals(results, [], msg="Expected no files")

    def testMatchPrimaryDir(self):
        """Test single file matching extension"""

        tempdir = os.path.join(self.basepath, self.directories[0])
        self.__addFile(tempdir, ".test")
        results = self.mdgen.getFileList(self.basepath, 
                                         self.directories[0], ".test")
        self.assertEquals(len(results), 1, msg="Expected one file")

    def testSplitMatches(self):
        """Test right number of files returned with matches in all dirs"""
        for splitdir in self.directories:
            tempdir = os.path.join(self.basepath, splitdir)
            os.mkdir(tempdir + "/subdir")
            self.__addFile(tempdir + "/subdir", ".test")
        total = 0
        for splitdir in self.directories:
            results = self.mdgen.getFileList(self.basepath, splitdir, ".test")
            total += 1
            self.assertEquals(len(results), 1, msg="Expected one file per dir")
        self.assertEquals(total, 3, msg="Expected total of 3 files got %d" %(total,))

    def testPrimaryReturnPath(self):
        """Test matching file referenced from within primary dir"""
        tempdir = os.path.join(self.basepath, self.directories[0])
        fname = self.__addFile(tempdir, ".test")
        results = self.mdgen.getFileList(self.basepath, 
                                         self.directories[0], ".test")
        self.assertEquals(results[0], os.path.basename(fname), 
                          msg="Returned file %s should be created file %s"
                          % (results[0],os.path.basename(fname)))

    def testPrimaryReturnPathSubdir(self):
        """Test matching file referenced from within subdir primary dir"""
        tempdir = os.path.join(self.basepath, self.directories[0], "subdir")
        os.mkdir(tempdir)
        fname = self.__addFile(tempdir, ".test")

        results = self.mdgen.getFileList(self.basepath, 
                                         self.directories[0], ".test")
        returned_dir = os.path.dirname(results[0])
        self.assertEquals(returned_dir, "subdir",
                          msg="Returned dir %s of file %s should be subdir"
                          % (returned_dir,results[0]))

    def testNonPrimaryReturnPathSubdir(self):
        """Test matching file referenced from within subdir primary dir"""
        tempdir = os.path.join(self.basepath, self.directories[1], "subdir")
        os.mkdir(tempdir)
        fname = self.__addFile(tempdir, ".test")

        results = self.mdgen.getFileList(self.basepath, 
                                         self.directories[1], ".test")
        returned_dir = os.path.dirname(results[0])
        self.assertEquals(returned_dir, "subdir",
                          msg="Returned dir %s of file %s should be subdir"
                          % (returned_dir,results[0]))

def suite():
    suite = unittest.TestSuite()
    suite.addTest(SplitMetaDataGeneratorTestCase("testNoFiles"))
    suite.addTest(SplitMetaDataGeneratorTestCase("testMatchPrimaryDir"))
    suite.addTest(SplitMetaDataGeneratorTestCase("testSplitMatches"))
    suite.addTest(SplitMetaDataGeneratorTestCase("testPrimaryReturnPath"))
    suite.addTest(SplitMetaDataGeneratorTestCase("testPrimaryReturnPathSubdir"))
    suite.addTest(SplitMetaDataGeneratorTestCase("testNonPrimaryReturnPathSubdir"))
    return suite

if __name__ == "__main__":
    testrunner = unittest.TextTestRunner()
    testrunner.run(suite())

