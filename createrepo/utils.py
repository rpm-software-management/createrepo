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
import os.path
import sys
import bz2
import gzip
from gzip import write32u, FNAME
from yum import misc
_available_compression = ['gz', 'bz2']
try:
    import lzma
    _available_compression.append('xz')
except ImportError:
    lzma = None

def errorprint(stuff):
    print >> sys.stderr, stuff

def _(args):
    """Stub function for translation"""
    return args


class GzipFile(gzip.GzipFile):
    def _write_gzip_header(self):
        self.fileobj.write('\037\213')             # magic header
        self.fileobj.write('\010')                 # compression method
        if hasattr(self, 'name'):
            fname = self.name[:-3]
        else:
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


def xzFile(source, dest):
    if not 'xz' in _available_compression:
        raise MDError, "Cannot use xz for compression, library/module is not available"
        
    s_fn = open(source, 'rb')
    destination = lzma.LZMAFile(dest, 'w')

    while True:
        data = s_fn.read(1024000)

        if not data: break
        destination.write(data)

    destination.close()
    s_fn.close()

def gzFile(source, dest):
        
    s_fn = open(source, 'rb')
    destination = GzipFile(dest, 'w')

    while True:
        data = s_fn.read(1024000)

        if not data: break
        destination.write(data)

    destination.close()
    s_fn.close()



def compressFile(source, dest, compress_type):
    """Compress an existing file using any compression type from source to dest"""
    
    if compress_type == 'xz':
        xzFile(source, dest)
    elif compress_type == 'bz2':
        bzipFile(source, dest)
    elif compress_type == 'gz':
        gzFile(source, dest)
    else:
        raise MDError, "Unknown compression type %s" % compress_type
    
def compressOpen(fn, mode='rb', compress_type=None):
    
    if not compress_type:
        # we are readonly and we don't give a compress_type - then guess based on the file extension
        compress_type = fn.split('.')[-1]
        if compress_type not in _available_compression:
            compress_type = 'gz'
            
    if compress_type == 'xz':
        return lzma.LZMAFile(fn, mode)
    elif compress_type == 'bz2':
        return bz2.BZ2File(fn, mode)
    elif compress_type == 'gz':
        return _gzipOpen(fn, mode)
    else:
        raise MDError, "Unknown compression type %s" % compress_type
    
def returnFD(filename):
    try:
        fdno = os.open(filename, os.O_RDONLY)
    except OSError:
        raise MDError, "Error opening file"
    return fdno

def checkAndMakeDir(directory):
    """
     check out the directory and make it, if possible, return 1 if done, else return 0
    """
    if os.path.exists(directory):
        if not os.path.isdir(directory):
            #errorprint(_('%s is not a dir') % directory)
            result = False
        else:
            if not os.access(directory, os.W_OK):
                #errorprint(_('%s is not writable') % directory)
                result = False
            else:
                result = True
    else:
        try:
            os.mkdir(directory)
        except OSError, e:
            #errorprint(_('Error creating dir %s: %s') % (directory, e))
            result = False
        else:
            result = True
    return result

def checksum_and_rename(fn_path, sumtype='sha256'):
    """checksum the file rename the file to contain the checksum as a prefix
       return the new filename"""
    csum = misc.checksum(sumtype, fn_path)
    fn = os.path.basename(fn_path)
    fndir = os.path.dirname(fn_path)
    csum_fn = csum + '-' + fn
    csum_path = os.path.join(fndir, csum_fn)
    os.rename(fn_path, csum_path)
    return (csum, csum_path)



def encodefilenamelist(filenamelist):
    return '/'.join(filenamelist)

def encodefiletypelist(filetypelist):
    result = ''
    ftl = {'file':'f', 'dir':'d', 'ghost':'g'}
    for x in filetypelist:
        result += ftl[x]
    return result

def split_list_into_equal_chunks(seq, num_chunks):
    avg = len(seq) / float(num_chunks)
    out = []
    last = 0.0
    while last < len(seq):
        out.append(seq[int(last):int(last + avg)])
        last += avg

    return out


class MDError(Exception):
    def __init__(self, value=None):
        Exception.__init__(self)
        self.value = value

    def __str__(self):
        return self.value
