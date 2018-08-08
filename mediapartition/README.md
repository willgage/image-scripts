# Mediapartition
mediapartition is a simple Python-based command line utility for partitioning libraries of media files by year of creation. You can think of it as a glorified 'cp' command with some intelligence built in.  In other words, it copies files from a source directory to a target directory, while also scanning the files for hints about the year in which they were authored.  The target directory will be divided into subdirectories based on the year.

## Why write this (or use it)?
I was struggling with how to manage my family's 400+ GB photo collection, which spanned over a decade and had grown quite unwieldy to manage in a single (Mac) Photos library.  The natural solution seemed to be to partition it into libraries by year.  I came across [PowerPhotos](https://www.fatcatsoftware.com/powerphotos/), which is a nice utility for managing multiple Photos libraries.  The product itself has a [recommended workflow](https://www.fatcatsoftware.com/powerphotos/Docs/split_library.html) for using Photos built in "Smart Albums" functionality to split a library by year. I tried this workflow out to partition a single year out of the monolithic library, but I wasn't happy with the Smart Albums feature.  It was slow, it seemed to be splitting by the year we imported into Photos rather than the year of authorship, and it just didn't seem workable for such a big library.

So, I wrote mediapartition to do the work of splitting things by year in one shot, after which I could create new Photos libraries using PowerPhotos and import the appropriate directory's files into each library.  To me, this was a much better solution.  Once written, mediapartition did the partitioning of my monolithic library in about 1.5 hrs.  Library creation and import are an additional step (and time investment), but this utility helps to check-point the workflow between partitioning and import and break it down into manageable pieces.

## Installation
* Requires Python 2.7 and setuptools
* `python setup.py install`

## Usage

See `mediapart -h` for an explanation of runtime options.
<pre>
usage: mediapart [-h] [--min-kb MIN_KB] [--file-extensions FILE_EXTENSIONS]
                 [--flatten-subdirectories] [--overwrite] [--no-dry-run]
                 [--num-workers NUM_WORKERS]
                 SRC_DIR DEST_DIR

Partition a media library into directories by year. Primarily designed with
image / video libraries in mind. This program will look through SRC_DIR for
media files, and copy them into a subdirectory of DEST_DIR, partitioned by
year. If the DEST_DIR/${YEAR} subdirectory does not yet exist, it will create
the directory. The program first tries to read the EXIF metadata of the files,
then if it cannot get a year from that, falls back on looking at the directory
path to find a year. If all else fails, it assigns the file to year 0.

positional arguments:
  SRC_DIR               Root directory of library
  DEST_DIR              Destination directory of partitioned libraries

optional arguments:
  -h, --help            show this help message and exit
  --min-kb MIN_KB       Minimum size of image to include in new library. For
                        example, can be used to eliminate thumbnails. Default
                        value: 1
  --file-extensions FILE_EXTENSIONS
                        File extensions to include in library. CSV list; case-
                        insensitive. Default value: BMP,CUR,EMF,ICO,GIF,JPG,JP
                        EG,PCX,PNG,TGA,TIFF,TIF,WMF,XCF,MKV,WMV,MOV,AVI,M4V,CR
                        2,MP4,3GP,MPG
  --flatten-subdirectories
                        Flatten subdirectories by placing all files in a
                        single directory per year. Note: files from SRC_DIR
                        which have duplicate filenames when the directories
                        are flattened will always be given a unique filename.
                        Default value: False
  --overwrite           Overwrite files that exist in DEST_DIR before the
                        program runs. Default value: False
  --no-dry-run          By default, we log expected changes, but do not
                        actually make the changes. If --no-dry-run is
                        specified, changes will actually be executed.
  --num-workers NUM_WORKERS
                        Number of parallel threads to run. Default value: 10
</pre>
One thing to bear in mind is that because the tool only supports copying files around rather than moving them, you will temporarily need 2x the storage capacity to hold the files as you partition whatever batch of files you're working with.
Supporting only copy was a design decision to prevent accidental data loss.

