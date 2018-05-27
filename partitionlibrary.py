import argparse
import fnmatch
import os
import os.path
import stat
import sys

from PIL import Image
from PIL.ExifTags import TAGS

DEFAULT_MIN_SIZE_KB=1000
DEFAULT_FILE_EXTENSIONS='JPEG,JPG'


def open_exif(file_name):
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

def file_size_cmp(path, min_kb):
    sz = os.stat(path).st_size
    sz_kb = sz / 1000
    return sz_kb - min_kb

        
def gather_paths(root_dir, included_extensions, min_kb):
    
    extensions = [x.strip().lower() for x in included_extensions.split(',')] + [x.strip().upper() for x in included_extensions.split(',')]

    paths = []
    for root, dirnames, filenames in os.walk(os.path.abspath(root_dir)):
        for x in extensions:
            glob = '*.%s' % x
            for filename in fnmatch.filter(filenames, glob):
                paths.append(os.path.join(root, filename))

    filtered_paths = filter(lambda x: file_size_cmp(x, min_kb) > -1, paths)
                
    return filtered_paths

                
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
    parser.add_argument('--dry-run', action='store_true', help='Log expected changes, but do not actually make the changes.  Default value: False')            
    args = parser.parse_args()

    if args.src_dir == args.dest_dir:
        print('SRC_DIR and DEST_DIR cannot be the same')
        sys.exit(1) 
    
    return args
    

if __name__ == '__main__':
    args = get_args()
    paths = gather_paths(args.src_dir, args.file_extensions, args.min_kb)


    # overwrite: check if dest_dir is empty.  if so, all filenames are un-munged other than what is necessary to flatten
    # directories
    # if not empty, then file names are decorated with a unique run id
    print(args)
    
    print paths

