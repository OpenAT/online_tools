# -*- coding: utf-'8' "-*-"

from shell_tools import shell
import os
import logging

log = logging.getLogger()


def submodule_sha1(path, submodule=str()):
    log.info("Get SHA1 of submodule %s at %s" % (submodule, path))
    # HINT: Full submodule path needed!
    #       e.g.: 'fundraising_studio/online' for 'dadi/fundraising_studio/online'
    #       This allows that submodules of submodules will not get found if they have the same name!

    # Use git to get the list of submodules and their current commits SHA1
    submodules = shell(['git', 'submodule', 'status', '--recursive'], cwd=path)
    assert submodules, 'No submodules found in %s! Did you run "git submodule init"?' % path

    # Create a dict out of the git output
    # e.g.: {'fundraising_studio/online': '-88b145319056b9d6feac9c86458371cd12a3960c'}
    # Example git-output line: "-88b145319056b9d6feac9c86458371cd12a3960c fundraising_studio/online "
    # HINT: [-40:] means use first 40 characters from right to left in the string (= removing the - if it exists)
    submodules = {line.split()[1].strip(): line.split()[0].strip()[-40:] for line in submodules.splitlines()}

    # Get SHA1 for submodule and check that it is 40 characters long!
    sha1 = submodules[submodule]
    assert len(sha1) == 40, 'Wrong or missing SHA1 (%s) for submodule %s in %s!' % (sha1, submodule, path)
    return sha1


def get_tag(path, match='o8r*'):
    log.info("Get 'tag' from github repository at %s" % path)
    assert os.path.isdir(path), "Repository path not found at %s" % path

    # HINT: -C and cwd=path are redundant (one would be enough) but kept here for reference
    tag = shell(['git', '-C', path, 'describe', '--tags', '--exact-match', '--match='+match], cwd=path)

    return tag

