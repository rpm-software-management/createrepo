import exceptions
import os
import sys
import libxml2
import string
import fnmatch
import hashlib
import rpm
import yumbased


from yum import misc
from utils import _
import readMetadata

try:
    import sqlitecachec
except ImportError:
    pass


from utils import _gzipOpen, bzipFile


__version__ = '0.9'


class MDError(exceptions.Exception):
    def __init__(self, value=None):
        exceptions.Exception.__init__(self)
        self.value = value
    
    def __str__(self):
        return self.value


class MetaDataGenerator:
    def __init__(self, cmds):
        self.cmds = cmds
        self.ts = rpm.TransactionSet()
        self.pkgcount = 0
        self.files = []

    # module
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
                if self.cmds['skip-symlinks'] and os.path.islink(fn):
                    continue
                elif fn[-extlen:].lower() == '%s' % (ext):
                    relativepath = dirname.replace(startdir, "", 1)
                    relativepath = relativepath.lstrip("/")
                    filelist.append(os.path.join(relativepath,fn))

        filelist = []
        startdir = os.path.join(basepath, directory) + '/'
        self._os_path_walk(startdir, extension_visitor, filelist)
        return filelist
    #module
    def checkTimeStamps(self, directory):
        if self.cmds['checkts']:
            files = self.getFileList(self.cmds['basedir'], directory, '.rpm')
            files = self.trimRpms(files)
            for f in files:
                fn = os.path.join(self.cmds['basedir'], directory, f)
                if not os.path.exists(fn):
                    errorprint(_('cannot get to file: %s') % fn)
                if os.path.getctime(fn) > self.cmds['mdtimestamp']:
                    return False
        return True
    #module
    def trimRpms(self, files):
        badrpms = []
        for file in files:
            for glob in self.cmds['excludes']:
                if fnmatch.fnmatch(file, glob):
                    # print 'excluded: %s' % file
                    if file not in badrpms:
                        badrpms.append(file)
        for file in badrpms:
            if file in files:
                files.remove(file)
        return files

    def doPkgMetadata(self, directory):
        """all the heavy lifting for the package metadata"""

        # rpms we're going to be dealing with
        if self.cmds['update']:
            #build the paths
            primaryfile = os.path.join(self.cmds['outputdir'], self.cmds['finaldir'], self.cmds['primaryfile'])
            flfile = os.path.join(self.cmds['outputdir'], self.cmds['finaldir'], self.cmds['filelistsfile'])
            otherfile = os.path.join(self.cmds['outputdir'], self.cmds['finaldir'], self.cmds['otherfile'])
            opts = {
                'verbose' : self.cmds['verbose'],
                'pkgdir' : os.path.normpath(os.path.join(self.cmds['basedir'], directory))
            }
            #and scan the old repo
            self.oldData = readMetadata.MetadataIndex(self.cmds['outputdir'],
                                                      primaryfile, flfile, otherfile, opts)
        if self.cmds['pkglist']:
            packages = self.cmds['pkglist']
        else:
            packages = self.getFileList(self.cmds['basedir'], directory, '.rpm')
            
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
        primaryfilepath = os.path.join(self.cmds['outputdir'], self.cmds['tempdir'], self.cmds['primaryfile'])
        fo = _gzipOpen(primaryfilepath, 'w')
        fo.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        fo.write('<metadata xmlns="http://linux.duke.edu/metadata/common" xmlns:rpm="http://linux.duke.edu/metadata/rpm" packages="%s">\n' %
                       self.pkgcount)
        return fo

    def _setupFilelists(self):
        # setup the filelist file
        filelistpath = os.path.join(self.cmds['outputdir'], self.cmds['tempdir'], self.cmds['filelistsfile'])
        fo = _gzipOpen(filelistpath, 'w')
        fo.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        fo.write('<filelists xmlns="http://linux.duke.edu/metadata/filelists" packages="%s">\n' %
                       self.pkgcount)
        return fo
        
    def _setupOther(self):
        # setup the other file
        otherfilepath = os.path.join(self.cmds['outputdir'], self.cmds['tempdir'], self.cmds['otherfile'])
        fo = _gzipOpen(otherfilepath, 'w')
        fo.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        fo.write('<otherdata xmlns="http://linux.duke.edu/metadata/other" packages="%s">\n' %
                       self.pkgcount)
        return fo
        
    def _getNodes(self, pkg, directory, current):
        # delete function since it seems to nothing anymore
        basenode = None
        filesnode = None
        othernode = None
        try:
            rpmdir= os.path.join(self.cmds['basedir'], directory)
            mdobj = dumpMetadata.RpmMetaData(self.ts, rpmdir, pkg, self.cmds)
        except dumpMetadata.MDError, e:
            errorprint('\n%s - %s' % (e, pkg))
            return None
        try:
            basenode = dumpMetadata.generateXML(self.basedoc, self.baseroot, self.formatns, mdobj, self.cmds['sumtype'])
        except dumpMetadata.MDError, e:
            errorprint(_('\nAn error occurred creating primary metadata: %s') % e)
            return None
        try:
            filesnode = dumpMetadata.fileListXML(self.filesdoc, self.filesroot, mdobj)
        except dumpMetadata.MDError, e:
            errorprint(_('\nAn error occurred creating filelists: %s') % e)
            return None
        try:
            othernode = dumpMetadata.otherXML(self.otherdoc, self.otherroot, mdobj)
        except dumpMetadata.MDError, e:
            errorprint(_('\nAn error occurred: %s') % e)
            return None
        return basenode,filesnode,othernode

    def read_in_package(self, directory, rpmfile):
        # XXX fixme try/excepts here
        # directory is stupid - just make it part of the class
        rpmfile = '%s/%s/%s' % (self.cmds['basedir'], directory, rpmfile)
        po = yumbased.CreateRepoPackage(self.ts, rpmfile)
        return po

    def writeMetadataDocs(self, pkglist, directory, current=0):
        # FIXME
        # directory is unused, kill it, pkglist should come from self
        # I don't see why current needs to be this way at all
        for pkg in pkglist:
            current+=1
            recycled = False
            sep = '-'
            
            # look to see if we can get the data from the old repodata
            # if so write this one out that way
            if self.cmds['update']:
                #see if we can pull the nodes from the old repo
                nodes = self.oldData.getNodes(pkg)
                if nodes is not None:
                    recycled = True

            
            # otherwise do it individually
            if not recycled:
                #scan rpm files
                po = self.read_in_package(directory, pkg)
                self.primaryfile.write(po.do_primary_xml_dump())
                self.flfile.write(po.do_filelists_xml_dump())
                self.otherfile.write(po.do_other_xml_dump())
            else:
                sep = '*'
                primarynode, filenode, othernode = nodes    

                for node, outfile in ((primarynode,self.primaryfile),
                                      (filenode,self.flfile),
                                      (othernode,self.otherfile)):
                    if node is None:
                        break
                    output = node.serialize('UTF-8', self.cmds['pretty'])
                    outfile.write(output)
                    outfile.write('\n')
  
                    self.oldData.freeNodes(pkg)

            if not self.cmds['quiet']:
                if self.cmds['verbose']:
                    print '%d/%d %s %s' % (current, self.pkgcount, sep, pkg)
                else:
                    sys.stdout.write('\r' + ' ' * 80)
                    sys.stdout.write("\r%d/%d %s %s" % (current, self.pkgcount, sep, pkg))
                    sys.stdout.flush()

        return current


    def closeMetadataDocs(self):
        if not self.cmds['quiet']:
            print ''

        # save them up to the tmp locations:
        if not self.cmds['quiet']:
            print _('Saving Primary metadata')
        self.primaryfile.write('\n</metadata>')
        self.primaryfile.close()

        if not self.cmds['quiet']:
            print _('Saving file lists metadata')
        self.flfile.write('\n</filelists>')
        self.flfile.close()

        if not self.cmds['quiet']:
            print _('Saving other metadata')
        self.otherfile.write('\n</otherdata>')
        self.otherfile.close()

    def doRepoMetadata(self):
        """wrapper to generate the repomd.xml file that stores the info on the other files"""
        repodoc = libxml2.newDoc("1.0")
        reporoot = repodoc.newChild(None, "repomd", None)
        repons = reporoot.newNs('http://linux.duke.edu/metadata/repo', None)
        reporoot.setNs(repons)
        repofilepath = os.path.join(self.cmds['outputdir'], self.cmds['tempdir'], self.cmds['repomdfile'])

        try:
            repoXML(reporoot, self.cmds)
        except MDError, e:
            errorprint(_('Error generating repo xml file: %s') % e)
            sys.exit(1)

        try:
            repodoc.saveFormatFileEnc(repofilepath, 'UTF-8', 1)
        except:
            errorprint(_('Error saving temp file for rep xml: %s') % repofilepath)
            sys.exit(1)

        del repodoc

