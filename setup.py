from setuptools import setup, find_packages

setup(
    name="media-partition",
    version="0.1a0",
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'mediapart = media-partition:main_func'
        ]
    },

    # Project uses reStructuredText, so ensure that the docutils get
    # installed or upgraded on the target machine
    install_requires=['bloom-filter==1.3', 'tqdm==4.23.4', 'hachoir-core==1.3.3', 'hachoir-metadata==1.3.3', 'hachoir-parser==1.3.4']
)
