#!/usr/bin/python
# util functions for createrepo
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



import os
import sys
import bz2
import gzip
from gzip import write32u, FNAME

def errorprint(stuff):
    print >> sys.stderr, stuff

def _(args):
    """Stub function for translation"""
    return args


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
    
def bzipFile(source, dest):
    
    s_fn = open(source, 'rb')
    destination = bz2.BZ2File(dest, 'w', compresslevel=9)

    while True:
        data = s_fn.read(1024000)
        
        if not data: break
        destination.write(data)

    destination.close()
    s_fn.close()
    

def returnFD(filename):
    try:
        fdno = os.open(filename, os.O_RDONLY)
    except OSError:
        raise MDError, "Error opening file"
    return fdno

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

def checkAndMakeDir(dir):
    """
     check out the dir and make it, if possible, return 1 if done, else return 0
    """
    if os.path.exists(dir):
        if not os.path.isdir(dir):
            #errorprint(_('%s is not a dir') % dir)
            result = False
        else:
            if not os.access(dir, os.W_OK):
                #errorprint(_('%s is not writable') % dir)
                result = False
            else:
                result = True
    else:
        try:
            os.mkdir(dir)
        except OSError, e:
            #errorprint(_('Error creating dir %s: %s') % (dir, e))
            result = False
        else:
            result = True
    return result

