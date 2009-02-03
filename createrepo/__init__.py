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

import os
import sys
import libxml2
import string
import fnmatch
import time
import yumbased
import shutil
from  bz2 import BZ2File
from urlgrabber import grabber
import tempfile

from yum import misc, Errors, to_unicode
from yum.sqlutils import executeSQL
from yum.packageSack import MetaSack
from yum.packages import YumAvailablePackage

import rpmUtils.transaction
from utils import _, errorprint, MDError
import readMetadata
try:
    import sqlite3 as sqlite
except ImportError:
    import sqlite

try:
    import sqlitecachec
except ImportError:
    pass

from utils import _gzipOpen, bzipFile, checkAndMakeDir, GzipFile, checksum_and_rename
import deltarpms

__version__ = '0.9.6'


class MetaDataConfig(object):
    def __init__(self):
        self.quiet = False
        self.verbose = False
        self.profile = False
        self.excludes = []
        self.baseurl = None
        self.groupfile = None
        self.sumtype = 'sha256'
        self.pretty = False
        self.cachedir = None 
        self.use_cache = False
        self.basedir = os.getcwd()
        self.checkts = False
        self.split = False        
        self.update = False
        self.deltas = False # do the deltarpm thing
        self.deltadir = None # where to put the .drpms - defaults to 'drpms' inside 'repodata'
        self.delta_relative = 'drpms/'
        self.oldpackage_paths = [] # where to look for the old packages - 
        self.deltafile = 'prestodelta.xml.gz'
        self.num_deltas = 1 # number of older versions to delta (max)
        self.update_md_path = None 
        self.skip_stat = False
        self.database = False
        self.outputdir = None
        self.file_patterns = ['.*bin\/.*', '^\/etc\/.*', '^\/usr\/lib\/sendmail$']
        self.dir_patterns = ['.*bin\/.*', '^\/etc\/.*']
        self.skip_symlinks = False
        self.pkglist = []
        self.database_only = False
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
        self.changelog_limit = None # needs to be an int or None
        self.unique_md_filenames = False
        self.additional_metadata = {} # dict of 'type':'filename'
        self.revision = str(int(time.time()))
        self.content_tags = [] # flat list of strings (like web 2.0 tags)
        self.distro_tags = []# [(cpeid(None allowed), human-readable-string)]

