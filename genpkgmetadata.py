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
# done to fix gzip randomly changing the checksum
import gzip
from zlib import error as zlibError
from gzip import write32u, FNAME

import dumpMetadata
__version__ = '0.3.3'

def errorprint(stuff):
    print >> sys.stderr, stuff

def _(args):
    """Stub function for translation"""
    return args
    
def usage():
    print _("""
    %s [options] directory-of-packages
    
    Options:
     -u, --baseurl = optional base url location for all files
     -x, --exclude = files globs to exclude, can be specified multiple times
     -q, --quiet = run quietly
     -g, --groupfile <filename> to point to for group information (precreated)
     -v, --verbose = run verbosely
     -s, --checksum = md5 or sha - select type of checksum to use (default: md5)
     -h, --help = show this help
     -V, --version = output version
     -p, --pretty = output xml files in pretty format.
    """) % os.path.basename(sys.argv[0])
    

    sys.exit(1)


def getFileList(path, ext, filelist):
    """Return all files in path matching ext, store them in filelist, recurse dirs
       return list object"""
    
    extlen = len(ext)
    try:
        dir_list = os.listdir(path)
    except OSError, e:
        errorprint(_('Error accessing directory %s, %s') % (path, e))
        sys.exit(1)
        
    for d in dir_list:
        if os.path.isdir(path + '/' + d):
            filelist = getFileList(path + '/' + d, ext, filelist)
        else:
            if string.lower(d[-extlen:]) == '%s' % (ext):
               newpath = os.path.normpath(path + '/' + d)
               filelist.append(newpath)
                    
    return filelist


def trimRpms(rpms, excludeGlobs):
    # print 'Pre-Trim Len: %d' % len(rpms)
    badrpms = []
    for file in rpms:
        for glob in excludeGlobs:
            if fnmatch.fnmatch(file, glob):
                # print 'excluded: %s' % file
                if file not in badrpms:
                    badrpms.append(file)
    for file in badrpms:
        if file in rpms:
            rpms.remove(file)            
    # print 'Post-Trim Len: %d' % len(rpms)
    return rpms

def checkAndMakeDir(dir):
    """
     check out the dir and make it, if possible, return 1 if done, else return 0
    """
    if os.path.exists(dir):
        if not os.path.isdir(dir):
            errorprint(_('%s is not a dir') % dir)
            result = 0
        else:
            if not os.access(dir, os.W_OK):
                errorprint(_('%s is not writable') % dir)
                result = 0
            else:
                result = 1
    else:
        try:
            os.mkdir(dir)
        except OSError, e:
            errorprint(_('Error creating dir %s: %s') % (dir, e))
            result = 0
        else:
            result = 1
    return result


# this is done to make the hdr writing _more_ sane for rsync users especially
__all__ = ["GzipFile","open"]

class GzipFile(gzip.GzipFile):
    def _write_gzip_header(self):
        self.fileobj.write('\037\213')             # magic header
        self.fileobj.write('\010')                 # compression method
        fname = self.filename[:-3]
        flags = 0
        if fname:
            flags = FNAME
        self.fileobj.write(chr(flags))
        write32u(self.fileobj, long(0))
        self.fileobj.write('\002')
        self.fileobj.write('\377')
        if fname:
            self.fileobj.write(fname + '\000')


def _gzipOpen(filename, mode="rb", compresslevel=9):
    return GzipFile(filename, mode, compresslevel)
    
def parseArgs(args):
    """
       Parse the command line args return a commands dict and directory.
       Sanity check all the things being passed in.
    """
    if  len(args) == 0:
        usage()
    cmds = {}
    cmds['quiet'] = 0
    cmds['verbose'] = 0
    cmds['excludes'] = []
    cmds['baseurl'] = None
    cmds['groupfile'] = None
    cmds['sumtype'] = 'md5'
    cmds['pretty'] = 0

    try:
        gopts, argsleft = getopt.getopt(args, 'phqVvg:s:x:u:', ['help', 'exclude', 
                                                              'quiet', 'verbose', 
                                                              'baseurl=', 'groupfile=',
                                                              'checksum=', 'version',
                                                              'pretty'])
    except getopt.error, e:
        errorprint(_('Options Error: %s.') % e)
        usage()
   
    try: 
        for arg,a in gopts:
            if arg in ['-h','--help']:
                usage()
            elif arg in ['-V', '--version']:
                print '%s' % __version__
                sys.exit(0)
            elif arg == '-v':
                cmds['verbose'] = 1
            elif arg == "-q":
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
                    if os.path.exists(a):
                        cmds['groupfile'] = a
                    else:
                        errorprint(_('Error: groupfile %s cannot be found.' % a))
                        usage()
            elif arg in ['-x', '--exclude']:
                cmds['excludes'].append(a)
            elif arg in ['-p', '--pretty']:
                cmds['pretty'] = 1
            elif arg in ['-s', '--checksum']:
                if a not in ['md5', 'sha']:
                    errorprint(_('Error: checksums are: md5 or sha.'))
                    usage()
                else:
                    cmds['sumtype'] = a
    
    except ValueError, e:
        errorprint(_('Options Error: %s') % e)
        usage()

    if len(argsleft) != 1:
        errorprint(_('Error: Only one directory allowed per run.'))
        usage()
    else:
        directory = argsleft[0]
        
    return cmds, directory

