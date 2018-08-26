# Copyright (c) 2018 William Gage
# This code is licensed under the terms of the MIT License
# See LICENSE file for more details

from setuptools import setup

setup(
    name="mediapartition",
    version="0.1a0",
    scripts=['mediapartition.py'],
    entry_points={
        'console_scripts': [
            'mediapart=mediapartition:main_func'
        ]
    },
    install_requires=['bloom-filter==1.3', 'tqdm==4.23.4', 'hachoir-core==1.3.3', 'hachoir-metadata==1.3.3', 'hachoir-parser==1.3.4']
)
