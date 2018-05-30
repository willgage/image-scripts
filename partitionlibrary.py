# See multi-threading examples in https://stackoverflow.com/questions/16665367/why-doesnt-a-simple-python-producer-consumer-multi-threading-program-speed-up-b

# See https://pypi.org/project/bloom-filter/
# TODO: support video files

import argparse
import fnmatch
import os
import os.path
import stat
import sys
import Queue
import logging
import re

from threading import Thread

from PIL import Image
from PIL.ExifTags import TAGS
from bloom_filter import BloomFilter
from tqdm import tqdm

UNKNOWN_PARTITION=0
DEFAULT_MIN_SIZE_KB=1000
DEFAULT_FILE_EXTENSIONS='JPEG,JPG'
DEFAULT_PARALLEL_WORKERS=10
WORK_BUFFER_SIZE=10000
EST_MAX_FILES_PER_YEAR=50000 

#TODO: set-up regular error logging as well to console


# Todo handle exif from video files
def read_exif(file_name):
    i = Image.open(file_name)
    try:
        if 'exif' in i.info:
            exif = {}
            for tag, value in i._getexif().items():
                d = TAGS.get(tag, tag)
                exif[d] = str(value)

            return exif
        else:
            return {}
    finally:
        i.close()


EXIF_YEAR_PTRN = re.compile('^\d+:\d+:\d+.*$')
# Note: this pattern will only work for the previous and current millenium
PATH_YEAR_PTRN = re.compile('^.*\%s([12]\d\d\d)\%s.*$' % (os.sep, os.sep))
        
def parse_exif_year(date_str):
    x = date_str.strip()
    if EXIF_YEAR_PTRN.match(x):
        return int(x.split(':')[0])
    return None

def parse_filename_year(file_name):
    m = PATH_YEAR_PTRN.match(file_name)
    if m:
        return int(m.group(1))
    return None


class Partition:

    partitions = {}
    
    def __init__(self, partition_id, src_dir, dest_dir, log_file, use_move, dry_run, flatten):
        self.partition_id = partition_id
        self.log_file = log_file
        self.src_dir = src_dir
        self.dest_dir = dest_dir
        self.dest_bloom = BloomFilter(max_elements=EST_MAX_FILES_PER_YEAR)
        self.use_move = use_move
        self.dry_run = dry_run
        self.flatten = flatten
        self.dir_created = False


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
            
    def ingest(self, file_name):
        if not self.dir_created and not self.dry_run:
            os.mkdir(os.path.join(self.dest_dir, str(self.year)))
            self.dir_created = True

        dest_file_name = self._dest_path(file_name)
            
        CMD_LOG.info('Partition %s, cp %s %s' % (self.partition_id, file_name, dest_file_name))

        
    @staticmethod
    def get_partition(file_name):
        exif = read_exif(file_name)
        for x in ['DateTimeOriginal','DateTimeDigitized', 'DateTime']:
            if x in exif:
                p = parse_exif_year(exif[x])
                if p:
                    return p

        path_year = parse_filename_year(file_name)
        if path_year:
            return path_year
                
        return UNKNOWN_PARTITION
    
    @staticmethod
    def handle_file(file_name, src_dir, dest_dir, log_file, use_move, dry_run, flatten):

        part = Partition.get_partition(file_name)

        # if first time, do partition set-up
        if part not in Partition.partitions:
            Partition.partitions[part] = Partition(part, src_dir, dest_dir, log_file, use_move, dry_run, flatten)

        Partition.partitions[part].ingest(file_name)


def file_size_cmp(path, min_kb):
    sz = os.stat(path).st_size
    sz_kb = sz / 1000
    return sz_kb - min_kb
        
def generate_src_paths(root_dir, included_extensions, min_kb):
    extensions = [x.strip().lower() for x in included_extensions.split(',')] \
                 + [x.strip().upper() for x in included_extensions.split(',')]
    paths = []
    for root, dirnames, filenames in os.walk(os.path.abspath(root_dir)):
        for x in extensions:
            glob = '*.%s' % x
            for filename in fnmatch.filter(filenames, glob):
                candidate_path = os.path.join(root, filename)
                if file_size_cmp(candidate_path, min_kb) > -1:
                    yield candidate_path

                    