def doPkgMetadata(cmds, ts):
    """all the heavy lifting for the package metadata"""

    # rpms we're going to be dealing with
    files = []
    files = getFileList('./', '.rpm', files)
    files = trimRpms(files, cmds['excludes'])
    pkgcount = len(files)
    
    # setup the base metadata doc
    basedoc = libxml2.newDoc("1.0")
    baseroot =  basedoc.newChild(None, "metadata", None)
    basens = baseroot.newNs('http://linux.duke.edu/metadata/common', None)
    formatns = baseroot.newNs('http://linux.duke.edu/metadata/rpm', 'rpm')
    baseroot.setNs(basens)
    basefilepath = os.path.join(cmds['tempdir'], cmds['primaryfile'])
    basefile = _gzipOpen(basefilepath, 'w')
    basefile.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    basefile.write('<metadata xmlns="http://linux.duke.edu/metadata/common" xmlns:rpm="http://linux.duke.edu/metadata/rpm" packages="%s">\n' % 
                   pkgcount)

    # setup the file list doc
    filesdoc = libxml2.newDoc("1.0")
    filesroot = filesdoc.newChild(None, "filelists", None)
    filesns = filesroot.newNs('http://linux.duke.edu/metadata/filelists', None)
    filesroot.setNs(filesns)
    filelistpath = os.path.join(cmds['tempdir'], cmds['filelistsfile'])
    flfile = _gzipOpen(filelistpath, 'w')    
    flfile.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    flfile.write('<filelists xmlns="http://linux.duke.edu/metadata/filelists" packages="%s">\n' % 
                   pkgcount)
    
    
    # setup the other doc
    otherdoc = libxml2.newDoc("1.0")
    otherroot = otherdoc.newChild(None, "otherdata", None)
    otherns = otherroot.newNs('http://linux.duke.edu/metadata/other', None)
    otherroot.setNs(otherns)
    otherfilepath = os.path.join(cmds['tempdir'], cmds['otherfile'])
    otherfile = _gzipOpen(otherfilepath, 'w')
    otherfile.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    otherfile.write('<otherdata xmlns="http://linux.duke.edu/metadata/other" packages="%s">\n' % 
                   pkgcount)
    
    
    current = 0
    for file in files:
        current+=1
        try:
            mdobj = dumpMetadata.RpmMetaData(ts, file, cmds['baseurl'], cmds['sumtype'])
            if not cmds['quiet']:
                if cmds['verbose']:
                    print '%d/%d - %s' % (current, len(files), file)
                else:
                    sys.stdout.write('\r' + ' ' * 80)
                    sys.stdout.write("\r%d/%d - %s" % (current, len(files), file))
                    sys.stdout.flush()
        except dumpMetadata.MDError, e:
            errorprint('\n%s - %s' % (e, file))
            continue
        else:
            try:
                node = dumpMetadata.generateXML(basedoc, baseroot, formatns, mdobj, cmds['sumtype'])
            except dumpMetadata.MDError, e:
                errorprint(_('\nAn error occurred creating primary metadata: %s') % e)
                continue
            else:
                output = node.serialize(None, cmds['pretty'])
                basefile.write(output)
                basefile.write('\n')
                node.unlinkNode()
                node.freeNode()
                del node

            try:
                node = dumpMetadata.fileListXML(filesdoc, filesroot, mdobj)
            except dumpMetadata.MDError, e:
                errorprint(_('\nAn error occurred creating filelists: %s') % e)
                continue
            else:
                output = node.serialize(None, cmds['pretty'])
                flfile.write(output)
                flfile.write('\n')
                node.unlinkNode()
                node.freeNode()
                del node

            try:
                node = dumpMetadata.otherXML(otherdoc, otherroot, mdobj)
            except dumpMetadata.MDError, e:
                errorprint(_('\nAn error occurred: %s') % e)
                continue
            else:
                output = node.serialize(None, cmds['pretty'])
                otherfile.write(output)
                otherfile.write('\n')
                node.unlinkNode()
                node.freeNode()
                del node

        
    if not cmds['quiet']:
        print ''
        
    # save them up to the tmp locations:
    if not cmds['quiet']:
        print _('Saving Primary metadata')
    basefile.write('\n</metadata>')
    basefile.close()
    basedoc.freeDoc()
    
    if not cmds['quiet']:
        print _('Saving file lists metadata')
    flfile.write('\n</filelists>')
    flfile.close()
    filesdoc.freeDoc()
    
    if not cmds['quiet']:
        print _('Saving other metadata')
    otherfile.write('\n</otherdata>')
    otherfile.close()
    otherdoc.freeDoc()

