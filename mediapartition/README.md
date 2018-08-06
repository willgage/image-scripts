# Mediapartition
mediapartition is a simple Python-based command utility for partitioning libraries of media files by year of creation. You can think of it as a glorified 'cp' command with some intelligence built in.  In other words, it copies files from a source directory to a target directory, while also scanning the files for hints about the year in which they were authored.  The target directory will be divided into subdirectories based on the year.

## Why write this (or use it)?
I was struggling with how to manage my family's 400+ GB photo collection, which spanned over a decade and had grown quite unwieldy to manage in a single (Mac) Photos library.  The natural solution seemed to be to partition it into libraries by year.  I came across [PowerPhotos](https://www.fatcatsoftware.com/powerphotos/), which is a nice utility for managing multiple Photos libraries.  The product itself has a [recommended workflow](https://www.fatcatsoftware.com/powerphotos/Docs/split_library.html) for using Photos' built in "Smart Albums" functionality to split a library by year. I tried this workflow out for a single year, but I wasn't happy with the Smart Albums feature.  It was slow, it seemed to be splitting by the year we imported into Photos rather than the year of authorship, and it just didn't seem workable for such a big library.  So, I wrote mediapartition to do the work of splitting things by year in one shot, after which I could create new Photos libraries using PowerPhotos and import the appropriate directory's files into each library.  To me, this was a much better solution.  Once written, mediapartition did the partitioning of my monolithic library in about 1 hr.  Library creation and import are an additional time-sink, but at least I had check-pointed the workflow between partitioning and import and had it broken it down into manageable pieces.

## Installation
* Requires Python 2.7 and setuptools
* `python setup.py install`

## Using mediapartition

See `mediapart -h` for an explanation of runtime options.

