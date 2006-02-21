#!/usr/bin/python -t
# base classes and functions for dumping out package Metadata
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
import rpm
import exceptions
import md5
import sha
import types
import struct
import re
import stat

# done to fix gzip randomly changing the checksum
import gzip
from zlib import error as zlibError
from gzip import write32u, FNAME

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
    


def returnFD(filename):
    try:
        fdno = os.open(filename, os.O_RDONLY)
    except OSError:
        raise MDError, "Error opening file"
    return fdno
    
def returnHdr(ts, package):
    """hand back the rpm header or raise an Error if the pkg is fubar"""
    opened_here = 0
    try:
        if type(package) is types.StringType:
            opened_here = 1
            fdno = os.open(package, os.O_RDONLY)
        else: 
            fdno = package # let's assume this is an fdno and go with it :)
    except OSError:
        raise MDError, "Error opening file"
    ts.setVSFlags((rpm._RPMVSF_NOSIGNATURES|rpm.RPMVSF_NOMD5|rpm.RPMVSF_NEEDPAYLOAD))
    try:
        hdr = ts.hdrFromFdno(fdno)
    except rpm.error:
        raise MDError, "Error opening package"
    if type(hdr) != rpm.hdr:
        raise MDError, "Error opening package"
    ts.setVSFlags(0)
    
    if opened_here:
        os.close(fdno)
        del fdno

    return hdr
    
def getChecksum(sumtype, file, CHUNK=2**16):
    """takes filename, hand back Checksum of it
       sumtype = md5 or sha
       filename = /path/to/file
       CHUNK=65536 by default"""
       
    # chunking brazenly lifted from Ryan Tomayko
    opened_here = 0
    try:
        if type(file) is not types.StringType:
            fo = file # assume it's a file-like-object
        else:
            opened_here = 1
            fo = open(file, 'rb', CHUNK)
            
        if sumtype == 'md5':
            sum = md5.new()
        elif sumtype == 'sha':
            sum = sha.new()
        else:
            raise MDError, 'Error Checksumming file, wrong checksum type %s' % sumtype
        chunk = fo.read
        while chunk: 
            chunk = fo.read(CHUNK)
            sum.update(chunk)

        if opened_here:
            fo.close()
            del fo
            
        return sum.hexdigest()
    except:
        raise MDError, 'Error opening file for checksum: %s' % file


def utf8String(string):
    """hands back a unicoded string"""
    if string is None:
        return ''
    elif isinstance(string, unicode):    
        return string
    try:
        x = unicode(string, 'ascii')
        return string
    except UnicodeError:
        encodings = ['utf-8', 'iso-8859-1', 'iso-8859-15', 'iso-8859-2']
        for enc in encodings:
            try:
                x = unicode(string, enc)
            except UnicodeError:
                pass
            else:
                if x.encode(enc) == string:
                    return x.encode('utf-8')
    newstring = ''
    for char in string:
        if ord(char) > 127:
            newstring = newstring + '?'
        else:
            newstring = newstring + char
    return newstring

        
