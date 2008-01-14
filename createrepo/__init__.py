# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
# Copyright 2007  Red Hat, Inc - written by seth vidal skvidal at fedoraproject.org

import exceptions
import os
import sys
import libxml2
import string
import fnmatch
import hashlib
import rpm
import yumbased
from optparse import OptionContainer


from yum import misc, Errors
import rpmUtils.transaction
from utils import _
import readMetadata

try:
    import sqlitecachec
except ImportError:
    pass


from utils import _gzipOpen, bzipFile


__version__ = '0.9.1'



class MDError(exceptions.Exception):
    def __init__(self, value=None):
        exceptions.Exception.__init__(self)
        self.value = value
    
    def __str__(self):
        return self.value

class MetaDataConfig(object):
    def __init__(self):
        self.quiet = False
        self.verbose = False
        self.excludes = []
        self.baseurl = ''
        self.groupfile = None
        self.sumtype = 'sha'
        self.noepoch = False #???
        self.pretty = False
        self.cachedir = None
        self.basedir = os.getcwd()
        self.use_cache = False
        self.checkts = False
        self.split = False        
        self.update = False
        self.database = False
        self.outputdir = None
        self.file_patterns = ['.*bin\/.*', '^\/etc\/.*', '^\/usr\/lib\/sendmail$']
        self.dir_patterns = ['.*bin\/.*', '^\/etc\/.*']
        self.skip_symlinks = False
        self.pkglist = []
        self.primaryfile = 'primary.xml.gz'
        self.filelistsfile = 'filelists.xml.gz'
        self.otherfile = 'other.xml.gz'
        self.repomdfile = 'repomd.xml'
        self.tempdir = '.repodata'
        self.finaldir = 'repodata'
        self.olddir = '.olddata'
        self.mdtimestamp = 0
        self.directory = None
        self.directories = []

class SimpleMDCallBack(object):
    def errorlog(self, thing):
        print >> sys.stderr, thing
        
    def log(self, thing):
        print thing
    
    def progress(self, item, current, total):
        sys.stdout.write('\r' + ' ' * 80)
        sys.stdout.write("\r%d/%d - %s" % (current, total, item))
        sys.stdout.flush()
            
#FIXME = make it so you pass in a dir to doPkgMetadata() and it
# parses out basedir and directory for relative dir from there
# it creates the .repodata directory in the output location, etc
        
