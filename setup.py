from distutils.core import setup

setup(
    name='MusicUtils',
    version='0.1',
    packages=['MusicUtils'],
    url='',
    license='MIT',
    author='kolding',
    author_email='kolding@washington.edu',
    description='',
    entry_points =
        {
            "console_scripts": [
                "tagit     = MusicUtils.tagit:main",
                "tagedit   = MusicUtils.tagedit:main",
                "reorg     = MusicUtils.reorg:main",
                "copyTags  = MusicUtils.copyTags:main",
                "aconvert  = MusicUtils.aconvert:main",
                "checkConsistency= MusicUtils.checkConsistency:main",
            ],
        },
)