import h5py
import numpy as np

# Feb 2024 simple hdf5 file parser by Andi
# last change 15/4/2024 by Andi

def read_group(group, path='', level=0, index=0, siblings=1):
    # print group data and attribute
    # on top level call with group = file handle
    full_path = '/' if path == '' else path
    if len(group.attrs) > 0:
        attrs = {a: v for a, v in group.attrs.items()}
        print("%i (%i/%i) group '%s': %i entries, %i attrs:\n" % (level, index+1, siblings, full_path, len(group), len(attrs)), attrs)
    else:
        print("%i (%i/%i) group '%s': %i entries, 0 attrs" % (level, index+1, siblings, full_path, len(group)))
    level += 1
    siblings = len(group)
    for index,name in enumerate(group):
        #print("    '%s'" % (name))
        data = group[name]
        attrs = {a: v for a, v in data.attrs.items()}
        full_name = name if path == '' else path + '/' + name
        if isinstance(data, h5py._hl.group.Group):
            read_group(data, full_name, level, index, siblings)
        elif isinstance(data, h5py._hl.dataset.Dataset):
            data = data[()]
            if isinstance (data, np.ndarray): shape = 'shape=%s'%(str(data.shape))
            else:                             shape = 'len=%i'%(len(data))
            if len(attrs) == 0:
                print("%i (%i/%i) dataset '%s': %s, type=%s" % (level, index+1, siblings, full_name, shape, str(type(data))))
            else:
                print("%i (%i/%i) dataset '%s': %s, type=%s, %i attrs:\n" % (level, index+1, siblings, full_name, shape, str(type(data)), len(attrs)), attrs)

def read_file(h5file):
    # read hdf5 file groups and attributes
    with h5py.File(h5file, 'r') as f:
        read_group(f)

            