def byteranges(file):
    """takes an rpm file or fileobject and returns byteranges for location of the header"""
    opened_here = 0
    if type(file) is not types.StringType:
        fo = file
    else:
        opened_here = 1
        fo = open(file, 'r')
    #read in past lead and first 8 bytes of sig header
    fo.seek(104)
    # 104 bytes in
    binindex = fo.read(4)
    # 108 bytes in
    (sigindex, ) = struct.unpack('>I', binindex)
    bindata = fo.read(4)
    # 112 bytes in
    (sigdata, ) = struct.unpack('>I', bindata)
    # each index is 4 32bit segments - so each is 16 bytes
    sigindexsize = sigindex * 16
    sigsize = sigdata + sigindexsize
    # we have to round off to the next 8 byte boundary
    disttoboundary = (sigsize % 8)
    if disttoboundary != 0:
        disttoboundary = 8 - disttoboundary
    # 112 bytes - 96 == lead, 8 = magic and reserved, 8 == sig header data
    hdrstart = 112 + sigsize  + disttoboundary
    
    fo.seek(hdrstart) # go to the start of the header
    fo.seek(8,1) # read past the magic number and reserved bytes

    binindex = fo.read(4) 
    (hdrindex, ) = struct.unpack('>I', binindex)
    bindata = fo.read(4)
    (hdrdata, ) = struct.unpack('>I', bindata)
    
    # each index is 4 32bit segments - so each is 16 bytes
    hdrindexsize = hdrindex * 16 
    # add 16 to the hdrsize to account for the 16 bytes of misc data b/t the
    # end of the sig and the header.
    hdrsize = hdrdata + hdrindexsize + 16
    
    # header end is hdrstart + hdrsize 
    hdrend = hdrstart + hdrsize 
    if opened_here:
        fo.close()
        del fo
    return (hdrstart, hdrend)
    

class MDError(exceptions.Exception):
    def __init__(self, args=None):
        exceptions.Exception.__init__(self)
        self.args = args



