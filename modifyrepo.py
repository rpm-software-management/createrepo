#!/usr/bin/python
# This tools is used to insert arbitrary metadata into an RPM repository.
# Example:
#           ./modifyrepo.py updateinfo.xml myrepo/repodata
# or in Python:
#           >>> from modifyrepo import RepoMetadata
#           >>> repomd = RepoMetadata('myrepo/repodata')
#           >>> repomd.add('updateinfo.xml')
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# (C) Copyright 2006  Red Hat, Inc.
# Luke Macken <lmacken@redhat.com>
# modified by Seth Vidal 2008

import os
import sys
from createrepo import __version__
from createrepo.utils import checksum_and_rename, GzipFile, MDError
from yum.misc import checksum

from yum.repoMDObject import RepoMD, RepoMDError, RepoData
from xml.dom import minidom
from optparse import OptionParser


class RepoMetadata:

    def __init__(self, repo):
        """ Parses the repomd.xml file existing in the given repo directory. """
        self.repodir = os.path.abspath(repo)
        self.repomdxml = os.path.join(self.repodir, 'repomd.xml')
        self.checksum_type = 'sha256'

        if not os.path.exists(self.repomdxml):
            raise MDError, '%s not found' % self.repomdxml

        try:
            self.repoobj = RepoMD(self.repodir)
            self.repoobj.parse(self.repomdxml)
        except RepoMDError, e:
            raise MDError, 'Could not parse %s' % self.repomdxml


    def add(self, metadata, mdtype=None):
        """ Insert arbitrary metadata into this repository.
            metadata can be either an xml.dom.minidom.Document object, or
            a filename.
        """
        md = None
        if not metadata:
            raise MDError, 'metadata cannot be None'
        if isinstance(metadata, minidom.Document):
            md = metadata.toxml()
            mdname = 'updateinfo.xml'
        elif isinstance(metadata, str):
            if os.path.exists(metadata):
                if metadata.endswith('.gz'):
                    oldmd = GzipFile(filename=metadata, mode='rb')
                else:
                    oldmd = file(metadata, 'r')
                md = oldmd.read()
                oldmd.close()
                mdname = os.path.basename(metadata)
            else:
                raise MDError, '%s not found' % metadata
        else:
            raise MDError, 'invalid metadata type'

        ## Compress the metadata and move it into the repodata
        if not mdname.endswith('.gz'):
            mdname += '.gz'
        if not mdtype:
            mdtype = mdname.split('.')[0]
            
        destmd = os.path.join(self.repodir, mdname)
        newmd = GzipFile(filename=destmd, mode='wb')
        newmd.write(md)
        newmd.close()
        print "Wrote:", destmd

        open_csum = checksum(self.checksum_type, metadata)
        csum, destmd = checksum_and_rename(destmd, self.checksum_type)
        base_destmd = os.path.basename(destmd)


        ## Remove any stale metadata
        if mdtype in self.repoobj.repoData:
            del self.repoobj.repoData[mdtype]
            

        new_rd = RepoData()
        new_rd.type = mdtype
        new_rd.location = (None, 'repodata/' + base_destmd)
        new_rd.checksum = (self.checksum_type, csum)
        new_rd.openchecksum = (self.checksum_type, open_csum)
        new_rd.size = str(os.stat(destmd).st_size)
        new_rd.timestamp = str(os.stat(destmd).st_mtime)
        self.repoobj.repoData[new_rd.type] = new_rd
        
        print "           type =", new_rd.type
        print "       location =", new_rd.location[1]
        print "       checksum =", new_rd.checksum[1]
        print "      timestamp =", new_rd.timestamp
        print "  open-checksum =", new_rd.openchecksum[1]

        ## Write the updated repomd.xml
        outmd = file(self.repomdxml, 'w')
        outmd.write(self.repoobj.dump_xml())
        outmd.close()
        print "Wrote:", self.repomdxml


def main(args):
    parser = OptionParser(version='modifyrepo version %s' % __version__)
    # query options
    parser.add_option("--mdtype", dest='mdtype',
                      help="specific datatype of the metadata, will be derived from the filename if not specified")
    parser.usage = "modifyrepo [options] <input_metadata> <output repodata>"
    
    (opts, argsleft) = parser.parse_args(args)
    if len(argsleft) != 2:
        parser.print_usage()
        return 0
    metadata = argsleft[0]
    repodir = argsleft[1]
    try:
        repomd = RepoMetadata(repodir)
    except MDError, e:
        print "Could not access repository: %s" % str(e)
        return 1
    try:
        repomd.add(metadata, mdtype=opts.mdtype)
    except MDError, e:
        print "Could not add metadata from file %s: %s" % (metadata, str(e))
        return 1

if __name__ == '__main__':
    ret = main(sys.argv[1:])
    sys.exit(ret)
