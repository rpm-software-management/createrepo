import exceptions
import os
import sys
import libxml2
import hashlib
from yum import misc

try:
    import sqlitecachec
except ImportError:
    pass


from utils import _gzipOpen, bzipFile


__version__ = '0.9'


class MDError(exceptions.Exception):
    def __init__(self, value=None):
        exceptions.Exception.__init__(self)
        self.value = value
    
    def __str__(self):
        return self.value

def repoXML(node, cmds):
    """generate the repomd.xml file that stores the info on the other files"""
    sumtype = cmds['sumtype']
    workfiles = [(cmds['otherfile'], 'other',),
                 (cmds['filelistsfile'], 'filelists'),
                 (cmds['primaryfile'], 'primary')]
    repoid='garbageid'
    
    repopath = os.path.join(cmds['outputdir'], cmds['tempdir'])
    
    if cmds['database']:
        try:
            dbversion = str(sqlitecachec.DBVERSION)
        except AttributeError:
            dbversion = '9'
        rp = sqlitecachec.RepodataParserSqlite(repopath, repoid, None)

    for (file, ftype) in workfiles:
        complete_path = os.path.join(repopath, file)
        
        zfo = _gzipOpen(complete_path)
        uncsum = misc.checksum(sumtype, zfo)
        zfo.close()
        csum = misc.checksum(sumtype, complete_path)
        timestamp = os.stat(complete_path)[8]
        
        db_csums = {}
        db_compressed_sums = {}
        
        if cmds['database']:
            if ftype == 'primary':
                rp.getPrimary(complete_path, csum)
                            
            elif ftype == 'filelists':
                rp.getFilelists(complete_path, csum)
                
            elif ftype == 'other':
                rp.getOtherdata(complete_path, csum)
            

            tmp_result_name = '%s.xml.gz.sqlite' % ftype
            tmp_result_path = os.path.join(repopath, tmp_result_name)
            good_name = '%s.sqlite' % ftype
            resultpath = os.path.join(repopath, good_name)
            
            # rename from silly name to not silly name
            os.rename(tmp_result_path, resultpath)
            compressed_name = '%s.bz2' % good_name
            result_compressed = os.path.join(repopath, compressed_name)
            db_csums[ftype] = misc.checksum(sumtype, resultpath)
            
            # compress the files
            bzipFile(resultpath, result_compressed)
            # csum the compressed file
            db_compressed_sums[ftype] = misc.checksum(sumtype, result_compressed)
            # remove the uncompressed file
            os.unlink(resultpath)

            # timestamp the compressed file
            db_timestamp = os.stat(result_compressed)[8]
            
            # add this data as a section to the repomdxml
            db_data_type = '%s_db' % ftype
            data = node.newChild(None, 'data', None)
            data.newProp('type', db_data_type)
            location = data.newChild(None, 'location', None)
            if cmds['baseurl'] is not None:
                location.newProp('xml:base', cmds['baseurl'])
            
            location.newProp('href', os.path.join(cmds['finaldir'], compressed_name))
            checksum = data.newChild(None, 'checksum', db_compressed_sums[ftype])
            checksum.newProp('type', sumtype)
            db_tstamp = data.newChild(None, 'timestamp', str(db_timestamp))
            unchecksum = data.newChild(None, 'open-checksum', db_csums[ftype])
            unchecksum.newProp('type', sumtype)
            database_version = data.newChild(None, 'database_version', dbversion)
            
            
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
        csum = misc.checksum(sumtype, fo)
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


