#!/usr/bin/python -t
# primary functions and glue for generating the repository metadata
#

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
# Copyright 2004 Duke University

# $Id$


import os
import sys
import getopt
import rpm
import libxml2
import string
import fnmatch
import urlgrabber

import dumpMetadata
from dumpMetadata import _gzipOpen
__version__ = '0.4.3'

def errorprint(stuff):
    print >> sys.stderr, stuff

def _(args):
    """Stub function for translation"""
    return args

def usage(retval=1):
    print _("""
    createrepo [options] directory-of-packages

    Options:
     -u, --baseurl = optional base url location for all files
     -x, --exclude = files globs to exclude, can be specified multiple times
     -q, --quiet = run quietly
     -g, --groupfile <filename> to point to for group information (precreated)
                    (<filename> relative to directory-of-packages)
     -v, --verbose = run verbosely
     -c, --cachedir <dir> = specify which dir to use for the checksum cache
     -U, --update-info-location <url> = acquire package update metadata
     -h, --help = show this help
     -V, --version = output version
     -p, --pretty = output xml files in pretty format.
    """)

    sys.exit(retval)

class MetaDataGenerator:
    def __init__(self, cmds):
        self.cmds = cmds
        self.ts = rpm.TransactionSet()
        self.pkgcount = 0
        self.files = []

    def getFileList(self, basepath, path, ext, filelist):
        """Return all files in path matching ext, store them in filelist,
        recurse dirs. Returns a list object"""

        extlen = len(ext)
        totalpath = os.path.normpath(os.path.join(basepath, path))
        try:
            dir_list = os.listdir(totalpath)
        except OSError, e:
            errorprint(_('Error accessing directory %s, %s') % (totalpath, e))
            sys.exit(1)

        for d in dir_list:
            if os.path.isdir(totalpath + '/' + d):
                filelist = self.getFileList(basepath, os.path.join(path, d), ext, filelist)
            else:
                if string.lower(d[-extlen:]) == '%s' % (ext):
                    if totalpath.find(basepath) == 0:
                        relativepath = totalpath.replace(basepath, "", 1)
                        relativepath = relativepath.lstrip("/")
                        filelist.append(os.path.join(relativepath, d))
                    else:
                        raise "basepath '%s' not found in path '%s'" % (basepath, totalpath)

        return filelist


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
        files = self.getFileList(self.cmds['basedir'], directory, '.rpm', [])
        files = self.trimRpms(files)
        self.pkgcount = len(files)
        self.openMetadataDocs()
        self.writeMetadataDocs(files)
        self.closeMetadataDocs()


    def openMetadataDocs(self):
        self._setupBase()
        self._setupFilelists()
        self._setupOther()

    def _setupBase(self):
        # setup the base metadata doc
        self.basedoc = libxml2.newDoc("1.0")
        self.baseroot =  self.basedoc.newChild(None, "metadata", None)
        basens = self.baseroot.newNs('http://linux.duke.edu/metadata/common', None)
        self.formatns = self.baseroot.newNs('http://linux.duke.edu/metadata/rpm', 'rpm')
        self.baseroot.setNs(basens)
        basefilepath = os.path.join(self.cmds['basedir'], self.cmds['tempdir'], self.cmds['primaryfile'])
        self.basefile = _gzipOpen(basefilepath, 'w')
        self.basefile.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        self.basefile.write('<metadata xmlns="http://linux.duke.edu/metadata/common" xmlns:rpm="http://linux.duke.edu/metadata/rpm" packages="%s">\n' %
                       self.pkgcount)

    def _setupFilelists(self):
        # setup the file list doc
        self.filesdoc = libxml2.newDoc("1.0")
        self.filesroot = self.filesdoc.newChild(None, "filelists", None)
        filesns = self.filesroot.newNs('http://linux.duke.edu/metadata/filelists', None)
        self.filesroot.setNs(filesns)
        filelistpath = os.path.join(self.cmds['basedir'], self.cmds['tempdir'], self.cmds['filelistsfile'])
        self.flfile = _gzipOpen(filelistpath, 'w')
        self.flfile.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        self.flfile.write('<filelists xmlns="http://linux.duke.edu/metadata/filelists" packages="%s">\n' %
                       self.pkgcount)

    def _setupOther(self):
        # setup the other doc
        self.otherdoc = libxml2.newDoc("1.0")
        self.otherroot = self.otherdoc.newChild(None, "otherdata", None)
        otherns = self.otherroot.newNs('http://linux.duke.edu/metadata/other', None)
        self.otherroot.setNs(otherns)
        otherfilepath = os.path.join(self.cmds['basedir'], self.cmds['tempdir'], self.cmds['otherfile'])
        self.otherfile = _gzipOpen(otherfilepath, 'w')
        self.otherfile.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        self.otherfile.write('<otherdata xmlns="http://linux.duke.edu/metadata/other" packages="%s">\n' %
                       self.pkgcount)

    def writeMetadataDocs(self, files, current=0):
        for file in files:
            current+=1
            try:
                mdobj = dumpMetadata.RpmMetaData(self.ts, self.cmds['basedir'], file, self.cmds)
                if not self.cmds['quiet']:
                    if self.cmds['verbose']:
                        print '%d/%d - %s' % (current, len(files), file)
                    else:
                        sys.stdout.write('\r' + ' ' * 80)
                        sys.stdout.write("\r%d/%d - %s" % (current, self.pkgcount, file))
                        sys.stdout.flush()
            except dumpMetadata.MDError, e:
                errorprint('\n%s - %s' % (e, file))
                continue
            else:
                try:
                    node = dumpMetadata.generateXML(self.basedoc, self.baseroot, self.formatns, mdobj, self.cmds['sumtype'])
                except dumpMetadata.MDError, e:
                    errorprint(_('\nAn error occurred creating primary metadata: %s') % e)
                    continue
                else:
                    try:
                        # Fetch the update metadata for this package
                        if self.cmds['update-info-location']:
                            metadata = urlgrabber.urlopen(
                                    self.cmds['update-info-location'] +
                                    '?pkg=%s' % file)
                            filename = file.replace('.rpm', '.xml')
                            metadata.filename = os.path.join(
                                    self.cmds['basedir'], self.cmds['tempdir'],
                                    self.cmds['update-info-dir'], filename)
                            metadata._do_grab()
                            metadata.close()

                            # Get the update ID from the metadata
                            md = libxml2.parseFile(metadata.filename)
                            update_root = md.children
                            update = node.newChild(None, 'update', None)
                            update.newProp('id', update_root.prop('id'))
                            update.newProp('location', os.path.join(
                                    self.cmds['update-info-dir'], filename))
                            del md, metadata
                    except Exception, e:
                        pass
                    output = node.serialize('UTF-8', self.cmds['pretty'])
                    self.basefile.write(output)
                    self.basefile.write('\n')
                    node.unlinkNode()
                    node.freeNode()
                    del node

                try:
                    node = dumpMetadata.fileListXML(self.filesdoc, self.filesroot, mdobj)
                except dumpMetadata.MDError, e:
                    errorprint(_('\nAn error occurred creating filelists: %s') % e)
                    continue
                else:
                    output = node.serialize('UTF-8', self.cmds['pretty'])
                    self.flfile.write(output)
                    self.flfile.write('\n')
                    node.unlinkNode()
                    node.freeNode()
                    del node

                try:
                    node = dumpMetadata.otherXML(self.otherdoc, self.otherroot, mdobj)
                except dumpMetadata.MDError, e:
                    errorprint(_('\nAn error occurred: %s') % e)
                    continue
                else:
                    output = node.serialize('UTF-8', self.cmds['pretty'])
                    self.otherfile.write(output)
                    self.otherfile.write('\n')
                    node.unlinkNode()
                    node.freeNode()
                    del node
        return current


    def closeMetadataDocs(self):
        if not self.cmds['quiet']:
            print ''

        # save them up to the tmp locations:
        if not self.cmds['quiet']:
            print _('Saving Primary metadata')
        self.basefile.write('\n</metadata>')
        self.basefile.close()
        self.basedoc.freeDoc()

        if not self.cmds['quiet']:
            print _('Saving file lists metadata')
        self.flfile.write('\n</filelists>')
        self.flfile.close()
        self.filesdoc.freeDoc()

        if not self.cmds['quiet']:
            print _('Saving other metadata')
        self.otherfile.write('\n</otherdata>')
        self.otherfile.close()
        self.otherdoc.freeDoc()

    def doRepoMetadata(self):
        """wrapper to generate the repomd.xml file that stores the info on the other files"""
        repodoc = libxml2.newDoc("1.0")
        reporoot = repodoc.newChild(None, "repomd", None)
        repons = reporoot.newNs('http://linux.duke.edu/metadata/repo', None)
        reporoot.setNs(repons)
        repofilepath = os.path.join(self.cmds['basedir'], self.cmds['tempdir'], self.cmds['repomdfile'])

        try:
            dumpMetadata.repoXML(reporoot, self.cmds)
        except dumpMetadata.MDError, e:
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
        self.initialdir = self.cmds['basedir']

    def _getFragmentUrl(self, url, fragment):
        import urlparse
        urlparse.uses_fragment.append('media')
        if not url:
            return url
        (scheme, netloc, path, query, fragid) = urlparse.urlsplit(url)
        return urlparse.urlunsplit((scheme, netloc, path, query, str(fragment)))

    def doPkgMetadata(self, directories):
        """all the heavy lifting for the package metadata"""
        import types
        if type(directories) == types.StringType:
            MetaDataGenerator.doPkgMetadata(self, directories)
            return
        filematrix = {}
        for mydir in directories:
            filematrix[mydir] = self.getFileList(os.path.join(self.initialdir, mydir), '.', '.rpm', [])
            self.trimRpms(filematrix[mydir])
            self.pkgcount += len(filematrix[mydir])

        mediano = 1
        current = 0
        self.cmds['baseurl'] = self._getFragmentUrl(self.cmds['baseurl'], mediano)
        self.cmds['basedir'] = os.path.join(self.initialdir, directories[0])
        self.openMetadataDocs()
        for mydir in directories:
            self.cmds['basedir'] = os.path.join(self.initialdir, mydir)
            self.cmds['baseurl'] = self._getFragmentUrl(self.cmds['baseurl'], mediano)
            current = self.writeMetadataDocs(filematrix[mydir], current)
            mediano += 1
        self.cmds['basedir'] = os.path.join(self.initialdir, directories[0])
        self.cmds['baseurl'] = self._getFragmentUrl(self.cmds['baseurl'], 1)
        self.closeMetadataDocs()