class MetaDataGenerator:
    def __init__(self, config_obj=None, callback=None):
        self.conf = config_obj
        if config_obj == None:
            self.conf = MetaDataConfig()
        if not callback:
            self.callback = SimpleMDCallBack()
        else:
            self.callback = callback    
        
                    
        self.ts = rpmUtils.transaction.initReadOnlyTransaction()
        self.pkgcount = 0
        self.files = []

    def _setup_and_check_repo_dir(self, direc):
        if os.path.isabs(direc):
            self.conf.basedir = os.path.dirname(direc)
            self.conf.directory = os.path.basename(direc)
        else:
            self.conf.basedir = os.path.realpath(self.conf.basedir)

        if not self.conf.opts.outputdir:
            self.conf.outputdir = os.path.join(self.conf.basedir, direc)


    def _os_path_walk(self, top, func, arg):
        """Directory tree walk with callback function.
         copy of os.path.walk, fixes the link/stating problem
         """

        try:
            names = os.listdir(top)
        except os.error:
            return
        func(arg, top, names)
        for name in names:
            name = os.path.join(top, name)
            if os.path.isdir(name):
                self._os_path_walk(name, func, arg)
    # module
    def getFileList(self, basepath, directory, ext):
        """Return all files in path matching ext, store them in filelist,
        recurse dirs. Returns a list object"""

        extlen = len(ext)

        def extension_visitor(filelist, dirname, names):
            for fn in names:
                if os.path.isdir(fn):
                    continue
                if self.conf.skip_symlinks and os.path.islink(fn):
                    continue
                elif fn[-extlen:].lower() == '%s' % (ext):
                    relativepath = dirname.replace(startdir, "", 1)
                    relativepath = relativepath.lstrip("/")
                    filelist.append(os.path.join(relativepath,fn))

        filelist = []
        startdir = os.path.join(basepath, directory) + '/'
        self._os_path_walk(startdir, extension_visitor, filelist)
        return filelist

    def errorlog(self, thing):
        """subclass this if you want something different...."""
        errorprint(thing)
        
    def checkTimeStamps(self):
        """check the timestamp of our target dir. If it is not newer than the repodata
           return False, else True"""
        if self.conf.checkts:
            files = self.getFileList(self.conf.basedir, self.conf.directory, '.rpm')
            files = self.trimRpms(files)
            for f in files:
                fn = os.path.join(self.conf.basedir, self.conf.directory, f)
                if not os.path.exists(fn):
                    self.callback.errorlog(_('cannot get to file: %s') % fn)
                if os.path.getctime(fn) > self.conf.mdtimestamp:
                    return False
                else:
                    return True
                
        return False

    def trimRpms(self, files):
        badrpms = []
        for file in files:
            for glob in self.conf.excludes:
                if fnmatch.fnmatch(file, glob):
                    if file not in badrpms:
                        badrpms.append(file)
        for file in badrpms:
            if file in files:
                files.remove(file)
        return files

    def doPkgMetadata(self, directory=None):
        """all the heavy lifting for the package metadata"""
        if not directory:
            directory = self.conf.directory
            
        # rpms we're going to be dealing with
        if self.conf.update:
            #build the paths
            primaryfile = os.path.join(self.conf.outputdir, self.conf.finaldir, self.conf.primaryfile)
            flfile = os.path.join(self.conf.outputdir, self.conf.finaldir, self.conf.filelistsfile)
            otherfile = os.path.join(self.conf.outputdir, self.conf.finaldir, self.conf.otherfile)
            opts = {
                'verbose' : self.conf.verbose,
                'pkgdir' : os.path.normpath(os.path.join(self.conf.basedir, directory))
            }
            #and scan the old repo
            self.oldData = readMetadata.MetadataIndex(self.conf.outputdir,
                                                      primaryfile, flfile, otherfile, opts)
        if self.conf.pkglist:
            packages = self.conf.pkglist
        else:
            packages = self.getFileList(self.conf.basedir, directory, '.rpm')
            
        packages = self.trimRpms(packages)
        self.pkgcount = len(packages)
        self.openMetadataDocs()
        self.writeMetadataDocs(packages, directory)
        self.closeMetadataDocs()

    # module
    def openMetadataDocs(self):
        self.primaryfile = self._setupPrimary()
        self.flfile = self._setupFilelists()
        self.otherfile = self._setupOther()

    def _setupPrimary(self):
        # setup the primary metadata file
        primaryfilepath = os.path.join(self.conf.outputdir, self.conf.tempdir, self.conf.primaryfile)
        fo = _gzipOpen(primaryfilepath, 'w')
        fo.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        fo.write('<metadata xmlns="http://linux.duke.edu/metadata/common" xmlns:rpm="http://linux.duke.edu/metadata/rpm" packages="%s">' %
                       self.pkgcount)
        return fo

    def _setupFilelists(self):
        # setup the filelist file
        filelistpath = os.path.join(self.conf.outputdir, self.conf.tempdir, self.conf.filelistsfile)
        fo = _gzipOpen(filelistpath, 'w')
        fo.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        fo.write('<filelists xmlns="http://linux.duke.edu/metadata/filelists" packages="%s">' %
                       self.pkgcount)
        return fo
        
    def _setupOther(self):
        # setup the other file
        otherfilepath = os.path.join(self.conf.outputdir, self.conf.tempdir, self.conf.otherfile)
        fo = _gzipOpen(otherfilepath, 'w')
        fo.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        fo.write('<otherdata xmlns="http://linux.duke.edu/metadata/other" packages="%s">' %
                       self.pkgcount)
        return fo
        

    def read_in_package(self, directory, rpmfile):
        # directory is stupid - just make it part of the class
        rpmfile = '%s/%s/%s' % (self.conf.basedir, directory, rpmfile)
        try:
            po = yumbased.CreateRepoPackage(self.ts, rpmfile)
        except Errors.MiscError, e:
            raise MDError, "Unable to open package: %s" % e
        return po

    def writeMetadataDocs(self, pkglist, directory, current=0):
        # FIXME
        # directory is unused, kill it, pkglist should come from self
        # I don't see why current needs to be this way at all
        for pkg in pkglist:
            current+=1
            recycled = False

            # look to see if we can get the data from the old repodata
            # if so write this one out that way
            if self.conf.update:
                #see if we can pull the nodes from the old repo
                nodes = self.oldData.getNodes(pkg)
                if nodes is not None:
                    recycled = True

            
            # otherwise do it individually
            if not recycled:
                #scan rpm files
                try:
                    po = self.read_in_package(directory, pkg)
                except MDError, e:
                    # need to say something here
                    self.callback.errorlog("\nError %s: %s\n" % (pkg, e))
                    continue
                reldir = os.path.join(self.conf.basedir, directory)
                self.primaryfile.write(po.do_primary_xml_dump(reldir, baseurl=self.conf.baseurl))
                self.flfile.write(po.do_filelists_xml_dump())
                self.otherfile.write(po.do_other_xml_dump())
            else:
                if self.conf.verbose:
                    self.callback.log(_("Using data from old metadata for %s") % pkg)
                (primarynode, filenode, othernode) = nodes    

                for node, outfile in ((primarynode,self.primaryfile),
                                      (filenode,self.flfile),
                                      (othernode,self.otherfile)):
                    if node is None:
                        break
                    output = node.serialize('UTF-8', self.conf.pretty)
                    if output:
                        outfile.write(output)
                    else:
                        if self.conf.verbose:
                            self.callback.log(_("empty serialize on write to %s in %s") % (outfile, pkg))
                    outfile.write('\n')

                self.oldData.freeNodes(pkg)

            if not self.conf.quiet:
                if self.conf.verbose:
                    self.callback.log('%d/%d - %s' % (current, self.pkgcount, pkg))
                else:
                    self.callback.progress(pkg, current, self.pkgcount)

        return current


    def closeMetadataDocs(self):
        if not self.conf.quiet:
            self.callback.log('')

        # save them up to the tmp locations:
        if not self.conf.quiet:
            self.callback.log(_('Saving Primary metadata'))
        self.primaryfile.write('\n</metadata>')
        self.primaryfile.close()

        if not self.conf.quiet:
            self.callback.log(_('Saving file lists metadata'))
        self.flfile.write('\n</filelists>')
        self.flfile.close()

        if not self.conf.quiet:
            self.callback.log(_('Saving other metadata'))
        self.otherfile.write('\n</otherdata>')
        self.otherfile.close()



    def doRepoMetadata(self):
        """wrapper to generate the repomd.xml file that stores the info on the other files"""
        repodoc = libxml2.newDoc("1.0")
        reporoot = repodoc.newChild(None, "repomd", None)
        repons = reporoot.newNs('http://linux.duke.edu/metadata/repo', None)
        reporoot.setNs(repons)
        repopath = os.path.join(self.conf.outputdir, self.conf.tempdir)
        repofilepath = os.path.join(repopath, self.conf.repomdfile)

        sumtype = self.conf.sumtype
        workfiles = [(self.conf.otherfile, 'other',),
                     (self.conf.filelistsfile, 'filelists'),
                     (self.conf.primaryfile, 'primary')]
        repoid='garbageid'
        
        if self.conf.database:
            try:
                dbversion = str(sqlitecachec.DBVERSION)
            except AttributeError:
                dbversion = '9'
            rp = sqlitecachec.RepodataParserSqlite(repopath, repoid, None)

        for (file, ftype) in workfiles:
            complete_path = os.path.join(repopath, file)
            
            zfo = _gzipOpen(complete_path)
            uncsum = misc.checksum(sumtype, zfo)
            zfo.close()
            csum = misc.checksum(sumtype, complete_path)
            timestamp = os.stat(complete_path)[8]
            
            db_csums = {}
            db_compressed_sums = {}
            
            if self.conf.database:
                if ftype == 'primary':
                    rp.getPrimary(complete_path, csum)
                                
                elif ftype == 'filelists':
                    rp.getFilelists(complete_path, csum)
                    
                elif ftype == 'other':
                    rp.getOtherdata(complete_path, csum)
                

                tmp_result_name = '%s.xml.gz.sqlite' % ftype
                tmp_result_path = os.path.join(repopath, tmp_result_name)
                good_name = '%s.sqlite' % ftype
                resultpath = os.path.join(repopath, good_name)
                
                # rename from silly name to not silly name
                os.rename(tmp_result_path, resultpath)
                compressed_name = '%s.bz2' % good_name
                result_compressed = os.path.join(repopath, compressed_name)
                db_csums[ftype] = misc.checksum(sumtype, resultpath)
                
                # compress the files
                bzipFile(resultpath, result_compressed)
                # csum the compressed file
                db_compressed_sums[ftype] = misc.checksum(sumtype, result_compressed)
                # remove the uncompressed file
                os.unlink(resultpath)

                # timestamp the compressed file
                db_timestamp = os.stat(result_compressed)[8]
                
                # add this data as a section to the repomdxml
                db_data_type = '%s_db' % ftype
                data = reporoot.newChild(None, 'data', None)
                data.newProp('type', db_data_type)
                location = data.newChild(None, 'location', None)
                if self.conf.baseurl is not None:
                    location.newProp('xml:base', self.conf.baseurl)
                
                location.newProp('href', os.path.join(self.conf.finaldir, compressed_name))
                checksum = data.newChild(None, 'checksum', db_compressed_sums[ftype])
                checksum.newProp('type', sumtype)
                db_tstamp = data.newChild(None, 'timestamp', str(db_timestamp))
                unchecksum = data.newChild(None, 'open-checksum', db_csums[ftype])
                unchecksum.newProp('type', sumtype)
                database_version = data.newChild(None, 'database_version', dbversion)
                
                
            data = reporoot.newChild(None, 'data', None)
            data.newProp('type', ftype)
            location = data.newChild(None, 'location', None)
            if self.conf.baseurl is not None:
                location.newProp('xml:base', self.conf.baseurl)
            location.newProp('href', os.path.join(self.conf.finaldir, file))
            checksum = data.newChild(None, 'checksum', csum)
            checksum.newProp('type', sumtype)
            timestamp = data.newChild(None, 'timestamp', str(timestamp))
            unchecksum = data.newChild(None, 'open-checksum', uncsum)
            unchecksum.newProp('type', sumtype)
        
        # if we've got a group file then checksum it once and be done
        if self.conf.groupfile is not None:
            grpfile = self.conf.groupfile
            timestamp = os.stat(grpfile)[8]
            sfile = os.path.basename(grpfile)
            fo = open(grpfile, 'r')
            output = open(os.path.join(self.conf.outputdir, self.conf.tempdir, sfile), 'w')
            output.write(fo.read())
            output.close()
            fo.seek(0)
            csum = misc.checksum(sumtype, fo)
            fo.close()

            data = reporoot.newChild(None, 'data', None)
            data.newProp('type', 'group')
            location = data.newChild(None, 'location', None)
            if self.conf.baseurl is not None:
                location.newProp('xml:base', self.conf.baseurl)
            location.newProp('href', os.path.join(self.conf.finaldir, sfile))
            checksum = data.newChild(None, 'checksum', csum)
            checksum.newProp('type', sumtype)
            timestamp = data.newChild(None, 'timestamp', str(timestamp))

        # save it down
        try:
            repodoc.saveFormatFileEnc(repofilepath, 'UTF-8', 1)
        except:
            self.callback.errorlog(_('Error saving temp file for repomd.xml: %s') % repofilepath)
            raise MDError, 'Could not save temp file: %s' % repofilepath 

        del repodoc