class SimpleMDCallBack(object):
    def errorlog(self, thing):
        print >> sys.stderr, thing
        
    def log(self, thing):
        print thing
    
    def progress(self, item, current, total):
        sys.stdout.write('\r' + ' ' * 80)
        sys.stdout.write("\r%d/%d - %s" % (current, total, item))
        sys.stdout.flush()
            
      
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
        self.current_pkg = 0
        self.files = []
        self.rpmlib_reqs = {}
                
        if not self.conf.directory and not self.conf.directories:
            raise MDError, "No directory given on which to run."
        
        if not self.conf.directories: # just makes things easier later
            self.conf.directories = [self.conf.directory]
        if not self.conf.directory: # ensure we have both in the config object
            self.conf.directory = self.conf.directories[0]
        
        # the cachedir thing:
        if self.conf.cachedir:
            self.conf.use_cache = True
            
        # this does the dir setup we need done
        self._parse_directory()
        self._test_setup_dirs()        

    def _parse_directory(self):
        """pick up the first directory given to us and make sure we know
           where things should go"""
        if os.path.isabs(self.conf.directory):
            self.conf.basedir = os.path.dirname(self.conf.directory)
            self.conf.relative_dir = os.path.basename(self.conf.directory)
        else:
            self.conf.basedir = os.path.realpath(self.conf.basedir)
            self.conf.relative_dir = self.conf.directory

        self.package_dir = os.path.join(self.conf.basedir, self.conf.relative_dir)
        
        if not self.conf.outputdir:
            self.conf.outputdir = os.path.join(self.conf.basedir, self.conf.relative_dir)

    def _test_setup_dirs(self):
        # start the sanity/stupidity checks
        for mydir in self.conf.directories:
            if os.path.isabs(mydir):
                testdir = mydir
            else:
                if mydir.startswith('../'):
                    testdir = os.path.realpath(mydir)
                else:
                    testdir = os.path.join(self.conf.basedir, mydir)

            if not os.path.exists(testdir):
                raise MDError, _('Directory %s must exist') % mydir

            if not os.path.isdir(testdir):
                raise MDError, _('%s must be a directory') % mydir

        if not os.access(self.conf.outputdir, os.W_OK):
            raise MDError, _('Directory %s must be writable.') % self.conf.outputdir

        temp_output = os.path.join(self.conf.outputdir, self.conf.tempdir)
        if not checkAndMakeDir(temp_output):
            raise MDError, _('Cannot create/verify %s') % temp_output

        temp_final = os.path.join(self.conf.outputdir, self.conf.finaldir)
        if not checkAndMakeDir(temp_final):
            raise MDError, _('Cannot create/verify %s') % temp_final

        if self.conf.deltas:
            temp_delta = os.path.join(self.conf.outputdir, self.conf.delta_relative)
            if not checkAndMakeDir(temp_delta):
                raise MDError, _('Cannot create/verify %s') % temp_delta
            self.conf.deltadir = temp_delta

        if os.path.exists(os.path.join(self.conf.outputdir, self.conf.olddir)):
            raise MDError, _('Old data directory exists, please remove: %s') % self.conf.olddir

        # make sure we can write to where we want to write to:
        # and pickup the mdtimestamps while we're at it
        direcs = ['tempdir' , 'finaldir']
        if self.conf.deltas:
            direcs.append('deltadir')

        for direc in direcs:
            filepath = os.path.join(self.conf.outputdir, getattr(self.conf, direc))
            if os.path.exists(filepath):
                if not os.access(filepath, os.W_OK):
                    raise MDError, _('error in must be able to write to metadata dir:\n  -> %s') % filepath

                if self.conf.checkts:
                    timestamp = os.path.getctime(filepath)
                    if timestamp > self.conf.mdtimestamp:
                        self.conf.mdtimestamp = timestamp

        if self.conf.groupfile:
            a = self.conf.groupfile
            if self.conf.split:
                a = os.path.join(self.package_dir, self.conf.groupfile)
            elif not os.path.isabs(a):
                a = os.path.join(self.package_dir, self.conf.groupfile)

            if not os.path.exists(a):
                raise MDError, _('Error: groupfile %s cannot be found.' % a)

            self.conf.groupfile = a

        if self.conf.cachedir:
            a = self.conf.cachedir
            if not os.path.isabs(a):
                a = os.path.join(self.conf.outputdir ,a)
            if not checkAndMakeDir(a):
                raise MDError, _('Error: cannot open/write to cache dir %s' % a)

            self.conf.cachedir = a


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
    def getFileList(self, directory, ext):
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
        startdir = directory + '/'
        self._os_path_walk(startdir, extension_visitor, filelist)
        return filelist

    def errorlog(self, thing):
        """subclass this if you want something different...."""
        errorprint(thing)
        
    def checkTimeStamps(self):
        """check the timestamp of our target dir. If it is not newer than the repodata
           return False, else True"""
        if self.conf.checkts:
            dn = os.path.join(self.conf.basedir, self.conf.directory)
            files = self.getFileList(dn, '.rpm')
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

    def _setup_old_metadata_lookup(self):
        """sets up the .oldData object for handling the --update call. Speeds
           up generating updates for new metadata"""
        #FIXME - this only actually works for single dirs. It will only
        # function for the first dir passed to --split, not all of them
        # this needs to be fixed by some magic in readMetadata.py
        # using opts.pkgdirs as a list, I think.
        if self.conf.update:
            #build the paths
            opts = {
                'verbose' : self.conf.verbose,
                'pkgdir'  : os.path.normpath(self.package_dir)
            }

            if self.conf.skip_stat:
                opts['do_stat'] = False

            if self.conf.update_md_path:
                old_repo_path = os.path.normpath(self.conf.update_md_path)
            else:
                old_repo_path = self.conf.outputdir

            #and scan the old repo
            self.oldData = readMetadata.MetadataIndex(old_repo_path, opts)

    def _setup_grabber(self):
        if not hasattr(self, '_grabber'):
            self._grabber = grabber.URLGrabber()
    
        return self._grabber

    grabber = property(fget = lambda self: self._setup_grabber())
    
    
    def doPkgMetadata(self):
        """all the heavy lifting for the package metadata"""
        if self.conf.update:
            self._setup_old_metadata_lookup()        
        # rpms we're going to be dealing with
        if self.conf.pkglist:
            packages = self.conf.pkglist
        else:
            packages = self.getFileList(self.package_dir, '.rpm')
        
        if not isinstance(packages, MetaSack):
            packages = self.trimRpms(packages)
        self.pkgcount = len(packages)
        self.openMetadataDocs()
        self.writeMetadataDocs(packages)
        self.closeMetadataDocs()

    # module
    def openMetadataDocs(self):
        if self.conf.database_only:
            self.setup_sqlite_dbs()
        else:
            self.primaryfile = self._setupPrimary()
            self.flfile = self._setupFilelists()
            self.otherfile = self._setupOther()
        if self.conf.deltas:
            self.deltafile = self._setupDelta()

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

    def _setupDelta(self):
        # setup the other file
        deltafilepath = os.path.join(self.conf.outputdir, self.conf.tempdir, self.conf.deltafile)
        fo = _gzipOpen(deltafilepath, 'w')
        fo.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        fo.write('<prestodelta>\n')
        return fo
        

    def read_in_package(self, rpmfile, pkgpath=None, reldir=None):
        """rpmfile == relative path to file from self.packge_dir"""
        remote_package = False
        baseurl = self.conf.baseurl

        if not pkgpath:
            pkgpath = self.package_dir

        if not rpmfile.strip():
            raise MDError, "Blank filename passed in, skipping"
            
        if rpmfile.find("://") != -1:
            remote_package = True
            
            if not hasattr(self, 'tempdir'):
                self.tempdir = tempfile.mkdtemp()
                
            pkgname = os.path.basename(rpmfile)
            baseurl = os.path.dirname(rpmfile)
            reldir = self.tempdir       
            dest = os.path.join(self.tempdir, pkgname)
            if not self.conf.quiet:
                self.callback.log('\nDownloading %s' % rpmfile)                        
            try:
                rpmfile = self.grabber.urlgrab(rpmfile, dest)
            except grabber.URLGrabError, e:
                raise MDError, "Unable to retrieve remote package %s: %s" %(rpmfile, e)

            
        else:
            rpmfile = '%s/%s' % (pkgpath, rpmfile)
            
        try:
            po = yumbased.CreateRepoPackage(self.ts, rpmfile)
        except Errors.MiscError, e:
            raise MDError, "Unable to open package: %s" % e
        # external info we need
        po._cachedir = self.conf.cachedir
        po._baseurl = baseurl
        po._reldir = reldir
        po._packagenumber = self.current_pkg
        for r in po.requires_print:
            if r.startswith('rpmlib('):
                self.rpmlib_reqs[r] = 1
           
        if po.checksum in (None, ""):
            raise MDError, "No Package ID found for package %s, not going to add it" % po
        
        return po

    def writeMetadataDocs(self, pkglist=[], pkgpath=None):

        if not pkglist:
            pkglist = self.conf.pkglist           

        if not pkgpath:
            directory=self.conf.directory
        else:
            directory=pkgpath

        for pkg in pkglist:
            self.current_pkg += 1
            recycled = False
            
            # look to see if we can get the data from the old repodata
            # if so write this one out that way
            if self.conf.update:
                #see if we can pull the nodes from the old repo
                #print self.oldData.basenodes.keys()
                old_pkg = pkg
                if pkg.find("://") != -1:
                    old_pkg = os.path.basename(pkg)
                nodes = self.oldData.getNodes(old_pkg)
                if nodes is not None:
                    recycled = True
                
                # FIXME also open up the delta file
            
            # otherwise do it individually
            if not recycled:
                #scan rpm files
                if not pkgpath:   
                    reldir = os.path.join(self.conf.basedir, directory)
                else:
                    reldir = pkgpath
                
                if not isinstance(pkg, YumAvailablePackage):

                    try:
                        po = self.read_in_package(pkg, pkgpath=pkgpath, reldir=reldir)
                    except MDError, e:
                        # need to say something here
                        self.callback.errorlog("\nError %s: %s\n" % (pkg, e))
                        continue
                    # we can use deltas:
                    presto_md = self._do_delta_rpm_package(po)
                    if presto_md:
                        self.deltafile.write(presto_md)

                else:
                    po = pkg

                if self.conf.database_only:
                    pass # disabled right now for sanity reasons (mine)
                    #po.do_sqlite_dump(self.md_sqlite)
                else:
                    self.primaryfile.write(po.xml_dump_primary_metadata())
                    self.flfile.write(po.xml_dump_filelists_metadata())
                    self.otherfile.write(po.xml_dump_other_metadata(
                              clog_limit=self.conf.changelog_limit))
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
                #FIXME - if we're in update and we have deltas enabled
                #        check the presto data for this pkg and write its info back out
                #       to our deltafile

            if not self.conf.quiet:
                if self.conf.verbose:
                    self.callback.log('%d/%d - %s' % (self.current_pkg, self.pkgcount, pkg))
                else:
                    self.callback.progress(pkg, self.current_pkg, self.pkgcount)

        return self.current_pkg


    def closeMetadataDocs(self):
        if not self.conf.quiet:
            self.callback.log('')

        
        # save them up to the tmp locations:
        if not self.conf.quiet:
            self.callback.log(_('Saving Primary metadata'))
        if self.conf.database_only:
            self.md_sqlite.pri_cx.close()
        else:
            self.primaryfile.write('\n</metadata>')
            self.primaryfile.close()

        if not self.conf.quiet:
            self.callback.log(_('Saving file lists metadata'))
        if self.conf.database_only:
            self.md_sqlite.file_cx.close()
        else:
            self.flfile.write('\n</filelists>')
            self.flfile.close()

        if not self.conf.quiet:
            self.callback.log(_('Saving other metadata'))
        if self.conf.database_only:
            self.md_sqlite.other_cx.close()
        else:
            self.otherfile.write('\n</otherdata>')
            self.otherfile.close()

        if self.conf.deltas:
            if not self.conf.quiet:
                self.callback.log(_('Saving delta metadata'))
            self.deltafile.write('\n</prestodelta>')
            self.deltafile.close()

    def _do_delta_rpm_package(self, pkg):
        """makes the drpms, if possible, for this package object.
           returns the presto/delta xml metadata as a string
        """

        results = u""
        thisdeltastart = u"""  <newpackage name="%s" epoch="%s" version="%s" release="%s" arch="%s">\n""" % (pkg.name,
                                     pkg.epoch, pkg.ver, pkg.release, pkg.arch)
        thisdeltaend = u"""  </newpackage>\n"""

        # generate a list of all the potential 'old rpms'
        opl = self._get_old_package_list()
        # get list of potential candidates which are likely to match
        pot_cand = []
        for fn in opl:
            if os.path.basename(fn).startswith(pkg.name):
                pot_cand.append(fn)
        
        candidates = []
        for fn in pot_cand:
            try:
                thispo = yumbased.CreateRepoPackage(self.ts, fn)
            except Errors.MiscError, e:
                continue
            if (thispo.name, thispo.arch) != (pkg.name, pkg.arch):
                # not the same, doesn't matter
                continue
            if thispo == pkg: #exactly the same, doesn't matter
                continue
            if thispo.EVR >= pkg.EVR: # greater or equal, doesn't matter
                continue
            candidates.append(thispo)
            candidates.sort()
            candidates.reverse()

        drpm_results = u""
        for delta_p in candidates[0:self.conf.num_deltas]:
            #make drpm of pkg and delta_p
            drpmfn = deltarpms.create_drpm(delta_p, pkg, self.conf.deltadir)

            if drpmfn:
                # TODO more sanity check the drpm for size, etc
                # make xml of drpm
                try:
                    drpm_po = yumbased.CreateRepoPackage(self.ts, drpmfn)
                except Errors.MiscError, e:
                    os.unlink(drpmfn)
                    continue
                rel_drpmfn = drpmfn.replace(self.conf.outputdir, '')
                if rel_drpmfn[0] == '/':
                    rel_drpmfn = rel_drpmfn[1:]
                if not self.conf.quiet:
                    if self.conf.verbose:
                        self.callback.log('created drpm from %s to %s: %s' % (
                            delta_p, pkg, drpmfn))

                drpm = deltarpms.DeltaRPMPackage(drpm_po, self.conf.outputdir, rel_drpmfn)
                drpm_results += to_unicode(drpm.xml_dump_metadata())
        
        if drpm_results:
            results = thisdeltastart + drpm_results + thisdeltaend
        
        return results

    def _get_old_package_list(self):
        if hasattr(self, '_old_package_list'):
            return self._old_package_list
        
        opl = []
        for d in self.conf.oldpackage_paths:
            for f in self.getFileList(d, 'rpm'):
                opl.append(d + '/' + f)
                    
        self._old_package_list = opl
        return self._old_package_list

    def addArbitraryMetadata(self, mdfile, mdtype, xml_node, compress=True, 
                                             compress_type='gzip', attribs={}):
        """add random metadata to the repodata dir and repomd.xml
           mdfile = complete path to file
           mdtype = the metadata type to use
           xml_node = the node of the repomd xml object to append this 
                      data onto
           compress = compress the file before including it
        """
        # copy the file over here
        sfile = os.path.basename(mdfile)
        fo = open(mdfile, 'r')
        outdir = os.path.join(self.conf.outputdir, self.conf.tempdir)
        if compress:
            if compress_type == 'gzip':
                sfile = '%s.gz' % sfile
                outfn = os.path.join(outdir, sfile)
                output = GzipFile(filename = outfn, mode='wb')
            elif compress_type == 'bzip2':
                sfile = '%s.bz2' % sfile
                outfn = os.path.join(outdir, sfile)
                output = BZ2File(filename = outfn, mode='wb')
        else:
            outfn  = os.path.join(outdir, sfile)
            output = open(outfn, 'w')
            
        output.write(fo.read())
        output.close()
        fo.seek(0)
        open_csum = misc.checksum(self.conf.sumtype, fo)
        fo.close()

        
        if self.conf.unique_md_filenames:
            (csum, outfn) = checksum_and_rename(outfn)
            sfile = os.path.basename(outfn)
        else:
            if compress:
                csum = misc.checksum(self.conf.sumtype, outfn)            
            else:
                csum = open_csum
            
        timest = os.stat(outfn)[8]

        # add all this garbage into the xml node like:
        data = xml_node.newChild(None, 'data', None)
        data.newProp('type', mdtype)
        location = data.newChild(None, 'location', None)
        if self.conf.baseurl is not None:
            location.newProp('xml:base', self.conf.baseurl)
        location.newProp('href', os.path.join(self.conf.finaldir, sfile))
        checksum = data.newChild(None, 'checksum', csum)
        checksum.newProp('type', self.conf.sumtype)
        if compress:
            opencsum = data.newChild(None, 'open-checksum', open_csum)
            opencsum.newProp('type', self.conf.sumtype)

        timestamp = data.newChild(None, 'timestamp', str(timest))

        # add the random stuff
        for (k,v) in attribs.items():
            data.newChild(None, k, str(v))
           
            
    def doRepoMetadata(self):
        """wrapper to generate the repomd.xml file that stores the info on the other files"""
        repodoc = libxml2.newDoc("1.0")
        reporoot = repodoc.newChild(None, "repomd", None)
        repons = reporoot.newNs('http://linux.duke.edu/metadata/repo', None)
        reporoot.setNs(repons)
        rpmns = reporoot.newNs("http://linux.duke.edu/metadata/rpm", 'rpm')        
        repopath = os.path.join(self.conf.outputdir, self.conf.tempdir)
        repofilepath = os.path.join(repopath, self.conf.repomdfile)
        
        revision = reporoot.newChild(None, 'revision', self.conf.revision)
        if self.conf.content_tags or self.conf.distro_tags:
            tags = reporoot.newChild(None, 'tags', None)
            for item in self.conf.content_tags:
                c_tags = tags.newChild(None, 'content', item)
            for (cpeid,item) in self.conf.distro_tags:
                d_tags = tags.newChild(None, 'distro', item)
                if cpeid:
                    d_tags.newProp('cpeid', cpeid)

        sumtype = self.conf.sumtype
        if self.conf.database_only:
            workfiles = []
            db_workfiles = [(self.md_sqlite.pri_sqlite_file, 'primary_db'),
                            (self.md_sqlite.file_sqlite_file, 'filelists_db'),
                            (self.md_sqlite.other_sqlite_file, 'other_db')]
            dbversion = '10'                            
        else:
            workfiles = [(self.conf.otherfile, 'other',),
                         (self.conf.filelistsfile, 'filelists'),
                         (self.conf.primaryfile, 'primary')]
            db_workfiles = []
            repoid='garbageid'
        
        if self.conf.deltas:
            workfiles.append((self.conf.deltafile, 'deltainfo'))
        if self.conf.database:
            if not self.conf.quiet: self.callback.log('Generating sqlite DBs')
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
                if self.conf.verbose:
                    self.callback.log("Starting %s db creation: %s" % (ftype, time.ctime()))
            
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

                if self.conf.unique_md_filenames:
                    csum_compressed_name = '%s-%s.bz2' % (db_compressed_sums[ftype], good_name)
                    csum_result_compressed =  os.path.join(repopath, csum_compressed_name)
                    os.rename(result_compressed, csum_result_compressed)
                    result_compressed = csum_result_compressed
                    compressed_name = csum_compressed_name
                    
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
                if self.conf.verbose:
                    self.callback.log("Ending %s db creation: %s" % (ftype, time.ctime()))
                

                
            data = reporoot.newChild(None, 'data', None)
            data.newProp('type', ftype)

            checksum = data.newChild(None, 'checksum', csum)
            checksum.newProp('type', sumtype)
            timestamp = data.newChild(None, 'timestamp', str(timestamp))
            unchecksum = data.newChild(None, 'open-checksum', uncsum)
            unchecksum.newProp('type', sumtype)
            location = data.newChild(None, 'location', None)
            if self.conf.baseurl is not None:
                location.newProp('xml:base', self.conf.baseurl)
            if self.conf.unique_md_filenames:
                res_file = '%s-%s.xml.gz' % (csum, ftype)
                orig_file = os.path.join(repopath, file)
                dest_file = os.path.join(repopath, res_file)
                os.rename(orig_file, dest_file)
                
            else:
                res_file = file

            file = res_file 
            
            location.newProp('href', os.path.join(self.conf.finaldir, file))


        if not self.conf.quiet and self.conf.database: self.callback.log('Sqlite DBs complete')        

        for (fn, ftype) in db_workfiles:
            attribs = {'database_version':dbversion}
            self.addArbitraryMetadata(fn, ftype, reporoot, compress=True, 
                                      compress_type='bzip2', attribs=attribs)
            try:
                os.unlink(fn)
            except (IOError, OSError), e:
                pass

            
        if self.conf.groupfile is not None:
            self.addArbitraryMetadata(self.conf.groupfile, 'group_gz', reporoot)
            self.addArbitraryMetadata(self.conf.groupfile, 'group', reporoot, compress=False)            
        
        if self.conf.additional_metadata:
            for md_type, mdfile in self.conf.additional_metadata.items():
                self.addArbitraryMetadata(mdfile, md_type, reporoot)

        # FIXME - disabled until we decide how best to use this
        #if self.rpmlib_reqs:
        #    rpmlib = reporoot.newChild(rpmns, 'lib', None)
        #    for r in self.rpmlib_reqs.keys():
        #        req  = rpmlib.newChild(rpmns, 'requires', r)
                
            
        # save it down
        try:
            repodoc.saveFormatFileEnc(repofilepath, 'UTF-8', 1)
        except:
            self.callback.errorlog(_('Error saving temp file for repomd.xml: %s') % repofilepath)
            raise MDError, 'Could not save temp file: %s' % repofilepath 

        del repodoc


    def doFinalMove(self):
        """move the just-created repodata from .repodata to repodata
           also make sure to preserve any files we didn't mess with in the 
           metadata dir"""
           
        output_final_dir = os.path.join(self.conf.outputdir, self.conf.finaldir) 
        output_old_dir = os.path.join(self.conf.outputdir, self.conf.olddir)
        
        if os.path.exists(output_final_dir):
            try:
                os.rename(output_final_dir, output_old_dir)
            except:
                raise MDError, _('Error moving final %s to old dir %s' % (output_final_dir,
                                                                     output_old_dir))

        output_temp_dir = os.path.join(self.conf.outputdir, self.conf.tempdir)

        try:
            os.rename(output_temp_dir, output_final_dir)
        except:
            # put the old stuff back
            os.rename(output_old_dir, output_final_dir)
            raise MDError, _('Error moving final metadata into place')

        for f in ['primaryfile', 'filelistsfile', 'otherfile', 'repomdfile', 'groupfile']:
            if getattr(self.conf, f):
                fn = os.path.basename(getattr(self.conf, f))
            else:
                continue
            oldfile = os.path.join(output_old_dir, fn)

            if os.path.exists(oldfile):
                try:
                    os.remove(oldfile)
                except OSError, e:
                    raise MDError, _('Could not remove old metadata file: %s: %s') % (oldfile, e)

        # Move everything else back from olddir (eg. repoview files)
        for f in os.listdir(output_old_dir):
            oldfile = os.path.join(output_old_dir, f)
            finalfile = os.path.join(output_final_dir, f)
            if f.find('-') != -1 and f.split('-')[1] in ('primary.sqlite.bz2',
                    'filelists.sqlite.bz2', 'primary.xml.gz','other.sqlite.bz2',
                    'other.xml.gz','filelists.xml.gz'):
                os.remove(oldfile) # kill off the old ones
                continue
            if f in ('filelists.sqlite.bz2', 'other.sqlite.bz2', 'primary.sqlite.bz2'):
                os.remove(oldfile)
                continue
                    
            if os.path.exists(finalfile):
                # Hmph?  Just leave it alone, then.
                try:
                    if os.path.isdir(oldfile):
                        shutil.rmtree(oldfile)
                    else:
                        os.remove(oldfile)
                except OSError, e:
                    raise MDError, _('Could not remove old metadata file: %s: %s') % (oldfile, e)
            else:
                try:
                    os.rename(oldfile, finalfile)
                except OSError, e:
                    msg = _('Could not restore old non-metadata file: %s -> %s') % (oldfile, finalfile)
                    msg += _('Error was %s') % e
                    raise MDError, msg

        try:
            os.rmdir(output_old_dir)
        except OSError, e:
            self.errorlog(_('Could not remove old metadata dir: %s') % self.conf.olddir)
            self.errorlog(_('Error was %s') % e)
            self.errorlog(_('Please clean up this directory manually.'))

    def setup_sqlite_dbs(self, initdb=True):
        """sets up the sqlite dbs w/table schemas and db_infos"""
        destdir = os.path.join(self.conf.outputdir, self.conf.tempdir)
        try:
            self.md_sqlite = MetaDataSqlite(destdir)
        except sqlite.OperationalError, e:
            raise MDError, _('Cannot create sqlite databases: %s.\nMaybe you need to clean up a .repodata dir?') % e
        
    
    
