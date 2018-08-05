from __future__ import print_function

import argparse
import fnmatch
import os
import os.path
import stat
import sys
import Queue
import logging
import re
import datetime
import shutil

from threading import Thread

from bloom_filter import BloomFilter
from tqdm import tqdm
from hachoir_core.error import HachoirError
from hachoir_core.cmd_line import unicodeFilename
from hachoir_parser import createParser
from hachoir_core.tools import makePrintable
from hachoir_metadata import extractMetadata
import hachoir_core.config

# Suppress metadata parse warnings
hachoir_core.config.quiet=True

UNKNOWN_PARTITION=0
DEFAULT_MIN_SIZE_KB=1
DEFAULT_FILE_EXTENSIONS='BMP,CUR,EMF,ICO,GIF,JPG,JPEG,PCX,PNG,TGA,TIFF,TIF,WMF,XCF,MKV,WMV,MOV,AVI,M4V,CR2,MP4,3GP,MPG'
DEFAULT_PARALLEL_WORKERS=10
QUEUE_TIMEOUT_SEC=30
WORK_BUFFER_SIZE=10000
EST_MAX_FILES_PER_YEAR=50000 

_start_time = datetime.datetime.now().isoformat()

ERROR_LOG_FILE = 'partition_error_%s.log' % _start_time
CMD_LOG_FILE = 'partition_command_%s.log' % _start_time

_formatter = logging.Formatter('[%(levelname)s] %(asctime)s - %(message)s')
_log_console_handler = logging.StreamHandler(stream=sys.stderr)
_log_console_handler.setFormatter(_formatter)
_log_file_handler = logging.FileHandler(ERROR_LOG_FILE, mode='w')
_log_file_handler.setFormatter(_formatter)

LOG = logging.getLogger(sys.argv[0])
LOG.setLevel(logging.ERROR)
LOG.addHandler(_log_console_handler)
LOG.addHandler(_log_file_handler)

_cmd_handler = logging.FileHandler(CMD_LOG_FILE, mode='w')
_cmd_handler.setFormatter(logging.Formatter('%(message)s'))

CMD_LOG = logging.getLogger('partition_command_log')
CMD_LOG.setLevel(logging.INFO)
CMD_LOG.addHandler(_cmd_handler)


class RunStatistics:

    def __init__(self, total_files):
        self.total_files = total_files
        self.partitioned_by={}
        self.partition_counts={}
        self.type_counts={}
        self.success=0
        self.failure=0
        
    def count_success(self, num_items=1):
        self.success += num_items

    def count_failure(self, num_items=1):
        self.failure += num_items

    @staticmethod
    def _map_count(map_obj, k, num_items=1):
        if k in map_obj:
            map_obj[k] += num_items
        else:
            map_obj[k] = num_items

    def count_type(self, file_type, num_items=1):
        RunStatistics._map_count(self.type_counts, file_type.upper(), num_items)
            
    def count_partition_method(self, partition_method, num_items=1):
        RunStatistics._map_count(self.partitioned_by, partition_method, num_items)

    def count_partition(self, partition_id, num_items=1):
        RunStatistics._map_count(self.partition_counts, partition_id, num_items)        
        
    def print_summary(self, stream=sys.stdout):
        sprint = lambda x='': print(x, file=stream) 
        sprint('Summary statistics for run %s' % _start_time)
        sprint('  Total files: %d' % self.total_files)
        sprint('  Successful files: %d' % self.success)
        sprint('  Failed files: %d' % self.failure)
        if self.success > 0:
            sprint('  Count by partition method:')
            for k in self.partitioned_by:
                sprint('    %s: %d' % (k, self.partitioned_by[k]))
            sprint('  Count by partition:')
            for k in self.partition_counts:
                sprint('    %s: %d' % (k, self.partition_counts[k]))
            sprint('  Count by file type:')
            for k in self.type_counts:
                sprint('    %s: %d' % (k, self.type_counts[k]))
        sprint()    
        sprint('  File system command logs in %s' % CMD_LOG_FILE)
        sprint('  Error logs in %s' % CMD_LOG_FILE)    
        sprint()
        
def _read_exif_hachoir(file_name):
    try:

        filename, realname = unicodeFilename(file_name), file_name
        parser = createParser(filename, realname)
        metadata = extractMetadata(parser)
        
        if metadata and metadata.has('creation_date'):
            exif = {}
            exif['creation_date'] = str(metadata.get('creation_date'))
            return exif
        else:
            LOG.warn('File %s did not have creation_date' % file_name)

        return {}

    except HachoirError, err:
        LOG.exception("Metadata extraction error: %s", unicode(err))
        

