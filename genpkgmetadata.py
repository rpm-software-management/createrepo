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
# Portions Copyright 2007  Red Hat, Inc - written by seth vidal skvidal at fedoraproject.org

import os
import sys
from optparse import OptionParser
import shutil


import createrepo
from createrepo import MDError
import createrepo.yumbased
import createrepo.utils

from createrepo.utils import _gzipOpen, errorprint, _, checkAndMakeDir


def parseArgs(args, conf):
    """
       Parse the command line args. return a config object.
       Sanity check all the things being passed in.
    """
    
    parser = OptionParser(version = "createrepo %s" % createrepo.__version__)
    # query options
    parser.add_option("-q", "--quiet", default=False, action="store_true",
                      help="output nothing except for serious errors")
    parser.add_option("-v", "--verbose", default=False, action="store_true",
                      help="output more debugging info.")
    parser.add_option("-x", "--excludes", default=[], action="append",
                      help="files to exclude")
    parser.add_option("--basedir", default=os.getcwd(),
                      help="basedir for path to directories")                      
    parser.add_option("-u", "--baseurl", default=None,
                      help="baseurl to append on all files")
    parser.add_option("-g", "--groupfile", default=None,
                      help="path to groupfile to include in metadata")
    parser.add_option("-s", "--checksum", default="sha", dest='sumtype',
                      help="Deprecated, ignore")
    parser.add_option("-n", "--noepoch", default=False, action="store_true",
                      help="don't add zero epochs for non-existent epochs"\
                         "(incompatible with yum and smart but required for" \
                         "systems with rpm < 4.2.1)")
    parser.add_option("-p", "--pretty", default=False, action="store_true",
                      help="make sure all xml generated is formatted")
    parser.add_option("-c", "--cachedir", default=None,
                      help="set path to cache dir")
    parser.add_option("-C", "--checkts", default=False, action="store_true",
      help="check timestamps on files vs the metadata to see if we need to update")
    parser.add_option("-d", "--database", default=False, action="store_true",
                      help="create sqlite database files")
    parser.add_option("--update", default=False, action="store_true",
                      help="use the existing repodata to speed up creation of new")
    parser.add_option("--skip-stat", dest='skip_stat', default=False, action="store_true",
                      help="skip the stat() call on a --update, assumes if the file" \
                            "name is the same then the file is still the same" \
                            "(only use this if you're fairly trusting or gullible)" )
    parser.add_option("--split", default=False, action="store_true",
                      help="generate split media")
    parser.add_option("-i", "--pkglist", default=None, 
        help="use only the files listed in this file from the directory specified")
    parser.add_option("-o", "--outputdir", default=None,
             help="<dir> = optional directory to output to")
    parser.add_option("-S", "--skip-symlinks", dest="skip_symlinks",
                      default=False, action="store_true",
                      help="ignore symlinks of packages")
    parser.add_option("--changelog-limit", dest="changelog_limit",
                      default=None, help="only import the last N changelog entries")
    parser.add_option("--unique-md-filenames", dest="unique_md_filenames",
                      default=False, action="store_true",
                      help="include the file's checksum in the filename, helps" \
                           "with proxies")
                           
    (opts, argsleft) = parser.parse_args()
    if len(argsleft) > 1 and not opts.split:
        errorprint(_('Error: Only one directory allowed per run.'))
        parser.print_usage()
        sys.exit(1)
        
    elif len(argsleft) == 0:
        errorprint(_('Error: Must specify a directory to index.'))
        parser.print_usage()
        sys.exit(1)
        
    else:
        directories = argsleft
    
    if opts.split and opts.checkts:
        errorprint(_('--split and --checkts options are mutually exclusive'))
        sys.exit(1)


    # let's switch over to using the conf object - put all the opts options into it
    for opt in parser.option_list:
        if opt.dest is None: # this is fairly silly
            continue
        setattr(conf, opt.dest, getattr(opts, opt.dest))
    
    directory = directories[0]
    conf.directory = directory
    conf.directories = directories

    lst = []
    if conf.pkglist:
        pfo = open(conf.pkglist, 'r')
        for line in pfo.readlines():
            line = line.replace('\n', '')
            lst.append(line)
        pfo.close()
            
    conf.pkglist = lst

    if conf.changelog_limit: # make sure it is an int, not a string
        conf.changelog_limit = int(conf.changelog_limit)
        
    return conf

class MDCallBack(object):
    def errorlog(self, thing):
        print >> sys.stderr, thing
        
    def log(self, thing):
        print thing
    
    def progress(self, item, current, total):
        sys.stdout.write('\r' + ' ' * 80)
        sys.stdout.write("\r%d/%d - %s" % (current, total, item))
        sys.stdout.flush()
        
def main(args):
    conf = createrepo.MetaDataConfig()
    conf = parseArgs(args, conf)

    try:
        if conf.split:
            mdgen = createrepo.SplitMetaDataGenerator(config_obj=conf, callback=MDCallBack())
        else:
            mdgen = createrepo.MetaDataGenerator(config_obj=conf, callback=MDCallBack())
            if mdgen.checkTimeStamps():
                if mdgen.conf.verbose:
                    print _('repo is up to date')
                sys.exit(0)

        mdgen.doPkgMetadata()
        mdgen.doRepoMetadata()
        mdgen.doFinalMove()
        
    except MDError, e:
        errorprint(_('%s') % e)
        sys.exit(1)


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
