#!/usr/bin/python -tt
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
# Copyright 2003 Duke University

import os
import sys
import getopt
import rpm
import libxml2
import string
import fnmatch
import dumpMetadata


def errorprint(stuff):
    print >> sys.stderr, stuff

def usage():
    print """
    %s [options] directory-of-packages
    
    Options:
     -u, --baseurl = optional base url location for all files
     -g, --groupfile = optional groups xml file for this repository
                       this should be relative to the 'directory-of-packages'
     -x, --exclude = files globs to exclude, can be specified multiple times
     -q, --quiet = run quietly
     -v, --verbose = run verbosely
     -s, --checksum = md5 or sha - select type of checksum to use (default: md5)
     -h, --help = show this help

    """ % os.path.basename(sys.argv[0])
    

    sys.exit(1)


def getFileList(path, ext, filelist):
    """Return all files in path matching ext, store them in filelist, recurse dirs
       return list object"""
    
    extlen = len(ext)
    try:
        dir_list = os.listdir(path)
    except OSError, e:
        errorprint('Error accessing directory %s, %s' % (path, e))
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

    try:
        gopts, argsleft = getopt.getopt(args, 'hqvg:s:x:u:', ['help', 'exclude', 
                                                              'quiet', 'verbose', 
                                                              'baseurl=', 'groupfile=',
                                                              'checksum='])
    except getopt.error, e:
        errorprint('Options Error: %s.' % e)
        usage()
   
    try: 
        for arg,a in gopts:
            if arg in ['-h','--help']:
                usage()
            elif arg == '-v':
                cmds['verbose'] = 1
            elif arg == "-q":
                cmds['quiet'] = 1
            elif arg in ['-u', '--baseurl']:
                if cmds['baseurl'] is not None:
                    errorprint('Error: Only one baseurl allowed.')
                    usage()
                else:
                    cmds['baseurl'] = a
            elif arg in ['-g', '--groupfile']:
                if cmds['groupfile'] is not None:
                    errorprint('Error: Only one groupfile allowed.')
                    usage()
                else:
                    cmds['groupfile'] = a
                    
            elif arg in ['-x', '--exclude']:
                cmds['excludes'].append(a)
            elif arg in ['-s', '--checksum']:
                if a not in ['md5', 'sha']:
                    errorprint('Error: checksums are: md5 or sha.')
                    usage()
                else:
                    cmds['sumtype'] = a
    
    except ValueError, e:
        errorprint('Options Error: %s' % e)
        usage()

    if len(argsleft) != 1:
        errorprint('Error: Only one directory allowed per run.')
        usage()
    else:
        directory = argsleft[0]
        
    return cmds, directory

def doPkgMetadata(cmds, ts):
    # setup the base metadata doc
    basedoc = libxml2.newDoc("1.0")
    baseroot =  basedoc.newChild(None, "metadata", None)
    basens = baseroot.newNs('http://linux.duke.edu/metadata/common', None)
    baseroot.setNs(basens)
    # setup the file list doc
    filesdoc = libxml2.newDoc("1.0")
    filesroot = filesdoc.newChild(None, "filelists", None)
    filesns = filesroot.newNs('http://linux.duke.edu/metadata/filelists', None)
    filesroot.setNs(filesns)
    # setup the other doc
    otherdoc = libxml2.newDoc("1.0")
    otherroot = otherdoc.newChild(None, "otherdata", None)
    otherns = otherroot.newNs('http://linux.duke.edu/metadata/other', None)
    otherroot.setNs(otherns)

    files = []
    files = getFileList('./', '.rpm', files)
    files = trimRpms(files, cmds['excludes'])
    
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
                dumpMetadata.generateXML(basedoc, baseroot, mdobj, cmds['sumtype'])
            except dumpMetadata.MDError, e:
                errorprint('\nan error occurred creating primary metadata - hmm %s' % e)
                continue
            try:
                dumpMetadata.fileListXML(filesdoc, filesroot, mdobj)
            except dumpMetadata.MDError, e:
                errorprint('\nan error occurred creating filelists- hmm %s' % e)
                continue
            try:
                dumpMetadata.otherXML(otherdoc, otherroot, mdobj)
            except dumpMetadata.MDError, e:
                errorprint('\nan error occurred - hmm %s' % e)
                continue
    if not cmds['quiet']:
        print ''
        
    # save them up to the tmp locations:
    basedoc.setDocCompressMode(9)                
    if not cmds['quiet']:
        print 'Saving Primary metadata'
    basedoc.saveFormatFileEnc('.primary.xml.gz', 'UTF-8', 1)
    
    filesdoc.setDocCompressMode(9)
    if not cmds['quiet']:
        print 'Saving file lists metadata'
    filesdoc.saveFormatFileEnc('.filelists.xml.gz', 'UTF-8', 1)
    
    otherdoc.setDocCompressMode(9)
    if not cmds['quiet']:
        print 'Saving other metadata'
    otherdoc.saveFormatFileEnc('.other.xml.gz', 'UTF-8', 1)
    
    # move them to their final locations
    for (tmp, dest) in [('.other.xml.gz', cmds['otherfile']), 
                        ('.primary.xml.gz', cmds['primaryfile']), 
                        ('.filelists.xml.gz', cmds['filelistsfile'])]:
        try:
            os.rename(tmp, dest)
        except OSError, e:
            errorprint('Error finishing file %s: %s' % (dest, e))
            errorprint('Exiting.')
            os.unlink(tmp)
            sys.exit(1)
   

