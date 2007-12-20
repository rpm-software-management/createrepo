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


import os
import sys
import getopt
import shutil


# for now, for later, we move all this around
import createrepo
from createrepo import MDError
import createrepo.yumbased
import createrepo.utils

from createrepo.utils import _gzipOpen, errorprint, _

__version__ = '0.9'

# cli
def usage(retval=1):
    print _("""
    createrepo [options] directory-of-packages

    Options:
     -u, --baseurl <url> = optional base url location for all files
     -o, --outputdir <dir> = optional directory to output to
     -x, --exclude = files globs to exclude, can be specified multiple times
     -q, --quiet = run quietly
     -n, --noepoch = don't add zero epochs for non-existent epochs
                    (incompatible with yum and smart but required for
                     systems with rpm < 4.2.1)
     -g, --groupfile <filename> to point to for group information (precreated)
                    (<filename> relative to directory-of-packages)
     -v, --verbose = run verbosely
     -c, --cachedir <dir> = specify which dir to use for the checksum cache
     -C, --checkts = don't generate repo metadata, if their ctimes are newer
                     than the rpm ctimes.
     -i, --pkglist = use only these files from the directory specified
     -h, --help = show this help
     -V, --version = output version
     -p, --pretty = output xml files in pretty format.
     --update = update existing metadata (if present)
     -d, --database = generate the sqlite databases.
    """)

    sys.exit(retval)

# module

def checkAndMakeDir(dir):
    """
     check out the dir and make it, if possible, return 1 if done, else return 0
    """
    if os.path.exists(dir):
        if not os.path.isdir(dir):
            errorprint(_('%s is not a dir') % dir)
            result = False
        else:
            if not os.access(dir, os.W_OK):
                errorprint(_('%s is not writable') % dir)
                result = False
            else:
                result = True
    else:
        try:
            os.mkdir(dir)
        except OSError, e:
            errorprint(_('Error creating dir %s: %s') % (dir, e))
            result = False
        else:
            result = True
    return result

def parseArgs(args):
    """
       Parse the command line args return a commands dict and directory.
       Sanity check all the things being passed in.
    """
    cmds = {}
    cmds['quiet'] = 0
    cmds['verbose'] = 0
    cmds['excludes'] = []
    cmds['baseurl'] = None
    cmds['groupfile'] = None
    cmds['sumtype'] = 'sha'
    cmds['noepoch'] = False
    cmds['pretty'] = 0
#    cmds['updategroupsonly'] = 0
    cmds['cachedir'] = None
    cmds['basedir'] = os.getcwd()
    cmds['cache'] = False
    cmds['checkts'] = False
    cmds['mdtimestamp'] = 0
    cmds['split'] = False
    cmds['update'] = False
    cmds['outputdir'] = ""
    cmds['database'] = False
    cmds['file-pattern-match'] = ['.*bin\/.*', '^\/etc\/.*', '^\/usr\/lib\/sendmail$']
    cmds['dir-pattern-match'] = ['.*bin\/.*', '^\/etc\/.*']
    cmds['skip-symlinks'] = False
    cmds['pkglist'] = []

    try:
        gopts, argsleft = getopt.getopt(args, 'phqVvndg:s:x:u:c:o:CSi:', ['help', 'exclude=',
                                                                  'quiet', 'verbose', 'cachedir=', 'basedir=',
                                                                  'baseurl=', 'groupfile=', 'checksum=',
                                                                  'version', 'pretty', 'split', 'outputdir=',
                                                                  'noepoch', 'checkts', 'database', 'update',
                                                                  'skip-symlinks', 'pkglist='])
    except getopt.error, e:
        errorprint(_('Options Error: %s.') % e)
        usage()

    try:
        for arg,a in gopts:
            if arg in ['-h','--help']:
                usage(retval=0)
            elif arg in ['-V', '--version']:
                print '%s' % __version__
                sys.exit(0)
            elif arg == '--split':
                cmds['split'] = True
    except ValueError, e:
        errorprint(_('Options Error: %s') % e)
        usage()


    # make sure our dir makes sense before we continue
    if len(argsleft) > 1 and not cmds['split']:
        errorprint(_('Error: Only one directory allowed per run.'))
        usage()
    elif len(argsleft) == 0:
        errorprint(_('Error: Must specify a directory to index.'))
        usage()
    else:
        directories = argsleft

    try:
        for arg,a in gopts:
            if arg in ['-v', '--verbose']:
                cmds['verbose'] = 1
            elif arg in ["-q", '--quiet']:
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
                    cmds['groupfile'] = a
            elif arg in ['-x', '--exclude']:
                cmds['excludes'].append(a)
            elif arg in ['-p', '--pretty']:
                cmds['pretty'] = 1