class SplitMetaDataGenerator(MetaDataGenerator):

    def __init__(self, cmds):
        MetaDataGenerator.__init__(self, cmds)

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

    def doPkgMetadata(self, directories):
        """all the heavy lifting for the package metadata"""
        import types
        if type(directories) == types.StringType:
            MetaDataGenerator.doPkgMetadata(self, directories)
            return
        filematrix = {}
        for mydir in directories:
            filematrix[mydir] = self.getFileList(self.cmds['basedir'], mydir, '.rpm')
            self.trimRpms(filematrix[mydir])
            self.pkgcount += len(filematrix[mydir])

        mediano = 1
        current = 0
        self.cmds['baseurl'] = self._getFragmentUrl(self.cmds['baseurl'], mediano)
        self.openMetadataDocs()
        original_basedir = self.cmds['basedir']
        for mydir in directories:
            self.cmds['baseurl'] = self._getFragmentUrl(self.cmds['baseurl'], mediano)
            current = self.writeMetadataDocs(filematrix[mydir], mydir, current)
            mediano += 1
        self.cmds['baseurl'] = self._getFragmentUrl(self.cmds['baseurl'], 1)
        self.closeMetadataDocs()



def repoXML(node, cmds):
    """generate the repomd.xml file that stores the info on the other files"""
    sumtype = cmds['sumtype']
    workfiles = [(cmds['otherfile'], 'other',),
                 (cmds['filelistsfile'], 'filelists'),
                 (cmds['primaryfile'], 'primary')]
    repoid='garbageid'
    
    repopath = os.path.join(cmds['outputdir'], cmds['tempdir'])
    
    if cmds['database']:
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
        
        if cmds['database']:
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
            data = node.newChild(None, 'data', None)
            data.newProp('type', db_data_type)
            location = data.newChild(None, 'location', None)
            if cmds['baseurl'] is not None:
                location.newProp('xml:base', cmds['baseurl'])
            
            location.newProp('href', os.path.join(cmds['finaldir'], compressed_name))
            checksum = data.newChild(None, 'checksum', db_compressed_sums[ftype])
            checksum.newProp('type', sumtype)
            db_tstamp = data.newChild(None, 'timestamp', str(db_timestamp))
            unchecksum = data.newChild(None, 'open-checksum', db_csums[ftype])
            unchecksum.newProp('type', sumtype)
            database_version = data.newChild(None, 'database_version', dbversion)
            
            
        data = node.newChild(None, 'data', None)
        data.newProp('type', ftype)
        location = data.newChild(None, 'location', None)
        if cmds['baseurl'] is not None:
            location.newProp('xml:base', cmds['baseurl'])
        location.newProp('href', os.path.join(cmds['finaldir'], file))
        checksum = data.newChild(None, 'checksum', csum)
        checksum.newProp('type', sumtype)
        timestamp = data.newChild(None, 'timestamp', str(timestamp))
        unchecksum = data.newChild(None, 'open-checksum', uncsum)
        unchecksum.newProp('type', sumtype)
    
    # if we've got a group file then checksum it once and be done
    if cmds['groupfile'] is not None:
        grpfile = cmds['groupfile']
        timestamp = os.stat(grpfile)[8]
        sfile = os.path.basename(grpfile)
        fo = open(grpfile, 'r')
        output = open(os.path.join(cmds['outputdir'], cmds['tempdir'], sfile), 'w')
        output.write(fo.read())
        output.close()
        fo.seek(0)
        csum = misc.checksum(sumtype, fo)
        fo.close()

        data = node.newChild(None, 'data', None)
        data.newProp('type', 'group')
        location = data.newChild(None, 'location', None)
        if cmds['baseurl'] is not None:
            location.newProp('xml:base', cmds['baseurl'])
        location.newProp('href', os.path.join(cmds['finaldir'], sfile))
        checksum = data.newChild(None, 'checksum', csum)
        checksum.newProp('type', sumtype)
        timestamp = data.newChild(None, 'timestamp', str(timestamp))