class SplitMetaDataGenerator(MetaDataGenerator):
    """takes a series of dirs and creates repodata for all of them
       most commonly used with -u media:// - if no outputdir is specified
       it will create the repodata in the first dir in the list of dirs
       """
    def __init__(self, config_obj=None, callback=None):
        MetaDataGenerator.__init__(self, config_obj=config_obj, callback=None)
        
    def _getFragmentUrl(self, url, fragment):
        import urlparse
        urlparse.uses_fragment.append('media')
        if not url:
            return url
        (scheme, netloc, path, query, fragid) = urlparse.urlsplit(url)
        return urlparse.urlunsplit((scheme, netloc, path, query, str(fragment)))

    def getFileList(self, directory, ext):

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
        os.path.walk(directory, extension_visitor, rpmlist)
        return rpmlist

    def doPkgMetadata(self):
        """all the heavy lifting for the package metadata"""
        if len(self.conf.directories) == 1:
            MetaDataGenerator.doPkgMetadata(self)
            return

        if self.conf.update:
            self._setup_old_metadata_lookup()
            
        filematrix = {}
        for mydir in self.conf.directories:
            if os.path.isabs(mydir):
                thisdir = mydir
            else:
                if mydir.startswith('../'):
                    thisdir = os.path.realpath(mydir)
                else:
                    thisdir = os.path.join(self.conf.basedir, mydir)
        
            filematrix[mydir] = self.getFileList(thisdir, '.rpm')
            self.trimRpms(filematrix[mydir])
            self.pkgcount += len(filematrix[mydir])

        mediano = 1
        self.current_pkg = 0
        self.conf.baseurl = self._getFragmentUrl(self.conf.baseurl, mediano)
        self.openMetadataDocs()
        original_basedir = self.conf.basedir
        for mydir in self.conf.directories:
            self.conf.baseurl = self._getFragmentUrl(self.conf.baseurl, mediano)
            self.writeMetadataDocs(filematrix[mydir], mydir)
            mediano += 1
        self.conf.baseurl = self._getFragmentUrl(self.conf.baseurl, 1)
        self.closeMetadataDocs()



