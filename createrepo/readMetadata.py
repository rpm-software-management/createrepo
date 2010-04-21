#!/usr/bin/python -t

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
# Copyright 2006 Red Hat

import os
import libxml2
import stat
from utils import errorprint, _

from yum import repoMDObject


class MetadataIndex(object):

    def __init__(self, outputdir, opts=None):
        if opts is None:
            opts = {}
        self.opts = opts
        self.outputdir = outputdir
        repodatadir = self.outputdir + '/repodata'
        myrepomdxml = repodatadir + '/repomd.xml'
        if os.path.exists(myrepomdxml):
            repomd = repoMDObject.RepoMD('garbageid', myrepomdxml)
            b = repomd.getData('primary').location[1]
            f = repomd.getData('filelists').location[1]
            o = repomd.getData('other').location[1]
            basefile = os.path.join(self.outputdir, b)
            filelistfile = os.path.join(self.outputdir, f)
            otherfile = os.path.join(self.outputdir, o)
        else:
            basefile = filelistfile = otherfile = ""

        self.files = {'base' : basefile,
                      'filelist' : filelistfile,
                      'other' : otherfile}
        self.scan()

    def scan(self):
        """Read in and index old repo data"""
        self.basenodes = {}
        self.filesnodes = {}
        self.othernodes = {}
        self.pkg_ids = {}
        if self.opts.get('verbose'):
            print _("Scanning old repo data")
        for fn in self.files.values():
            if not os.path.exists(fn):
                #cannot scan
                errorprint(_("Warning: Old repodata file missing: %s") % fn)
                return
        root = libxml2.parseFile(self.files['base']).getRootElement()
        self._scanPackageNodes(root, self._handleBase)
        if self.opts.get('verbose'):
            print _("Indexed %i base nodes" % len(self.basenodes))
        root = libxml2.parseFile(self.files['filelist']).getRootElement()
        self._scanPackageNodes(root, self._handleFiles)
        if self.opts.get('verbose'):
            print _("Indexed %i filelist nodes" % len(self.filesnodes))
        root = libxml2.parseFile(self.files['other']).getRootElement()
        self._scanPackageNodes(root, self._handleOther)
        if self.opts.get('verbose'):
            print _("Indexed %i other nodes" % len(self.othernodes))
        #reverse index pkg ids to track references
        self.pkgrefs = {}
        for relpath, pkgid in self.pkg_ids.iteritems():
            self.pkgrefs.setdefault(pkgid,[]).append(relpath)

    def _scanPackageNodes(self, root, handler):
        node = root.children
        while node is not None:
            if node.type != "element":
                node = node.next
                continue
            if node.name == "package":
                handler(node)
            node = node.next

    def _handleBase(self, node):
        top = node
        node = node.children
        pkgid = None
        mtime = None
        size = None
        relpath = None
        do_stat = self.opts.get('do_stat', True)
        while node is not None:
            if node.type != "element":
                node = node.next
                continue
            if node.name == "checksum":
                pkgid = node.content
            elif node.name == "time":
                mtime = int(node.prop('file'))
            elif node.name == "size":
                size = int(node.prop('package'))
            elif node.name == "location":
                relpath = node.prop('href')
            node = node.next
        if relpath is None:
            print _("Incomplete data for node")
            return
        if pkgid is None:
            print _("pkgid missing for %s") % relpath
            return
        if mtime is None:
            print _("mtime missing for %s") % relpath
            return
        if size is None:
            print _("size missing for %s") % relpath
            return
        if do_stat:
            filepath = os.path.join(self.opts['pkgdir'], relpath)
            try:
                st = os.stat(filepath)
            except OSError:
                #file missing -- ignore
                return
            if not stat.S_ISREG(st.st_mode):
                #ignore non files
                return
            #check size and mtime
            if st.st_size != size:
                if self.opts.get('verbose'):
                    print _("Size (%i -> %i) changed for file %s") % (size,st.st_size,filepath)
                return
            if int(st.st_mtime) != mtime:
                if self.opts.get('verbose'):
                    print _("Modification time changed for %s") % filepath
                return
        #otherwise we index
        self.basenodes[relpath] = top
        self.pkg_ids[relpath] = pkgid

    def _handleFiles(self, node):
        pkgid = node.prop('pkgid')
        if pkgid:
            self.filesnodes[pkgid] = node

    def _handleOther(self, node):
        pkgid = node.prop('pkgid')
        if pkgid:
            self.othernodes[pkgid] = node

    def getNodes(self, relpath):
        """Return base, filelist, and other nodes for file, if they exist

        Returns a tuple of nodes, or None if not found
        """
        bnode = self.basenodes.get(relpath,None)
        if bnode is None:
            return None
        pkgid = self.pkg_ids.get(relpath,None)
        if pkgid is None:
            print _("No pkgid found for: %s") % relpath
            return None
        fnode = self.filesnodes.get(pkgid,None)
        if fnode is None:
            return None
        onode = self.othernodes.get(pkgid,None)
        if onode is None:
            return None
        return bnode, fnode, onode

    def freeNodes(self,relpath):
        #causing problems
        """Free up nodes corresponding to file, if possible"""
        bnode = self.basenodes.get(relpath,None)
        if bnode is None:
            print "Missing node for %s" % relpath
            return
        bnode.unlinkNode()
        bnode.freeNode()
        del self.basenodes[relpath]
        pkgid = self.pkg_ids.get(relpath,None)
        if pkgid is None:
            print _("No pkgid found for: %s") % relpath
            return None
        del self.pkg_ids[relpath]
        dups = self.pkgrefs.get(pkgid)
        dups.remove(relpath)
        if len(dups):
            #still referenced
            return
        del self.pkgrefs[pkgid]
        for nodes in self.filesnodes, self.othernodes:
            node = nodes.get(pkgid)
            if node is not None:
                node.unlinkNode()
                node.freeNode()
                del nodes[pkgid]


if __name__ == "__main__":
    cwd = os.getcwd()
    opts = {'verbose':1,
            'pkgdir': cwd}

    idx = MetadataIndex(cwd, opts)
    for fn in idx.basenodes.keys():
        a,b,c, = idx.getNodes(fn)
        a.serialize()
        b.serialize()
        c.serialize()
        idx.freeNodes(fn)
