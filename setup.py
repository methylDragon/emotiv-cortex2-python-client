from setuptools import setup, find_packages
with open('PyPI/README.md') as readme_file:
    README = readme_file.read()
with open('PyPI/HISTORY.md') as history_file:
    HISTORY = history_file.read()

setup_args = {'name': "cortex2",
              'version': "1.0.0.post2",
              'description': "Comprehensive threaded, asynchronous Python client for the Emotiv EEG Cortex 2 API",
              'long_description_content_type': "text/markdown",
              'long_description': README + '\n\n' + HISTORY,
              'license': "MIT",
              'packages': find_packages(),
              'author': "methylDragon",
              'author_email': "methylDragon@gmail.com",
              'keywords': ['emotiv', 'eeg', 'client', 'websockets', 'api', 'bci', 'brain'],
              'url': "https://github.com/methylDragon/emotiv-cortex2-python-client",
              'download_url': "https://pypi.org/project/cortex2/"}

install_requires = ['websockets>=7.0',
                    ]

if __name__ == '__main__':
    setup(**setup_args, install_requires=install_requires)
