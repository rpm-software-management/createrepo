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
# Copyright 2008  Red Hat, Inc - written by seth vidal skvidal at fedoraproject.org

# merge repos from arbitrary repo urls

import sys
import createrepo.merge
from optparse import OptionParser

#TODO:
# excludes?

def parse_args(args):
    usage = """
    mergerepo: take 2 or more repositories and merge their metadata into a new repo
              
    mergerepo --repo=url --repo=url --outputdir=/some/path"""
    
    parser = OptionParser(version = "mergerepo 0.1", usage=usage)
    # query options
    parser.add_option("-r", "--repo", dest='repos', default=[], action="append",
                      help="repo url")
    parser.add_option("-a", "--archlist", default=[], action="append",
                      help="Defaults to all arches - otherwise specify arches")
    parser.add_option("-d", "--database", default=False, action="store_true")
    parser.add_option("-o", "--outputdir", default=None, 
                      help="Location to create the repository")
    parser.add_option("", "--nogroups", default=False, action="store_true",
                      help="Do not merge group(comps) metadata")
    parser.add_option("", "--noupdateinfo", default=False, action="store_true",
                      help="Do not merge updateinfo metadata")
    (opts, argsleft) = parser.parse_args()

    if len(opts.repos) < 2:
        parser.print_usage()
        sys.exit(1)

    # sort out the comma-separated crap we somehow inherited.    
    archlist = []
    for a in opts.archlist:
        for arch in a.split(','):
             archlist.append(arch)

    opts.archlist = archlist
    
    return opts
    
def main(args):
    opts = parse_args(args)
    rm = createrepo.merge.RepoMergeBase(opts.repos)
    if opts.archlist:
        rm.archlist = opts.archlist
    if opts.outputdir:
        rm.outputdir = opts.outputdir
    if opts.database:
        rm.mdconf.database = True
    if opts.nogroups:
        rm.groups = False
    if opts.noupdateinfo:
        rm.updateinfo = False

    rm.merge_repos()
    rm.write_metadata()

if __name__ == "__main__":
    main(sys.argv[1:])