def is_subdir(lpath, rpath):
    l_real = os.path.realpath(lpath)
    r_real = os.path.realpath(rpath)
    return l_real == os.path.commonprefix([l_real, r_real])


def validate_src_and_dest(src_path, dest_path, allow_overwrite):
    valid = True
    if not os.path.isdir(src_path) or not os.path.isdir(dest_path):
        valid = False
        print('Both SRC_DIR and DEST_DIR must be valid directories')
    elif is_subdir(src_path, dest_path):
        valid = False
        print('DEST_DIR cannot be a subdirectory of SRC_DIR')
    elif not allow_overwrite and len(os.listdir(dest_path)) > 0:    
        valid = False
        print('DEST_DIR must be empty, unless you have specified --overwrite')
        
    if not valid:
        sys.exit(1)

                
def get_args():
    parser = argparse.ArgumentParser(description='''
    Partition an image library into directories by year.
    This program will look through SRC_DIR for image files, and copy (or move) them into a subdirectory of DEST_DIR, partitioned by year.  If the DEST_DIR/${YEAR} subdirectory does not yet exist, it will create the directory. 
    ''')
    parser.add_argument('src_dir', metavar='SRC_DIR', type=str, help='Root directory of library')
    parser.add_argument('dest_dir', metavar='DEST_DIR', type=str, help='Destination directory of partitioned libraries')
    parser.add_argument('--min-kb', type=int, default=DEFAULT_MIN_SIZE_KB, help='Minimum size of image to include in new library.  For example, can be used to eliminate thumbnails. Default value: %d' % DEFAULT_MIN_SIZE_KB)
    parser.add_argument('--file-extensions', type=str, default=DEFAULT_FILE_EXTENSIONS, help='File extensions to include in library.  Default value: %s' % DEFAULT_FILE_EXTENSIONS)
    parser.add_argument('--use-move', action='store_true', help='Move files instead of copying them.  This is less safe, but sometimes warranted if you have space constraints.  Default value: False')
    parser.add_argument('--flatten-subdirectories', action='store_true', help='Flatten subdirectories by placing all files in a single directory per year.  Note: files from SRC_DIR which have duplicate filenames when the directories are flattened will always be given a unique filename.  Default value: False')
    parser.add_argument('--overwrite', action='store_true', help='Overwrite files that exist in DEST_DIR before the program runs.  Default value: False')
    parser.add_argument('--no-dry-run', action='store_true', help='By defalt, we log expected changes, but do not actually make the changes.  If --no-dry-run is specified, changes will actually be executed.')
    parser.add_argument('--num-workers', type=int, default=DEFAULT_PARALLEL_WORKERS, help='Number of parallel threads to run.  Default value: %d' % DEFAULT_PARALLEL_WORKERS)
    
    args = parser.parse_args()

    validate_src_and_dest(args.src_dir, args.dest_dir, args.overwrite)
    
    return args


def parallel_task():

    while True:
        src_file = work_queue.get()
        try:
            Partition.handle_file(src_file, args.src_dir, args.dest_dir, 'some_log_file_thing', args.use_move, \
                             not args.no_dry_run, args.flatten_subdirectories)
        finally:
            work_queue.task_done()
            progress_bar.set_postfix(file=os.path.basename(src_file), refresh=False)
            progress_bar.update(1)

if __name__ == '__main__':

    args = get_args()

    CMD_HANDLER = logging.FileHandler('partition.log', mode='w')
    CMD_HANDLER.setFormatter(logging.Formatter('%(message)s'))
    CMD_LOG = logging.getLogger('partition_command_log')
    CMD_LOG.setLevel(logging.INFO)
    CMD_LOG.addHandler(CMD_HANDLER)
    
    work_queue = Queue.Queue(WORK_BUFFER_SIZE)
    for i in range(args.num_workers):
        t = Thread(target=parallel_task)
        t.daemon = True
        t.start()

    # walk the list once to count for our progress bar total   
    paths = generate_src_paths(args.src_dir, args.file_extensions, args.min_kb)
    total_files = 0
    for f in paths:
        total_files += 1

    progress_bar = tqdm(total=total_files, unit='Files', unit_scale=True)
        
    # this generator will feed the actual work    
    paths = generate_src_paths(args.src_dir, args.file_extensions, args.min_kb)    
    
    for p in paths:
        work_queue.put(p)

    work_queue.join()   