def doRepoMetadata(cmds):
    """wrapper to generate the repomd.xml file that stores the info on the other files"""
    repodoc = libxml2.newDoc("1.0")
    reporoot = repodoc.newChild(None, "repomd", None)
    repons = reporoot.newNs('http://linux.duke.edu/metadata/repo', None)
    reporoot.setNs(repons)
    repofilepath = os.path.join(cmds['tempdir'], cmds['repomdfile'])
    
    try:
        dumpMetadata.repoXML(reporoot, cmds)
    except dumpMetadata.MDError, e:
        errorprint(_('Error generating repo xml file: %s') % e)
        sys.exit(1)
        
    try:        
        repodoc.saveFormatFileEnc(repofilepath, 'UTF-8', 1)
    except:
        errorprint(_('Error saving temp file for rep xml: %s') % repofilepath)
        sys.exit(1)
        
    del repodoc
        
   

def main(args):
    cmds, directory = parseArgs(args)
    #setup some defaults
    cmds['primaryfile'] = 'primary.xml.gz'
    cmds['filelistsfile'] = 'filelists.xml.gz'
    cmds['otherfile'] = 'other.xml.gz'
    cmds['repomdfile'] = 'repomd.xml'
    cmds['tempdir'] = '.repodata'
    cmds['finaldir'] = 'repodata'
    cmds['olddir'] = '.olddata'
    
    # save where we are right now
    curdir = os.getcwd()
    # start the sanity/stupidity checks
    if not os.path.exists(directory):
        errorprint(_('Directory must exist'))
        sys.exit(1)
        
    if not os.path.isdir(directory):
        errorprint(_('Directory of packages must be a directory.'))
        sys.exit(1)
        
    if not os.access(directory, os.W_OK):
        errorprint(_('Directory must be writable.'))
        sys.exit(1)

 
    if not checkAndMakeDir(os.path.join(directory, cmds['tempdir'])):
        sys.exit(1)
        
    if not checkAndMakeDir(os.path.join(directory, cmds['finaldir'])):
        sys.exit(1)
        
    if os.path.exists(os.path.join(directory, cmds['olddir'])):
        errorprint(_('Old data directory exists, please remove: %s') % cmds['olddir'])
        sys.exit(1)
        
    # change to the basedir to work from w/i the path - for relative url paths
    os.chdir(directory)

    # make sure we can write to where we want to write to:
    for direc in ['tempdir', 'finaldir']:
        for file in ['primaryfile', 'filelistsfile', 'otherfile', 'repomdfile']:
            filepath = os.path.join(cmds[direc], cmds[file])
            if os.path.exists(filepath):
                if not os.access(filepath, os.W_OK):
                    errorprint(_('error in must be able to write to metadata files:\n  -> %s') % filepath)
                    os.chdir(curdir)
                    usage()
                    
    ts = rpm.TransactionSet()
    try:
        doPkgMetadata(cmds, ts)
    except:
        # always clean up your messes
        os.chdir(curdir)
        raise
    
    try:
        doRepoMetadata(cmds)
    except:
        os.chdir(curdir)
        raise
        
    if os.path.exists(cmds['finaldir']):
        try:
            os.rename(cmds['finaldir'], cmds['olddir'])
        except:
            errorprint(_('Error moving final to old dir'))
            os.chdir(curdir)
            sys.exit(1)
        
    try:
        os.rename(cmds['tempdir'], cmds['finaldir'])
    except:
        errorprint(_('Error moving final metadata into place'))
        # put the old stuff back
        os.rename(cmds['olddir'], cmds['finaldir'])
        os.chdir(curdir)
        sys.exit(1)
        
    for file in ['primaryfile', 'filelistsfile', 'otherfile', 'repomdfile', 'groupfile']:
        if cmds[file]:
            fn = os.path.basename(cmds[file])
        else:
            continue
        oldfile = os.path.join(cmds['olddir'], fn)
        if os.path.exists(oldfile):
            try:
                os.remove(oldfile)
            except OSError, e:
                errorprint(_('Could not remove old metadata file: %s') % oldfile)
                errorprint(_('Error was %s') % e)
                os.chdir(curdir)
                sys.exit(1)
            
    try:
        os.rmdir(cmds['olddir'])
    except OSError, e:
        errorprint(_('Could not remove old metadata dir: %s') % cmds['olddir'])
        errorprint(_('Error was %s') % e)
        os.chdir(curdir)
        sys.exit(1)
        
            
        
    # take us home mr. data
    os.chdir(curdir)
        

        
if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == 'profile':
            import profile
            profile.run('main(sys.argv[2:])')
        else:
            main(sys.argv[1:])
    else:
        main(sys.argv[1:])