class RpmMetaData:
    """each rpm is one object, you pass it an rpm file
       it opens the file, and pulls the information out in bite-sized chunks :)
    """

    mode_cache = {}

    def __init__(self, ts, basedir, filename, options):
        try:
            stats = os.stat(os.path.join(basedir, filename))
            self.size = stats[6]
            self.mtime = stats[8]
            del stats
        except OSError, e:
            raise MDError, "Error Stat'ing file %s %s" % (basedir, filename)
        self.options = options
        self.localurl = options['baseurl']
        self.relativepath = filename
        fd = returnFD(os.path.join(basedir, filename))
        self.hdr = returnHdr(ts, fd)
        os.lseek(fd, 0, 0)
        fo = os.fdopen(fd, 'rb')
        self.pkgid = self.doChecksumCache(fo)
        fo.seek(0)
        (self.rangestart, self.rangeend) = byteranges(fo)
        fo.close()
        del fo
        del fd
        
        # setup our regex objects
        fileglobs = options['file-pattern-match']
        #['.*bin\/.*', '^\/etc\/.*', '^\/usr\/lib\/sendmail$']
        dirglobs = options['dir-pattern-match']
        #['.*bin\/.*', '^\/etc\/.*']
        self.dirrc = []
        self.filerc = []
        for glob in fileglobs:
            self.filerc.append(re.compile(glob))
        
        for glob in dirglobs:
            self.dirrc.append(re.compile(glob))
            
        self.filenames = []
        self.dirnames = []
        self.ghostnames = []
        self.genFileLists()

    def arch(self):
        if self.tagByName('sourcepackage') == 1:
            return 'src'
        else:
            return self.tagByName('arch')

    def _correctFlags(self, flags):
        returnflags=[]
        if flags is None:
            return returnflags

        if type(flags) is not types.ListType:
            newflag = flags & 0xf
            returnflags.append(newflag)
        else:
            for flag in flags:
                newflag = flag
                if flag is not None:
                    newflag = flag & 0xf
                returnflags.append(newflag)
        return returnflags

    def _checkPreReq(self, flags):
        reqs=[]
        if flags is None:
            return reqs

        if type(flags) is not types.ListType:
            flags = [flags]
        for flag in flags:
            newflag = flag
            if flag is not None:
                newflag = flag & 64
                if newflag == 64:
                    reqs.append(1)
                else:
                    reqs.append(0)
        return reqs


    def _correctVersion(self, vers):
        returnvers = []
        vertuple = (None, None, None)
        if vers is None:
            returnvers.append(vertuple)
            return returnvers
            
        if type(vers) is not types.ListType:
            if vers is not None:
                vertuple = self._stringToVersion(vers)
            else:
                vertuple = (None, None, None)
            returnvers.append(vertuple)
        else:
            for ver in vers:
                if ver is not None:
                    vertuple = self._stringToVersion(ver)
                else:
                    vertuple = (None, None, None)
                returnvers.append(vertuple)
        return returnvers
            
    
    def _stringToVersion(self, strng):
        i = strng.find(':')
        if i != -1:
            epoch = strng[:i]
        else:
            epoch = '0'
        j = strng.find('-')
        if j != -1:
            if strng[i + 1:j] == '':
                version = None
            else:
                version = strng[i + 1:j]
            release = strng[j + 1:]
        else:
            if strng[i + 1:] == '':
                version = None
            else:
                version = strng[i + 1:]
            release = None
        return (epoch, version, release)

    ###########
    # Title: Remove duplicates from a sequence
    # Submitter: Tim Peters 
    # From: http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/52560                      
        
    def _uniq(self,s):
        """Return a list of the elements in s, but without duplicates.
    
        For example, unique([1,2,3,1,2,3]) is some permutation of [1,2,3],
        unique("abcabc") some permutation of ["a", "b", "c"], and
        unique(([1, 2], [2, 3], [1, 2])) some permutation of
        [[2, 3], [1, 2]].
    
        For best speed, all sequence elements should be hashable.  Then
        unique() will usually work in linear time.
    
        If not possible, the sequence elements should enjoy a total
        ordering, and if list(s).sort() doesn't raise TypeError it's
        assumed that they do enjoy a total ordering.  Then unique() will
        usually work in O(N*log2(N)) time.
    
        If that's not possible either, the sequence elements must support
        equality-testing.  Then unique() will usually work in quadratic
        time.
        """
    
        n = len(s)
        if n == 0:
            return []
    
        # Try using a dict first, as that's the fastest and will usually
        # work.  If it doesn't work, it will usually fail quickly, so it
        # usually doesn't cost much to *try* it.  It requires that all the
        # sequence elements be hashable, and support equality comparison.
        u = {}
        try:
            for x in s:
                u[x] = 1
        except TypeError:
            del u  # move on to the next method
        else:
            return u.keys()
    
        # We can't hash all the elements.  Second fastest is to sort,
        # which brings the equal elements together; then duplicates are
        # easy to weed out in a single pass.
        # NOTE:  Python's list.sort() was designed to be efficient in the
        # presence of many duplicate elements.  This isn't true of all
        # sort functions in all languages or libraries, so this approach
        # is more effective in Python than it may be elsewhere.
        try:
            t = list(s)
            t.sort()
        except TypeError:
            del t  # move on to the next method
        else:
            assert n > 0
            last = t[0]
            lasti = i = 1
            while i < n:
                if t[i] != last:
                    t[lasti] = last = t[i]
                    lasti += 1
                i += 1
            return t[:lasti]
    
        # Brute force is all that's left.
        u = []
        for x in s:
            if x not in u:
                u.append(x)
        return u

    def tagByName(self, tag):
        data = self.hdr[tag]
        if type(data) is types.ListType:
            if len(data) > 0:
                return data[0]
            else:
                return ''
        else:
            return data
    
    def listTagByName(self, tag):
        """take a tag that should be a list and make sure it is one"""
        lst = []
        data = self.hdr[tag]
        if data is None:
            return lst
            
        if type(data) is types.ListType:
            lst.extend(data)
        else:
            lst.append(data)
        return lst

        
    def epoch(self):
        if self.hdr['epoch'] is None:
            return 0
        else:
            return self.tagByName('epoch')
            
    def genFileLists(self):
        """produces lists of dirs and files for this header in two lists"""
        
        files = self.listTagByName('filenames')
        fileflags = self.listTagByName('fileflags')
        filemodes = self.listTagByName('filemodes')
        filetuple = zip(files, filemodes, fileflags)
        for (file, mode, flag) in filetuple:
            #garbage checks
            if mode is None or mode == '':
                self.filenames.append(file)
                continue
            if not RpmMetaData.mode_cache.has_key(mode):
                RpmMetaData.mode_cache[mode] = stat.S_ISDIR(mode)
            if RpmMetaData.mode_cache[mode]:
                self.dirnames.append(file)
            else:
                if flag is None:
                    self.filenames.append(file)
                else:
                    if (flag & 64): 
                        self.ghostnames.append(file)
                        continue
                    self.filenames.append(file)

        
    def usefulFiles(self):
        """search for good files"""
        returns = {}     
        for item in self.filenames:
            if item is None:
                continue
            for glob in self.filerc:
                if glob.match(item):
                    returns[item] = 1
        return returns
                    
    def usefulGhosts(self):
        """search for useful ghost file names"""
        returns = {}
        for item in self.ghostnames:
            if item is None:
                continue
            for glob in self.filerc:
                if glob.match(item):
                    returns[item] = 1
        return returns


    def usefulDirs(self):
        """search for good dirs"""
        returns = {}
        for item in self.dirnames:
            if item is None:
                continue
            for glob in self.dirrc:
                if glob.match(item):
                    returns[item] = 1
        return returns.keys()

    
    def depsList(self):
        """returns a list of tuples of dependencies"""
        # these should probably compress down duplicates too
        lst = []
        names = self.hdr[rpm.RPMTAG_REQUIRENAME]
        tmpflags = self.hdr[rpm.RPMTAG_REQUIREFLAGS]
        flags = self._correctFlags(tmpflags)
        prereq = self._checkPreReq(tmpflags)
        ver = self._correctVersion(self.hdr[rpm.RPMTAG_REQUIREVERSION])
        if names is not None:
            lst = zip(names, flags, ver, prereq)
        return self._uniq(lst)
        
    def obsoletesList(self):
        lst = []
        names = self.hdr[rpm.RPMTAG_OBSOLETENAME]
        tmpflags = self.hdr[rpm.RPMTAG_OBSOLETEFLAGS]
        flags = self._correctFlags(tmpflags)
        ver = self._correctVersion(self.hdr[rpm.RPMTAG_OBSOLETEVERSION])
        if names is not None:
            lst = zip(names, flags, ver)
        return self._uniq(lst)

    def conflictsList(self):
        lst = []
        names = self.hdr[rpm.RPMTAG_CONFLICTNAME]
        tmpflags = self.hdr[rpm.RPMTAG_CONFLICTFLAGS]
        flags = self._correctFlags(tmpflags)
        ver = self._correctVersion(self.hdr[rpm.RPMTAG_CONFLICTVERSION])
        if names is not None:
            lst = zip(names, flags, ver)
        return self._uniq(lst)

    def providesList(self):
        lst = []
        names = self.hdr[rpm.RPMTAG_PROVIDENAME]
        tmpflags = self.hdr[rpm.RPMTAG_PROVIDEFLAGS]
        flags = self._correctFlags(tmpflags)
        ver = self._correctVersion(self.hdr[rpm.RPMTAG_PROVIDEVERSION])
        if names is not None:
            lst = zip(names, flags, ver)
        return self._uniq(lst)
        
    def changelogLists(self):
        lst = []
        names = self.listTagByName('changelogname')
        times = self.listTagByName('changelogtime')
        texts = self.listTagByName('changelogtext')
        if len(names) > 0:
            lst = zip(names, times, texts)
        return lst
    
    def doChecksumCache(self, fo):
        """return a checksum for a package:
           - check if the checksum cache is enabled
              if not - return the checksum
              if so - check to see if it has a cache file
                if so, open it and return the first line's contents
                if not, grab the checksum and write it to a file for this pkg
            """
        if not self.options['cache']:
            return getChecksum(self.options['sumtype'], fo)
        
        csumtag = '%s-%s' % (self.hdr['name'] , self.hdr[rpm.RPMTAG_SHA1HEADER])
        csumfile = '%s/%s' % (self.options['cachedir'], csumtag)
        if os.path.exists(csumfile) and self.mtime <= os.stat(csumfile)[8]:
            csumo = open(csumfile, 'r')
            checksum = csumo.readline()
            csumo.close()
            
        else:
            checksum = getChecksum(self.options['sumtype'], fo)
            csumo = open(csumfile, 'w')
            csumo.write(checksum)
            csumo.close()
            
        return checksum


    