EXIF_YEAR_PTRN = re.compile('^\d+[:\-\/]\d+[:\-\/]\d+.*$')
# Note: this pattern will only work for years from 1000CE to 2999CE
PATH_YEAR_PTRN = re.compile('^.*\%s([12]\d\d\d)\%s.*$' % (os.sep, os.sep))
        
def _parse_exif_year(date_str):
    x = date_str.strip()
    if EXIF_YEAR_PTRN.match(x):
        return int(re.split('[:\-\/]', x)[0])
    return None

def _parse_filename_year(file_name):
    m = PATH_YEAR_PTRN.match(file_name)
    if m:
        return int(m.group(1))
    return None


class Partition:

    partitions = {}
    created_dirs = set()
    
    def __init__(self, partition_id, src_dir, dest_dir, dry_run, flatten):
        self.partition_id = partition_id
        self.src_dir = src_dir
        self.dest_dir = dest_dir
        self.dest_bloom = BloomFilter(max_elements=EST_MAX_FILES_PER_YEAR)
        self.dry_run = dry_run
        self.flatten = flatten

    def _dest_path(self, file_name):    
        """
        Given a source path, determine a safe final destination path, disallowing any overwrites
        within a single job run.
        """
        if self.flatten:
            base = os.path.basename(file_name)
            (x, y) = os.path.splitext(base)
            # linear probing until we find an unused destination name
            tmp_dest = base
            i=0
            while tmp_dest in self.dest_bloom:
                i += 1
                tmp_dest = ''.join([x, '-%d' % i, y])

            self.dest_bloom.add(tmp_dest)
            return os.path.join(self.dest_dir, str(self.partition_id), tmp_dest)
            
        else:
            common_prefix = os.path.commonprefix([self.src_dir, file_name])
            path_suffix = file_name[len(common_prefix) + 1:]
            return os.path.join(self.dest_dir, str(self.partition_id), path_suffix)
            
    def _ingest(self, file_name):

        dest_file_name = self._dest_path(file_name)
        
        if not self.dry_run:
            dest_dir = os.path.dirname(dest_file_name)
            
            if not dest_dir in Partition.created_dirs:
                Partition.created_dirs.add(dest_dir)
                if not os.path.isdir(dest_dir):
                    os.makedirs(dest_dir)
                
            shutil.copy2(file_name, dest_file_name)
            
        CMD_LOG.info('Partition %s\tcp %s %s' % (self.partition_id, file_name, dest_file_name))

        
    @staticmethod
    def _get_partition(file_name, run_stats):
        exif = _read_exif_hachoir(file_name)
        if 'creation_date' in exif:
            p = _parse_exif_year(exif['creation_date'])
            if p:
                run_stats.count_partition_method('exif')
                return p

        path_year = _parse_filename_year(file_name)
        if path_year:
            run_stats.count_partition_method('path')
            return path_year

        run_stats.count_partition_method('unknown')
        return UNKNOWN_PARTITION
    
    @staticmethod
    def handle_file(file_name, src_dir, dest_dir, dry_run, flatten, run_stats):

        part = Partition._get_partition(file_name, run_stats)
        
        # if first time, do partition set-up
        if part not in Partition.partitions:
            Partition.partitions[part] = Partition(part, src_dir, dest_dir, dry_run, flatten)

        Partition.partitions[part]._ingest(file_name)

        base, ext = os.path.splitext(file_name)
        run_stats.count_type(ext)
        run_stats.count_partition(part)

def _file_size_cmp(path, min_kb):
    sz = os.stat(path).st_size
    sz_kb = sz / 1000
    return sz_kb - min_kb
        
def _generate_src_paths(root_dir, included_extensions, min_kb):
    extensions = [x.strip().lower() for x in included_extensions.split(',')] \
                 + [x.strip().upper() for x in included_extensions.split(',')]
    paths = []
    for root, dirnames, filenames in os.walk(os.path.abspath(root_dir)):
        for x in extensions:
            glob = '*.%s' % x
            for filename in fnmatch.filter(filenames, glob):
                candidate_path = os.path.join(root, filename)
                if _file_size_cmp(candidate_path, min_kb) > -1:
                    yield candidate_path
                else:
                    LOG.debug('Skipping file %s; size < %d kb' % (candidate_path, min_kb))

                    
def _is_subdir(lpath, rpath):
    l_real = os.path.realpath(lpath)
    r_real = os.path.realpath(rpath)
    return l_real == os.path.commonprefix([l_real, r_real])