def checkAndMakeDir(dir):
    """
     check out the dir and make it, if possible, return 1 if done, else return 0
    """
    if os.path.exists(dir):
        if not os.path.isdir(dir):
            errorprint(_('%s is not a dir') % dir)
            result = False
        else:
            if not os.access(dir, os.W_OK):
                errorprint(_('%s is not writable') % dir)
                result = False
            else:
                result = True
    else:
        try:
            os.mkdir(dir)
        except OSError, e:
            errorprint(_('Error creating dir %s: %s') % (dir, e))
            result = False
        else:
            result = True
    return result

def parseArgs(args):
    """
       Parse the command line args return a commands dict and directory.
       Sanity check all the things being passed in.
    """
    cmds = {}
    cmds['quiet'] = 0
    cmds['verbose'] = 0
    cmds['excludes'] = []
    cmds['baseurl'] = None
    cmds['groupfile'] = None
    cmds['sumtype'] = 'sha'
    cmds['pretty'] = 0
#    cmds['updategroupsonly'] = 0
    cmds['cachedir'] = None
    cmds['basedir'] = os.getcwd()
    cmds['cache'] = False
    cmds['split'] = False
    cmds['file-pattern-match'] = ['.*bin\/.*', '^\/etc\/.*', '^\/usr\/lib\/sendmail$']
    cmds['dir-pattern-match'] = ['.*bin\/.*', '^\/etc\/.*']

    try:
        gopts, argsleft = getopt.getopt(args, 'phqVvg:s:x:u:c:U:', ['help', 'exclude=',
                                                                  'quiet', 'verbose', 'cachedir=', 'basedir=',
                                                                  'baseurl=', 'groupfile=', 'checksum=',
                                                                  'version', 'pretty', 'split',
                                                                  'update-info-location='])
    except getopt.error, e:
        errorprint(_('Options Error: %s.') % e)
        usage()

    try:
        for arg,a in gopts:
            if arg in ['-h','--help']:
                usage(retval=0)
            elif arg in ['-V', '--version']:
                print '%s' % __version__
                sys.exit(0)
            elif arg == '--split':
                cmds['split'] = True
    except ValueError, e:
        errorprint(_('Options Error: %s') % e)
        usage()


    # make sure our dir makes sense before we continue
    if len(argsleft) > 1 and not cmds['split']:
        errorprint(_('Error: Only one directory allowed per run.'))
        usage()
    elif len(argsleft) == 0:
        errorprint(_('Error: Must specify a directory to index.'))
        usage()
    else:
        directories = argsleft

    try:
        for arg,a in gopts:
            if arg in ['-v', '--verbose']:
                cmds['verbose'] = 1
            elif arg in ["-q", '--quiet']:
                cmds['quiet'] = 1
            elif arg in ['-u', '--baseurl']:
                if cmds['baseurl'] is not None:
                    errorprint(_('Error: Only one baseurl allowed.'))
                    usage()
                else:
                    cmds['baseurl'] = a
            elif arg in ['-g', '--groupfile']:
                if cmds['groupfile'] is not None:
                    errorprint(_('Error: Only one groupfile allowed.'))
                    usage()
                else:
                    cmds['groupfile'] = a
            elif arg in ['-x', '--exclude']:
                cmds['excludes'].append(a)
            elif arg in ['-p', '--pretty']:
                cmds['pretty'] = 1
