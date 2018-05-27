import argparse
from PIL import Image
from PIL.ExifTags import TAGS


def get_exif(file_name):
    i = Image.open(file_name)
    if 'exif' in i.info:

        exif = {}
        for tag, value in i._getexif().items():
            d = TAGS.get(tag, tag)
            exif[d] = str(value)
        
        return exif
    else:
        return {}

def get_args():
    parser = argparse.ArgumentParser(description='Show EXIF tags from image file')
    parser.add_argument('files', metavar='FILE', type=str, nargs='+', help='Filename(s)')
    
    return parser.parse_args()



if __name__ == '__main__':

    args = get_args()

    for f in args.files:
        ex = get_exif(f)
        print(f)
        print(ex)
        