def _validate_src_and_dest(src_path, dest_path, allow_overwrite):
    valid = True
    if not os.path.isdir(src_path) or not os.path.isdir(dest_path):
        valid = False
        print('Both SRC_DIR and DEST_DIR must be valid directories')
    elif _is_subdir(src_path, dest_path):
        valid = False
        print('DEST_DIR cannot be a subdirectory of SRC_DIR')
    elif not allow_overwrite and len(os.listdir(dest_path)) > 0:    
        valid = False
        print('DEST_DIR must be empty, unless you have specified --overwrite')
        
    if not valid:
        sys.exit(1)

                
def _get_args():
    parser = argparse.ArgumentParser(description='''
    Partition a media library into directories by year. Primarily designed with image / video libraries in mind.
    This program will look through SRC_DIR for media files, and copy them into a subdirectory of DEST_DIR, partitioned by year.  If the DEST_DIR/${YEAR} subdirectory does not yet exist, it will create the directory.  The program first tries to read the EXIF metadata of the files, then if it cannot get a year from that, falls back on looking at the directory path to find a year.  If all else fails, it assigns the file to year 0.
    ''')
    parser.add_argument('src_dir', metavar='SRC_DIR', type=str, help='Root directory of library')
    parser.add_argument('dest_dir', metavar='DEST_DIR', type=str, help='Destination directory of partitioned libraries')
    parser.add_argument('--min-kb', type=int, default=DEFAULT_MIN_SIZE_KB, help='Minimum size of image to include in new library.  For example, can be used to eliminate thumbnails. Default value: %d' % DEFAULT_MIN_SIZE_KB)
    parser.add_argument('--file-extensions', type=str, default=DEFAULT_FILE_EXTENSIONS, help='File extensions to include in library.  CSV list; case-insensitive. Default value: %s' % DEFAULT_FILE_EXTENSIONS)
    parser.add_argument('--flatten-subdirectories', action='store_true', help='Flatten subdirectories by placing all files in a single directory per year.  Note: files from SRC_DIR which have duplicate filenames when the directories are flattened will always be given a unique filename.  Default value: False')
    parser.add_argument('--overwrite', action='store_true', help='Overwrite files that exist in DEST_DIR before the program runs.  Default value: False')
    parser.add_argument('--no-dry-run', action='store_true', help='By default, we log expected changes, but do not actually make the changes.  If --no-dry-run is specified, changes will actually be executed.')
    parser.add_argument('--num-workers', type=int, default=DEFAULT_PARALLEL_WORKERS, help='Number of parallel threads to run.  Default value: %d' % DEFAULT_PARALLEL_WORKERS)
    
    args = parser.parse_args()
    
    _validate_src_and_dest(args.src_dir, args.dest_dir, args.overwrite)
    
    return args


def _parallel_task(work_queue, progress, args, run_stats):

    while True:
        try:
            src_file = work_queue.get(True, QUEUE_TIMEOUT_SEC)
            Partition.handle_file(src_file, args.src_dir, args.dest_dir, \
                                  not args.no_dry_run, args.flatten_subdirectories, run_stats)

            run_stats.count_success()
        except Queue.Empty:
            LOG.error("No more files to process. Exiting.")
        except:
            LOG.exception("Unexpected error processing file %s: %s", src_file, sys.exc_info()[0])
            run_stats.count_failure()
        finally:
            work_queue.task_done()
            
        try:
            #TODO: I think this may break with Unicode filenames
            progress.set_postfix(file=unicodeFilename(os.path.basename(src_file)), refresh=False)
            progress.update(1)
        except:
            LOG.exception("Error updating progress bar: %s", sys.exc_info()[0])
            
def main_func():

    args = _get_args()

    # walk the list once to count for our progress bar total   
    paths = _generate_src_paths(args.src_dir, args.file_extensions, args.min_kb)
    total_files = 0
    for f in paths:
        total_files += 1

    progress_bar = tqdm(total=total_files, unit='Files', unit_scale=True)    

    run_stats = RunStatistics(total_files)
    
    work_queue = Queue.Queue(WORK_BUFFER_SIZE)
    for i in range(args.num_workers):
        t = Thread(target=lambda: _parallel_task(work_queue, progress_bar, args, run_stats))
        t.daemon = True
        t.start()
        
    # this generator will feed the actual work    
    paths = _generate_src_paths(args.src_dir, args.file_extensions, args.min_kb)     
    for p in paths:
        work_queue.put(p)

    work_queue.join()

    progress_bar.clear()
    run_stats.print_summary()
    
            
if __name__ == '__main__':

    main_func()