#            elif arg in ['--update-groups-only']:
#                cmds['updategroupsonly'] = 1
            elif arg in ['-s', '--checksum']:
                errorprint(_('This option is deprecated'))
            elif arg in ['-c', '--cachedir']:
                cmds['cache'] = True
                cmds['cachedir'] = a
            elif arg in ['-U', '--update-info-location']:
                cmds['update-info-location'] = a
            elif arg == '--basedir':
                cmds['basedir'] = a
                    
    except ValueError, e:
        errorprint(_('Options Error: %s') % e)
        usage()

    #setup some defaults
    cmds['primaryfile'] = 'primary.xml.gz'
    cmds['filelistsfile'] = 'filelists.xml.gz'
    cmds['otherfile'] = 'other.xml.gz'
    cmds['repomdfile'] = 'repomd.xml'
    cmds['tempdir'] = '.repodata'
    cmds['finaldir'] = 'repodata'
    cmds['olddir'] = '.olddata'
    cmds['update-info-dir'] = 'update-info'

    return cmds, directories

def main(args):
    cmds, directories = parseArgs(args)
    directory = directories[0]
# Fix paths
    directory = os.path.normpath(directory)
    if cmds['split']:
        pass
    elif os.path.isabs(directory):
        cmds['basedir'] = directory
        directory = '.'
    else:
        cmds['basedir'] = os.path.realpath(os.path.join(cmds['basedir'], directory))
        directory = '.'
    if cmds['groupfile']:
        a = cmds['groupfile']
        if cmds['split']:
            a = os.path.join(cmds['basedir'], directory, cmds['groupfile'])
        elif not os.path.isabs(a):
            a = os.path.join(cmds['basedir'], cmds['groupfile'])
        if not os.path.exists(a):
            errorprint(_('Error: groupfile %s cannot be found.' % a))
            usage()
        cmds['groupfile'] = a
    if cmds['cachedir']:
        a = cmds ['cachedir']
        if not os.path.isabs(a):
            a = os.path.join(cmds['basedir'] ,a)
        if not checkAndMakeDir(a):
            errorprint(_('Error: cannot open/write to cache dir %s' % a))
            usage()
        cmds['cachedir'] = a

    # start the sanity/stupidity checks
    if not os.path.exists(os.path.join(cmds['basedir'], directory)):
        errorprint(_('Directory must exist'))
        sys.exit(1)

    if not os.path.isdir(os.path.join(cmds['basedir'], directory)):
        errorprint(_('Directory of packages must be a directory.'))
        sys.exit(1)

    if not os.access(cmds['basedir'], os.W_OK):
        errorprint(_('Directory must be writable.'))
        sys.exit(1)

    if cmds['split']:
        oldbase = cmds['basedir']
        cmds['basedir'] = os.path.join(cmds['basedir'], directory)
    if not checkAndMakeDir(os.path.join(cmds['basedir'], cmds['tempdir'])):
        sys.exit(1)

    if not checkAndMakeDir(os.path.join(cmds['basedir'], cmds['finaldir'])):
        sys.exit(1)

    if os.path.exists(os.path.join(cmds['basedir'], cmds['olddir'])):
        errorprint(_('Old data directory exists, please remove: %s') % cmds['olddir'])
        sys.exit(1)

    if cmds.has_key('update-info-location'):
        if not checkAndMakeDir(os.path.join(cmds['basedir'],
                               cmds['tempdir'], cmds['update-info-dir'])):
            errorprint(_('Error: cannot open/write to update info dir %s' % a))
            usage()

    # make sure we can write to where we want to write to:
    for direc in ['tempdir', 'finaldir']:
        for file in ['primaryfile', 'filelistsfile', 'otherfile', 'repomdfile']:
            filepath = os.path.join(cmds['basedir'], cmds[direc], cmds[file])
            if os.path.exists(filepath):
                if not os.access(filepath, os.W_OK):
                    errorprint(_('error in must be able to write to metadata files:\n  -> %s') % filepath)
                    usage()

    if cmds['split']:
        cmds['basedir'] = oldbase
        mdgen = SplitMetaDataGenerator(cmds)
        mdgen.doPkgMetadata(directories)
    else:
        mdgen = MetaDataGenerator(cmds)
        mdgen.doPkgMetadata(directory)
    mdgen.doRepoMetadata()

    if os.path.exists(os.path.join(cmds['basedir'], cmds['finaldir'])):
        try:
            os.rename(os.path.join(cmds['basedir'], cmds['finaldir']),
                      os.path.join(cmds['basedir'], cmds['olddir']))
        except:
            errorprint(_('Error moving final %s to old dir %s' % (os.path.join(cmds['basedir'], cmds['finaldir']),
                                                                  os.path.join(cmds['basedir'], cmds['olddir']))))
            sys.exit(1)

    try:
        os.rename(os.path.join(cmds['basedir'], cmds['tempdir']),
                  os.path.join(cmds['basedir'], cmds['finaldir']))
    except:
        errorprint(_('Error moving final metadata into place'))
        # put the old stuff back
        os.rename(os.path.join(cmds['basedir'], cmds['olddir']),
                  os.path.join(cmds['basedir'], cmds['finaldir']))
        sys.exit(1)

    for file in ['primaryfile', 'filelistsfile', 'otherfile', 'repomdfile', 'groupfile']:
        if cmds[file]:
            fn = os.path.basename(cmds[file])
        else:
            continue
        oldfile = os.path.join(cmds['basedir'], cmds['olddir'], fn)
        if os.path.exists(oldfile):
            try:
                os.remove(oldfile)
            except OSError, e:
                errorprint(_('Could not remove old metadata file: %s') % oldfile)
                errorprint(_('Error was %s') % e)
                sys.exit(1)

    # Clean up any update metadata
    mdpath = os.path.join(cmds['basedir'], cmds['olddir'], cmds['update-info-dir'])
    if os.path.isdir(mdpath):
        for file in os.listdir(mdpath):
            os.remove(os.path.join(mdpath, file))
        os.rmdir(mdpath)


#XXX: fix to remove tree as we mung basedir
    try:
        os.rmdir(os.path.join(cmds['basedir'], cmds['olddir']))
    except OSError, e:
        errorprint(_('Could not remove old metadata dir: %s') % cmds['olddir'])
        errorprint(_('Error was %s') % e)
        errorprint(_('Please clean up this directory manually.'))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == 'profile':
            import hotshot
            p = hotshot.Profile(os.path.expanduser("~/createrepo.prof"))
            p.run('main(sys.argv[2:])')
            p.close()
        else:
            main(sys.argv[1:])
    else:
        main(sys.argv[1:])