#            elif arg in ['--update-groups-only']:
#                cmds['updategroupsonly'] = 1
            elif arg in ['-s', '--checksum']:
                errorprint(_('This option is deprecated'))
            elif arg in ['-c', '--cachedir']:
                cmds['cache'] = True
                cmds['cachedir'] = a
            elif arg == '--update':
                cmds['update'] = True
            elif arg in ['-C', '--checkts']:
                cmds['checkts'] = True
            elif arg == '--basedir':
                cmds['basedir'] = a
            elif arg in ['-o','--outputdir']:
                cmds['outputdir'] = a
            elif arg in ['-n', '--noepoch']:
                cmds['noepoch'] = True
            elif arg in ['-d', '--database']:
                cmds['database'] = True
            elif arg in ['-S', '--skip-symlinks']:
                cmds['skip-symlinks'] = True
            elif arg in ['-i', '--pkglist']:
                cmds['pkglist'] = a
                                
    except ValueError, e:
        errorprint(_('Options Error: %s') % e)
        usage()

    if cmds['split'] and cmds['checkts']:
        errorprint(_('--split and --checkts options are mutually exclusive'))
        sys.exit(1)

    directory = directories[0]

    directory = os.path.normpath(directory)
    if cmds['split']:
        pass
    elif os.path.isabs(directory):
        cmds['basedir'] = os.path.dirname(directory)
        directory = os.path.basename(directory)
    else:
        cmds['basedir'] = os.path.realpath(cmds['basedir'])
    if not cmds['outputdir']:
        cmds['outputdir'] = os.path.join(cmds['basedir'], directory)
    if cmds['groupfile']:
        a = cmds['groupfile']
        if cmds['split']:
            a = os.path.join(cmds['basedir'], directory, cmds['groupfile'])
        elif not os.path.isabs(a):
            a = os.path.join(cmds['basedir'], directory, cmds['groupfile'])
        if not os.path.exists(a):
            errorprint(_('Error: groupfile %s cannot be found.' % a))
            usage()
        cmds['groupfile'] = a
    if cmds['cachedir']:
        a = cmds ['cachedir']
        if not os.path.isabs(a):
            a = os.path.join(cmds['outputdir'] ,a)
        if not checkAndMakeDir(a):
            errorprint(_('Error: cannot open/write to cache dir %s' % a))
            usage()
        cmds['cachedir'] = a

    if cmds['pkglist']:
        lst = []
        pfo = open(cmds['pkglist'], 'r')
        for line in pfo.readlines():
            line = line.replace('\n', '')
            lst.append(line)
        pfo.close()
            
        cmds['pkglist'] = lst
        
    #setup some defaults
    cmds['primaryfile'] = 'primary.xml.gz'
    cmds['filelistsfile'] = 'filelists.xml.gz'
    cmds['otherfile'] = 'other.xml.gz'
    cmds['repomdfile'] = 'repomd.xml'
    cmds['tempdir'] = '.repodata'
    cmds['finaldir'] = 'repodata'
    cmds['olddir'] = '.olddata'

    # Fixup first directory
    directories[0] = directory
    return cmds, directories