def generateXML(doc, node, formatns, rpmObj, sumtype):
    """takes an xml doc object and a package metadata entry node, populates a 
       package node with the md information"""
    ns = node.ns()
    pkgNode = node.newChild(None, "package", None)
    pkgNode.newProp('type', 'rpm')
    pkgNode.newChild(None, 'name', rpmObj.tagByName('name'))
    pkgNode.newChild(None, 'arch', rpmObj.arch())
    version = pkgNode.newChild(None, 'version', None)
    version.newProp('epoch', str(rpmObj.epoch()))
    version.newProp('ver', str(rpmObj.tagByName('version')))
    version.newProp('rel', str(rpmObj.tagByName('release')))
    csum = pkgNode.newChild(None, 'checksum', rpmObj.pkgid)
    csum.newProp('type', sumtype)
    csum.newProp('pkgid', 'YES')
    for tag in ['summary', 'description', 'packager', 'url']:
        value = rpmObj.tagByName(tag)
        value = utf8String(value)
        value = re.sub("\n$", '', value)
        entry = pkgNode.newChild(None, tag, None)
        entry.addContent(value)
        
    time = pkgNode.newChild(None, 'time', None)
    time.newProp('file', str(rpmObj.mtime))
    time.newProp('build', str(rpmObj.tagByName('buildtime')))
    size = pkgNode.newChild(None, 'size', None)
    size.newProp('package', str(rpmObj.size))
    size.newProp('installed', str(rpmObj.tagByName('size')))
    size.newProp('archive', str(rpmObj.tagByName('archivesize')))
    location = pkgNode.newChild(None, 'location', None)
    if rpmObj.localurl is not None:
        location.newProp('xml:base', rpmObj.localurl)
    location.newProp('href', rpmObj.relativepath)
    format = pkgNode.newChild(ns, 'format', None)
    for tag in ['license', 'vendor', 'group', 'buildhost', 'sourcerpm']:
        value = rpmObj.tagByName(tag)
        value = utf8String(value)
        value = re.sub("\n$", '', value)
        entry = format.newChild(formatns, tag, None)
        entry.addContent(value)
        
    hr = format.newChild(formatns, 'header-range', None)
    hr.newProp('start', str(rpmObj.rangestart))
    hr.newProp('end', str(rpmObj.rangeend))
    for (lst, nodename) in [(rpmObj.providesList(), 'provides'),
                            (rpmObj.conflictsList(), 'conflicts'),
                            (rpmObj.obsoletesList(), 'obsoletes')]:
        if len(lst) > 0:               
            rpconode = format.newChild(formatns, nodename, None)
            for (name, flags, (e,v,r)) in lst:
                entry = rpconode.newChild(formatns, 'entry', None)
                entry.newProp('name', name)
                if flags != 0:
                    if flags == 2: arg = 'LT'
                    if flags == 4: arg = 'GT'
                    if flags == 8: arg = 'EQ'
                    if flags == 10: arg = 'LE'
                    if flags == 12: arg = 'GE'
                    entry.newProp('flags', arg)
                    # if we've got a flag we've got a version, I hope :)
                    if e:
                        entry.newProp('epoch', str(e))
                    if v:
                        entry.newProp('ver', str(v))
                    if r:
                        entry.newProp('rel', str(r))

    depsList = rpmObj.depsList()
    if len(depsList) > 0:
        rpconode = format.newChild(formatns, 'requires', None)    
        for (name, flags, (e,v,r), prereq) in depsList:
            entry = rpconode.newChild(formatns, 'entry', None)
            entry.newProp('name', name)
            if flags != 0:
                if flags == 2: arg = 'LT'
                if flags == 4: arg = 'GT'
                if flags == 8: arg = 'EQ'
                if flags == 10: arg = 'LE'
                if flags == 12: arg = 'GE'
                entry.newProp('flags', arg)
                # if we've got a flag we've got a version, I hope :)
                if e:
                    entry.newProp('epoch', str(e))
                if v:
                    entry.newProp('ver', str(v))
                if r:
                    entry.newProp('rel', str(r))
            if prereq == 1:
                entry.newProp('pre', str(prereq))
        
    for file in rpmObj.usefulFiles():
        files = format.newChild(None, 'file', None)
        file = utf8String(file)
        files.addContent(file)
    for directory in rpmObj.usefulDirs():
        files = format.newChild(None, 'file', None)
        directory = utf8String(directory)
        files.addContent(directory)
        files.newProp('type', 'dir')
    for directory in rpmObj.usefulGhosts():
        files = format.newChild(None, 'file', None)
        directory = utf8String(directory)
        files.addContent(directory)
        files.newProp('type', 'ghost')

    return pkgNode
    