class MetaDataSqlite(object):
    def __init__(self, destdir):
        self.pri_sqlite_file = os.path.join(destdir, 'primary.sqlite')
        self.pri_cx = sqlite.Connection(self.pri_sqlite_file)
        self.file_sqlite_file = os.path.join(destdir, 'filelists.sqlite')
        self.file_cx = sqlite.Connection(self.file_sqlite_file)
        self.other_sqlite_file = os.path.join(destdir, 'other.sqlite')
        self.other_cx = sqlite.Connection(self.other_sqlite_file)
        self.primary_cursor = self.pri_cx.cursor()

        self.filelists_cursor = self.file_cx.cursor()
        
        self.other_cursor = self.other_cx.cursor()
                
        self.create_primary_db()
        self.create_filelists_db()
        self.create_other_db()
        
    def create_primary_db(self):
        # make the tables
        schema = [
        """PRAGMA synchronous="OFF";""",
        """pragma locking_mode="EXCLUSIVE";""",
        """CREATE TABLE conflicts (  name TEXT,  flags TEXT,  epoch TEXT,  version TEXT,  release TEXT,  pkgKey INTEGER );""",
        """CREATE TABLE db_info (dbversion INTEGER, checksum TEXT);""",
        """CREATE TABLE files (  name TEXT,  type TEXT,  pkgKey INTEGER);""",
        """CREATE TABLE obsoletes (  name TEXT,  flags TEXT,  epoch TEXT,  version TEXT,  release TEXT,  pkgKey INTEGER );""",
        """CREATE TABLE packages (  pkgKey INTEGER PRIMARY KEY,  pkgId TEXT,  name TEXT,  arch TEXT,  version TEXT,  epoch TEXT,  release TEXT,  summary TEXT,  description TEXT,  url TEXT,  time_file INTEGER,  time_build INTEGER,  rpm_license TEXT,  rpm_vendor TEXT,  rpm_group TEXT,  rpm_buildhost TEXT,  rpm_sourcerpm TEXT,  rpm_header_start INTEGER,  rpm_header_end INTEGER,  rpm_packager TEXT,  size_package INTEGER,  size_installed INTEGER,  size_archive INTEGER,  location_href TEXT,  location_base TEXT,  checksum_type TEXT);""",
        """CREATE TABLE provides (  name TEXT,  flags TEXT,  epoch TEXT,  version TEXT,  release TEXT,  pkgKey INTEGER );""",
        """CREATE TABLE requires (  name TEXT,  flags TEXT,  epoch TEXT,  version TEXT,  release TEXT,  pkgKey INTEGER , pre BOOL DEFAULT FALSE);""",
        """CREATE INDEX filenames ON files (name);""",
        """CREATE INDEX packageId ON packages (pkgId);""",
        """CREATE INDEX packagename ON packages (name);""",
        """CREATE INDEX pkgconflicts on conflicts (pkgKey);""",
        """CREATE INDEX pkgobsoletes on obsoletes (pkgKey);""",
        """CREATE INDEX pkgprovides on provides (pkgKey);""",
        """CREATE INDEX pkgrequires on requires (pkgKey);""",
        """CREATE INDEX providesname ON provides (name);""",
        """CREATE INDEX requiresname ON requires (name);""",
        """CREATE TRIGGER removals AFTER DELETE ON packages  
             BEGIN    
             DELETE FROM files WHERE pkgKey = old.pkgKey;    
             DELETE FROM requires WHERE pkgKey = old.pkgKey;    
             DELETE FROM provides WHERE pkgKey = old.pkgKey;    
             DELETE FROM conflicts WHERE pkgKey = old.pkgKey;    
             DELETE FROM obsoletes WHERE pkgKey = old.pkgKey;
             END;""",
         """INSERT into db_info values (%s, 'direct_create');""" % sqlitecachec.DBVERSION,
             ]
        
        for cmd in schema:
            executeSQL(self.primary_cursor, cmd)

    def create_filelists_db(self):
        schema = [
            """PRAGMA synchronous="0FF";""",
            """pragma locking_mode="EXCLUSIVE";""",
            """CREATE TABLE db_info (dbversion INTEGER, checksum TEXT);""",
            """CREATE TABLE filelist (  pkgKey INTEGER,  dirname TEXT,  filenames TEXT,  filetypes TEXT);""",
            """CREATE TABLE packages (  pkgKey INTEGER PRIMARY KEY,  pkgId TEXT);""",
            """CREATE INDEX dirnames ON filelist (dirname);""",
            """CREATE INDEX keyfile ON filelist (pkgKey);""",
            """CREATE INDEX pkgId ON packages (pkgId);""",
            """CREATE TRIGGER remove_filelist AFTER DELETE ON packages  
                   BEGIN    
                   DELETE FROM filelist WHERE pkgKey = old.pkgKey;  
                   END;""",
         """INSERT into db_info values (%s, 'direct_create');""" % sqlitecachec.DBVERSION,                   
            ]
        for cmd in schema:
            executeSQL(self.filelists_cursor, cmd)
        
    def create_other_db(self):
        schema = [
            """PRAGMA synchronous="OFF";""",
            """pragma locking_mode="EXCLUSIVE";""",
            """CREATE TABLE changelog (  pkgKey INTEGER,  author TEXT,  date INTEGER,  changelog TEXT);""",
            """CREATE TABLE db_info (dbversion INTEGER, checksum TEXT);""",
            """CREATE TABLE packages (  pkgKey INTEGER PRIMARY KEY,  pkgId TEXT);""",
            """CREATE INDEX keychange ON changelog (pkgKey);""",
            """CREATE INDEX pkgId ON packages (pkgId);""",
            """CREATE TRIGGER remove_changelogs AFTER DELETE ON packages  
                 BEGIN    
                 DELETE FROM changelog WHERE pkgKey = old.pkgKey;  
                 END;""",
         """INSERT into db_info values (%s, 'direct_create');""" % sqlitecachec.DBVERSION,                 
            ]
            
        for cmd in schema:
            executeSQL(self.other_cursor, cmd)

