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
import time
import yumbased


from yum import misc, Errors
import rpmUtils.transaction
from utils import _
import readMetadata

try:
    import sqlitecachec
except ImportError:
    pass


from utils import _gzipOpen, bzipFile, checkAndMakeDir, GzipFile, checksum_and_rename


__version__ = '0.9.4'



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
        self.baseurl = None
        self.groupfile = None
        self.sumtype = 'sha'
        self.noepoch = False # hmm - maybe a fixme?
        self.pretty = False
        self.cachedir = None 
        self.use_cache = False
        self.basedir = os.getcwd()
        self.checkts = False
        self.split = False        
        self.update = False
        self.skip_stat = False
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
        self.changelog_limit = None # needs to be an int or None
        self.unique_md_filenames = False
        

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
        self.files = []
        
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

        if os.path.exists(os.path.join(self.conf.outputdir, self.conf.olddir)):
            raise MDError, _('Old data directory exists, please remove: %s') % self.conf.olddir

        # make sure we can write to where we want to write to:
        # and pickup the mdtimestamps while we're at it
        for direc in ['tempdir', 'finaldir']:
            for f in ['primaryfile', 'filelistsfile', 'otherfile', 'repomdfile']:
                filepath = os.path.join(self.conf.outputdir, direc, f)
                if os.path.exists(filepath):
                    if not os.access(filepath, os.W_OK):
                        raise MDError, _('error in must be able to write to metadata files:\n  -> %s') % filepath

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
                errorprint(_('Error: cannot open/write to cache dir %s' % a))
                parser.print_usage()
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

    def _setup_old_metadata_lookup(self):
        """sets up the .oldData object for handling the --update call. Speeds
           up generating updates for new metadata"""
        #FIXME - this only actually works for single dirs. It will only
        # function for the first dir passed to --split, not all of them
        # this needs to be fixed by some magic in readMetadata.py
        # using opts.pkgdirs as a list, I think.
        # FIXME - this needs to read the old repomd.xml to figure out where
        # the files WERE to pass in the right fns.
        if self.conf.update:
            #build the paths
            opts = {
                'verbose' : self.conf.verbose,
                'pkgdir'  : os.path.normpath(self.package_dir)
            }
            if self.conf.skip_stat:
                opts['do_stat'] = False
                
            #and scan the old repo
            self.oldData = readMetadata.MetadataIndex(self.conf.outputdir, opts)
           
    def doPkgMetadata(self):
        """all the heavy lifting for the package metadata"""
        if self.conf.update:
            self._setup_old_metadata_lookup()        
        # rpms we're going to be dealing with
        if self.conf.pkglist:
            packages = self.conf.pkglist
        else:
            packages = self.getFileList(self.package_dir, '.rpm')
            
        packages = self.trimRpms(packages)
        self.pkgcount = len(packages)
        self.openMetadataDocs()
        self.writeMetadataDocs(packages)
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
        

    def read_in_package(self, rpmfile, pkgpath=None):
        """rpmfile == relative path to file from self.packge_dir"""
        if not pkgpath:
            pkgpath = self.package_dir

        rpmfile = '%s/%s' % (pkgpath, rpmfile)
        try:
            po = yumbased.CreateRepoPackage(self.ts, rpmfile)
        except Errors.MiscError, e:
            raise MDError, "Unable to open package: %s" % e
        # if we're going to add anything in from outside, here is where
        # you can do it
        po.crp_changelog_limit = self.conf.changelog_limit
        po.crp_cachedir = self.conf.cachedir
        return po

    def writeMetadataDocs(self, pkglist=[], pkgpath=None, current=0):

        if not pkglist:
            pkglist = self.conf.pkglist           
        if not pkgpath:
            directory=self.conf.directory
        else:
            directory=pkgpath

        for pkg in pkglist:
            current+=1
            recycled = False

            # look to see if we can get the data from the old repodata
            # if so write this one out that way
            if self.conf.update:
                #see if we can pull the nodes from the old repo
                #print self.oldData.basenodes.keys()
                nodes = self.oldData.getNodes(pkg)
                if nodes is not None:
                    recycled = True

            
            # otherwise do it individually
            if not recycled:
                #scan rpm files
                try:
                    po = self.read_in_package(pkg, pkgpath=pkgpath)
                except MDError, e:
                    # need to say something here
                    self.callback.errorlog("\nError %s: %s\n" % (pkg, e))
                    continue
                if not pkgpath:
                    reldir = os.path.join(self.conf.basedir, directory)
                else:
                    reldir = pkgpath
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

    def addArbitraryMetadata(self, mdfile, mdtype, xml_node, compress=True):
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
            sfile = '%s.gz' % sfile
            outfn = os.path.join(outdir, sfile)
            output = GzipFile(filename = outfn, mode='wb')
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


        if self.conf.groupfile is not None:
            self.addArbitraryMetadata(self.conf.groupfile, 'group_gz', reporoot)
            self.addArbitraryMetadata(self.conf.groupfile, 'group', reporoot, compress=False)            

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
        current = 0
        self.conf.baseurl = self._getFragmentUrl(self.conf.baseurl, mediano)
        self.openMetadataDocs()
        original_basedir = self.conf.basedir
        for mydir in self.conf.directories:
            self.conf.baseurl = self._getFragmentUrl(self.conf.baseurl, mediano)
            current = self.writeMetadataDocs(filematrix[mydir], mydir, current)
            mediano += 1
        self.conf.baseurl = self._getFragmentUrl(self.conf.baseurl, 1)
        self.closeMetadataDocs()