class SplitMetaDataGenerator(MetaDataGenerator):

    def __init__(self, config_obj=None, callback=None):
        MetaDataGenerator.__init__(self, config_obj=conf, callback=None)

    def _getFragmentUrl(self, url, fragment):
        import urlparse
        urlparse.uses_fragment.append('media')
        if not url:
            return url
        (scheme, netloc, path, query, fragid) = urlparse.urlsplit(url)
        return urlparse.urlunsplit((scheme, netloc, path, query, str(fragment)))

    def getFileList(self, basepath, directory, ext):

        extlen = len(ext)

        def extension_visitor(arg, dirname, names):
            for fn in names:
                if os.path.isdir(fn):
                    continue
                elif string.lower(fn[-extlen:]) == '%s' % (ext):
                    reldir = os.path.basename(dirname)
                    if reldir == os.path.basename(directory):
                        reldir = ""
                    arg.append(os.path.join(reldir,fn))

        rpmlist = []
        startdir = os.path.join(basepath, directory)
        os.path.walk(startdir, extension_visitor, rpmlist)
        return rpmlist

    def doPkgMetadata(self):
        """all the heavy lifting for the package metadata"""
        import types
        if type(self.directories) == types.StringType:
            MetaDataGenerator.doPkgMetadata(self)
            return
        filematrix = {}
        for mydir in self.directories:
            filematrix[mydir] = self.getFileList(self.conf.basedir, mydir, '.rpm')
            self.trimRpms(filematrix[mydir])
            self.pkgcount += len(filematrix[mydir])

        mediano = 1
        current = 0
        self.conf.baseurl = self._getFragmentUrl(self.conf.baseurl, mediano)
        self.openMetadataDocs()
        original_basedir = self.conf.basedir
        for mydir in self.directories:
            self.conf.baseurl = self._getFragmentUrl(self.conf.baseurl, mediano)
            current = self.writeMetadataDocs(filematrix[mydir], mydir, current)
            mediano += 1
        self.conf.baseurl = self._getFragmentUrl(self.conf.baseurl, 1)
        self.closeMetadataDocs()