def main(args):
    cmds, directories = parseArgs(args)
    directory = directories[0]
    testdir = os.path.realpath(os.path.join(cmds['basedir'], directory))
    # start the sanity/stupidity checks
    if not os.path.exists(testdir):
        errorprint(_('Directory %s must exist') % (directory,))
        sys.exit(1)

    if not os.path.isdir(testdir):
        errorprint(_('%s - must be a directory') 
                   % (directory,))
        sys.exit(1)

    if not os.access(cmds['outputdir'], os.W_OK):
        errorprint(_('Directory %s must be writable.') % (cmds['outputdir'],))
        sys.exit(1)

    if cmds['split']:
        oldbase = cmds['basedir']
        cmds['basedir'] = os.path.join(cmds['basedir'], directory)
    if not checkAndMakeDir(os.path.join(cmds['outputdir'], cmds['tempdir'])):
        sys.exit(1)

    if not checkAndMakeDir(os.path.join(cmds['outputdir'], cmds['finaldir'])):
        sys.exit(1)

    if os.path.exists(os.path.join(cmds['outputdir'], cmds['olddir'])):
        errorprint(_('Old data directory exists, please remove: %s') % cmds['olddir'])
        sys.exit(1)

    # make sure we can write to where we want to write to:
    for direc in ['tempdir', 'finaldir']:
        for f in ['primaryfile', 'filelistsfile', 'otherfile', 'repomdfile']:
            filepath = os.path.join(cmds['outputdir'], cmds[direc], cmds[f])
            if os.path.exists(filepath):
                if not os.access(filepath, os.W_OK):
                    errorprint(_('error in must be able to write to metadata files:\n  -> %s') % filepath)
                    usage()
                if cmds['checkts']:
                    ts = os.path.getctime(filepath)
                    if ts > cmds['mdtimestamp']:
                        cmds['mdtimestamp'] = ts
        
    if cmds['split']:
        cmds['basedir'] = oldbase
        mdgen = createrepo.SplitMetaDataGenerator(cmds)
        mdgen.doPkgMetadata(directories)
    else:
        mdgen = createrepo.MetaDataGenerator(cmds)
        if cmds['checkts'] and mdgen.checkTimeStamps(directory):
            if cmds['verbose']:
                print _('repo is up to date')
            sys.exit(0)
        mdgen.doPkgMetadata(directory)
    mdgen.doRepoMetadata()

    if os.path.exists(os.path.join(cmds['outputdir'], cmds['finaldir'])):
        try:
            os.rename(os.path.join(cmds['outputdir'], cmds['finaldir']),
                      os.path.join(cmds['outputdir'], cmds['olddir']))
        except:
            errorprint(_('Error moving final %s to old dir %s' % (os.path.join(cmds['outputdir'], cmds['finaldir']),
                                                                  os.path.join(cmds['outputdir'], cmds['olddir']))))
            sys.exit(1)

    try:
        os.rename(os.path.join(cmds['outputdir'], cmds['tempdir']),
                  os.path.join(cmds['outputdir'], cmds['finaldir']))
    except:
        errorprint(_('Error moving final metadata into place'))
        # put the old stuff back
        os.rename(os.path.join(cmds['outputdir'], cmds['olddir']),
                  os.path.join(cmds['outputdir'], cmds['finaldir']))
        sys.exit(1)

    for f in ['primaryfile', 'filelistsfile', 'otherfile', 'repomdfile', 'groupfile']:
        if cmds[f]:
            fn = os.path.basename(cmds[f])
        else:
            continue
        oldfile = os.path.join(cmds['outputdir'], cmds['olddir'], fn)
        if os.path.exists(oldfile):
            try:
                os.remove(oldfile)
            except OSError, e:
                errorprint(_('Could not remove old metadata file: %s') % oldfile)
                errorprint(_('Error was %s') % e)
                sys.exit(1)

    # Move everything else back from olddir (eg. repoview files)
    olddir = os.path.join(cmds['outputdir'], cmds['olddir'])
    finaldir = os.path.join(cmds['outputdir'], cmds['finaldir'])
    for f in os.listdir(olddir):
        oldfile = os.path.join(olddir, f)
        finalfile = os.path.join(finaldir, f)
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
        os.rmdir(os.path.join(cmds['outputdir'], cmds['olddir']))
    except OSError, e:
        errorprint(_('Could not remove old metadata dir: %s') % cmds['olddir'])
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