def fileListXML(doc, node, rpmObj):
    pkg = node.newChild(None, 'package', None)
    pkg.newProp('pkgid', rpmObj.pkgid)
    pkg.newProp('name', rpmObj.tagByName('name'))
    pkg.newProp('arch', rpmObj.arch())
    version = pkg.newChild(None, 'version', None)
    version.newProp('epoch', str(rpmObj.epoch()))
    version.newProp('ver', str(rpmObj.tagByName('version')))
    version.newProp('rel', str(rpmObj.tagByName('release')))
    for file in rpmObj.filenames:
        files = pkg.newChild(None, 'file', None)
        file = utf8String(file)
        files.addContent(file)
    for directory in rpmObj.dirnames:
        files = pkg.newChild(None, 'file', None)
        directory = utf8String(directory)
        files.addContent(directory)
        files.newProp('type', 'dir')
    for ghost in rpmObj.ghostnames:
        files = pkg.newChild(None, 'file', None)
        ghost = utf8String(ghost)
        files.addContent(ghost)
        files.newProp('type', 'ghost')
    return pkg
       
def otherXML(doc, node, rpmObj):
    pkg = node.newChild(None, 'package', None)
    pkg.newProp('pkgid', rpmObj.pkgid)
    pkg.newProp('name', rpmObj.tagByName('name'))
    pkg.newProp('arch', rpmObj.arch())
    version = pkg.newChild(None, 'version', None)
    version.newProp('epoch', str(rpmObj.epoch()))
    version.newProp('ver', str(rpmObj.tagByName('version')))
    version.newProp('rel', str(rpmObj.tagByName('release')))
    clogs = rpmObj.changelogLists()
    for (name, time, text) in clogs:
        clog = pkg.newChild(None, 'changelog', None)
        clog.addContent(utf8String(text))
        clog.newProp('author', utf8String(name))
        clog.newProp('date', str(time))
    return pkg
    
def repoXML(node, cmds):
    """generate the repomd.xml file that stores the info on the other files"""
    sumtype = cmds['sumtype']
    workfiles = [(cmds['otherfile'], 'other',),
                 (cmds['filelistsfile'], 'filelists'),
                 (cmds['primaryfile'], 'primary')]
    
    
    for (file, ftype) in workfiles:
        zfo = _gzipOpen(os.path.join(cmds['outputdir'], cmds['tempdir'], file))
        uncsum = getChecksum(sumtype, zfo)
        zfo.close()
        csum = getChecksum(sumtype, os.path.join(cmds['outputdir'], cmds['tempdir'], file))
        timestamp = os.stat(os.path.join(cmds['outputdir'], cmds['tempdir'], file))[8]
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
        csum = getChecksum(sumtype, fo)
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
