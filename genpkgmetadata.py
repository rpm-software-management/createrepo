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


# for now, for later, we move all this around
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
    parser.add_option("-u", "--baseurl", default=None)
    parser.add_option("-g", "--groupfile", default=None)
    parser.add_option("-s", "--checksum", default="sha", dest='sumtype')
    parser.add_option("-n", "--noepoch", default=False, action="store_true")
    parser.add_option("-p", "--pretty", default=False, action="store_true")
    parser.add_option("-c", "--cachedir", default=None)
    parser.add_option("--basedir", default=os.getcwd())
    parser.add_option("-C", "--checkts", default=False, action="store_true")
    parser.add_option("-d", "--database", default=False, action="store_true")
    parser.add_option("--update", default=False, action="store_true")
    parser.add_option("--split", default=False, action="store_true")
    parser.add_option("-i", "--pkglist", default=False, action="store_true")
    parser.add_option("-o", "--outputdir", default="")
    parser.add_option("-S", "--skip-symlinks", dest="skip_symlinks",
                      default=False, action="store_true")

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
    directory = os.path.normpath(directory)
    if conf.split:
        pass
    elif os.path.isabs(directory):
        conf.basedir = os.path.dirname(directory)
        directory = os.path.basename(directory)
    else:
        conf.basedir = os.path.realpath(conf.basedir)

   
    if not opts.outputdir:
        conf.outputdir = os.path.join(conf.basedir, directory)
    if conf.groupfile:
        a = conf.groupfile
        if conf.split:
            a = os.path.join(conf.basedir, directory, conf.groupfile)
        elif not os.path.isabs(a):
            a = os.path.join(conf.basedir, directory, conf.groupfile)
        if not os.path.exists(a):
            errorprint(_('Error: groupfile %s cannot be found.' % a))
            usage()
        conf.groupfile = a
    if conf.cachedir:
        conf.cache = True
        a = conf.cachedir
        if not os.path.isabs(a):
            a = os.path.join(conf.outputdir ,a)
        if not checkAndMakeDir(a):
            errorprint(_('Error: cannot open/write to cache dir %s' % a))
            parser.print_usage()
        conf.cachedir = a

    if conf.pkglist:
        lst = []
        pfo = open(conf.pkglist, 'r')
        for line in pfo.readlines():
            line = line.replace('\n', '')
            lst.append(line)
        pfo.close()
            
        conf.pkglist = lst
        
    #setup some defaults

    # Fixup first directory
    directories[0] = directory
    conf.directory = directory
    conf.directories = directories

    return conf

def main(args):
    conf = createrepo.MetaDataConfig()
    conf = parseArgs(args, conf)
    # FIXME - some of these should be moved into the module and out of the cli routines        
    testdir = os.path.realpath(os.path.join(conf.basedir, conf.directory))
    # start the sanity/stupidity checks
    if not os.path.exists(testdir):
        errorprint(_('Directory %s must exist') % (conf.directory,))
        sys.exit(1)

    if not os.path.isdir(testdir):
        errorprint(_('%s - must be a directory') 
                   % (conf.directory,))
        sys.exit(1)

    if not os.access(conf.outputdir, os.W_OK):
        errorprint(_('Directory %s must be writable.') % (conf.outputdir,))
        sys.exit(1)

    if conf.split:
        oldbase = conf.basedir
        conf.basedir = os.path.join(conf.basedir, conf.directory)
    if not checkAndMakeDir(os.path.join(conf.outputdir, conf.tempdir)):
        sys.exit(1)

    if not checkAndMakeDir(os.path.join(conf.outputdir, conf.finaldir)):
        sys.exit(1)

    if os.path.exists(os.path.join(conf.outputdir, conf.olddir)):
        errorprint(_('Old data directory exists, please remove: %s') % conf.olddir)
        sys.exit(1)

    # make sure we can write to where we want to write to:
    for direc in ['tempdir', 'finaldir']:
        for f in ['primaryfile', 'filelistsfile', 'otherfile', 'repomdfile']:
            filepath = os.path.join(conf.outputdir, direc, f)
            if os.path.exists(filepath):
                if not os.access(filepath, os.W_OK):
                    errorprint(_('error in must be able to write to metadata files:\n  -> %s') % filepath)
                    usage()
                if conf.checkts:
                    timestamp = os.path.getctime(filepath)
                    if timestamp > conf.mdtimestamp:
                        conf.mdtimestamp = timestamp
        
    if conf.split:
        conf.basedir = oldbase
        mdgen = createrepo.SplitMetaDataGenerator(config_obj=conf)
        mdgen.doPkgMetadata(directories)
    else:
        mdgen = createrepo.MetaDataGenerator(config_obj=conf)
        if mdgen.checkTimeStamps():
            if mdgen.conf.verbose:
                print _('repo is up to date')
            sys.exit(0)
        mdgen.doPkgMetadata()
    mdgen.doRepoMetadata()

    output_final_dir = os.path.join(mdgen.conf.outputdir, mdgen.conf.finaldir) 
    output_old_dir = os.path.join(mdgen.conf.outputdir, mdgen.conf.olddir)
    
    if os.path.exists(output_final_dir):
        try:
            os.rename(output_final_dir, output_old_dir)
        except:
            errorprint(_('Error moving final %s to old dir %s' % (output_final_dir,
                                                                 output_old_dir)))
            sys.exit(1)

    output_temp_dir =os.path.join(mdgen.conf.outputdir, mdgen.conf.tempdir)

    try:
        os.rename(output_temp_dir, output_final_dir)
    except:
        errorprint(_('Error moving final metadata into place'))
        # put the old stuff back
        os.rename(output_old_dir, output_final_dir)
        sys.exit(1)

    for f in ['primaryfile', 'filelistsfile', 'otherfile', 'repomdfile', 'groupfile']:
        if getattr(mdgen.conf, f):
            fn = os.path.basename(getattr(mdgen.conf, f))
        else:
            continue
        oldfile = os.path.join(output_old_dir, fn)

        if os.path.exists(oldfile):
            try:
                os.remove(oldfile)
            except OSError, e:
                errorprint(_('Could not remove old metadata file: %s') % oldfile)
                errorprint(_('Error was %s') % e)
                sys.exit(1)

    # Move everything else back from olddir (eg. repoview files)
    for f in os.listdir(output_old_dir):
        oldfile = os.path.join(output_old_dir, f)
        finalfile = os.path.join(output_final_dir, f)
        if os.path.exists(finalfile):
            # Hmph?  Just leave it alone, then.
            try:
                if os.path.isdir(oldfile):
                    shutil.rmtree(oldfile)
                else:
                    os.remove(oldfile)
            except OSError, e:
                errorprint(_('Could not remove old non-metadata file: %s') % oldfile)
                errorprint(_('Error was %s') % e)
                sys.exit(1)
        else:
            try:
                os.rename(oldfile, finalfile)
            except OSError, e:
                errorprint(_('Could not restore old non-metadata file: %s -> %s') % (oldfile, finalfile))
                errorprint(_('Error was %s') % e)
                sys.exit(1)

#XXX: fix to remove tree as we mung basedir
    try:
        os.rmdir(output_old_dir)
    except OSError, e:
        errorprint(_('Could not remove old metadata dir: %s') % mdgen.conf.olddir)
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
