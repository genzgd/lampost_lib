from setuptools import setup, find_packages

setup(
    use_scm_version=True,
    setup_requires=['setuptools_scm'],
    name='lampost_lib',
    description='Multiuser environment web app framework ',
    long_description='Please see README.md for the full description',

    url='https://github.com/genzgd/lampost_lib',

    author='Geoffrey D. Genz',
    author_email='genzgd@gmail.com',

    license='MIT',

    classifiers=[
        'Development Status :: 3 - Alpha',

        'Intended Audience :: Developers',

        'Topic :: Software Development :: Libraries :: Application Frameworks',

        'License :: OSI Approved :: MIT License',

        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],

    keywords='mud database',
    packages=find_packages(),
)
