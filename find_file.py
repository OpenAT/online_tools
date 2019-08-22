#!/usr/bin/env python

import os
try:
    import scandir
except:
    print "python lib scandir could not be imported"

import time
import inspect

# Alias
pj = os.path.join


def find_file(file_name, start_dir='/', max_finds=0, exclude_folders=tuple(), walk_method=None):
    start = time.time()
    exclude_folders = list(set(exclude_folders))

    # Process Info
    print "find_file: START: Search for file %s in startfolder and below %s" % (file_name, start_dir)
    if max_finds > 0:
        print "find_file: Stop the search if the file was found %s times!" % max_finds
    if exclude_folders:
        print "find_file: Exclude contents in folders %s from the search!" % str(exclude_folders)

    # Select walk method
    if not walk_method:
        try:
            walk_method = scandir.walk
        except:
            walk_method = os.walk

    res = []
    for root_folder, sub_folders, files in walk_method(start_dir, topdown=True):

        # Exclude unwanted folders
        # HINT: Modifying sub_folders in-place will prune the (subsequent) files and directories visited by os.walk
        if exclude_folders:
            len_start = len(sub_folders)
            sub_folders[:] = [d for d in sub_folders if d not in exclude_folders]
            if len_start != len(sub_folders):
                print "Subfolder removed!"

        # Search for the file
        if file_name in files:
            res.append(pj(root_folder, file_name))

        # Stop if file was found max_finds times
        if 0 < max_finds <= len(res):
            print "find_file: File found %s times! Stopping the search!" % len(res)
            break

    print "find_file: File search finished in %s seconds with method '%s'" % (time.time() - start, walk_method.__name__)
    print "find_file: File '%s' was found %s times!" % (file_name, len(res))
    print "find_file: RESULT: %s" % res
    return res


# Start comparison
if __name__ == "__main__":
    file_name = 'backup_tester.py'
    start_dir = '/Users/michaelkarrer/pycharm_projects'
    exclude_folders = ['work-in-progress']
    #exclude_folders = []
    max_finds = 1
    find_file(file_name, start_dir=start_dir, max_finds=max_finds,
              walk_method=os.walk, exclude_folders=exclude_folders)
    find_file(file_name, start_dir=start_dir, max_finds=max_finds,
              walk_method=scandir.walk, exclude_folders=exclude_folders)