def doRepoMetadata(cmds):
    """generate the repomd.xml file that stores the info on the other files"""
    #<repomd>
    #  <data type='other'>
    #    <location base=foo href=relative/>
    #    <checksum type="md5">md5sumhere</checksum>
    #    <timestamp>timestamp</timestamp>
    #  </data>
    repodoc = libxml2.newDoc("1.0")
    reporoot = repodoc.newChild(None, "repomd", None)
    repons = reporoot.newNs('http://linux.duke.edu/metadata/repo', None)
    reporoot.setNs(repons)
    sumtype = cmds['sumtype']
    
    if cmds['groupfile'] is not None:
        workfiles = [(cmds['otherfile'], 'other',),
                     (cmds['filelistsfile'], 'filelists'),
                     (cmds['primaryfile'], 'primary'),
                     (cmds['groupfile'], 'group')]
                     
    else:
        workfiles = [(cmds['otherfile'], 'other',),
                     (cmds['filelistsfile'], 'filelists'),
                     (cmds['primaryfile'], 'primary')]
    
    for (file, ftype) in workfiles:
        csum = dumpMetadata.getChecksum(sumtype, file)
        timestamp = os.stat(file)[8]
        data = reporoot.newChild(None, 'data', None)
        data.newProp('type', ftype)
        location = data.newChild(None, 'location', None)
        if cmds['baseurl'] is not None:
            location.newProp('xml:base', cmds['baseurl'])
        location.newProp('href', file)
        checksum = data.newChild(None, 'checksum', csum)
        checksum.newProp('type', sumtype)
        timestamp = data.newChild(None, 'timestamp', str(timestamp))
        
    repodoc.saveFormatFileEnc('.repomd.xml.gz', 'UTF-8', 1)
    try:
        os.rename('.repomd.xml.gz', cmds['repomdfile'])
    except OSError, e:
        errorprint('Error finishing file %s: %s' % (cmds['repomdfile'], e))
        errorprint('Exiting.')
        os.unlink('.repomd.xml.gz')
        sys.exit(1)
    else:
        del repodoc
        
   

def main(args):
    cmds, directory = parseArgs(args)
    #setup some defaults
    cmds['primaryfile'] = 'primary.xml.gz'
    cmds['filelistsfile'] = 'filelists.xml.gz'
    cmds['otherfile'] = 'other.xml.gz'
    cmds['repomdfile'] = 'repomd.xml'
    
    # save where we are right now
    curdir = os.getcwd()
    # start the sanity/stupidity checks
    if not os.path.exists(directory):
        errorprint('Directory must exist')
        usage()
    if not os.path.isdir(directory):
        errorprint('Directory of packages must be a directory.')
        usage()
    if not os.access(directory, os.W_OK):
        errorprint('Directory must be writable.')
        usage()
    # check out the group file if specified
    if cmds['groupfile'] is not None:
        grpfile = os.path.join(directory, cmds['groupfile'])
        if not os.access(grpfile, os.R_OK):
            errorprint('groupfile %s must exist and be readable' % grpfile)
            usage()
    # make sure we can write to where we want to write to:
        for file in ['primaryfile', 'filelistsfile', 'otherfile', 'repomdfile']:
            filepath = os.path.join(directory, cmds[file])
            dirpath = os.path.dirname(filepath)
            if os.path.exists(filepath):
                if not os.access(filepath, os.W_OK):
                    errorprint('error in must be able to write to metadata files:\n  -> %s' % filepath)
                    usage()
            else:                
                if not os.access(dirpath, os.W_OK):
                    errorprint('must be able to write to path for metadata files:\n  -> %s' % dirpath)
                    usage()
                    
    # change to the basedir to work from w/i the path - for relative url paths
    os.chdir(directory)
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

    os.chdir(curdir)
        

        
if __name__ == "__main__":
    if sys.argv[1] == 'profile':
        import profile
        profile.run('main(sys.argv[2:])')
    else:    
        main(sys.argv[1:])
