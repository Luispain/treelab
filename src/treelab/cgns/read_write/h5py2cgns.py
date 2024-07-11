#    Copyright 2023 ONERA - contact luis.bernardos@onera.fr
#
#    This file is part of MOLA.
#
#    MOLA is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    MOLA is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public License
#    along with MOLA.  If not, see <http://www.gnu.org/licenses/>.

'''
Low-level module for wrapping HDF5 file operations and inferring the CGNS
list-like structure. It is used as a backend of MOLA.Data structure.

Requires installation of python libraries "h5py" and "numpy"

File history:
24/11/2022 - Luis Bernardos - creation
'''

import numpy as np
import h5py


use_chunks = True
encoding = 'utf-8'
nodesNamesToRead = ['proc', 'kind']

str_dtype = h5py.string_dtype(encoding, 33)
cgns_dtype = h5py.string_dtype(encoding, 3)

h5py.get_config().track_order = True

# https://cgns.github.io/cgns-modern.github.io/standard/hdf5.html#the-data-type
Numpy_dtype_to_CGNS_dtype = {
    np.dtype('int32'):'I4',
    np.dtype('int64'):'I8',
    np.dtype('uint32'):'U4',
    np.dtype('float32'):'R4',
    np.dtype('float64'):'R8',
    np.dtype('S1'):'C1',
    }

def load(filename, only_skeleton=False):
    f = load_h5(filename)
    children = []
    l = []

    for childname in f['/'].keys():
        childnode = build_cgns_nodelist( f[childname], links=l,
                                         ignore_DataArray=only_skeleton)
        if not childnode: continue
        children += [ childnode ]

    t = ['CGNSTree', None, children, 'CGNSTree_t']

    return t, f, l

def load_from_path(filename, path):
    f = load_h5(filename)
    childnode = build_cgns_nodelist( f[path] )
    return childnode

def load_h5(filename, permission='r'):
    f = h5py.File(filename, permission, track_order=True)
    return f

def save(t, filename, links=[]):
    with h5py.File(filename, 'w', track_order=True) as f:
        f['/'].attrs.create('name', np.array('HDF5 MotherNode'.encode(encoding), dtype=str_dtype) )
        f['/'].attrs.create('label', np.array('Root Node of HDF5 File'.encode(encoding), dtype=str_dtype) )
        f['/'].attrs.create('type', np.array('MT'.encode(encoding), dtype=cgns_dtype) )

        data = np.frombuffer('IEEE_LITTLE_32'.encode(encoding), dtype='int8'.encode(encoding))
        f.create_dataset(' format', data=data)

        data = np.frombuffer('HDF5 Version 1.8.17'.encode(encoding), dtype='int8'.encode(encoding))
        data = np.concatenate((data,np.zeros(33-len(data), dtype='int8'.encode(encoding))))
        f.create_dataset(' hdf5version', data=data)

        for child in t[2]: nodelist_to_group(f, child)

        for l in links: write_link(f, l)



def nodelist_to_group(f, node, nodepath=None, links=[] ):
    if nodepath is not None:
        group = f.create_group( nodepath.encode(encoding), track_order=True )
    else:
        group = f.create_group( node[0].encode(encoding), track_order=True )
    group.attrs.create('name',  np.array(node[0].encode(encoding), dtype=str_dtype) )
    group.attrs.create('flags', np.array([1],dtype=np.int32))
    group.attrs.create('label', np.array(node[3].encode(encoding), dtype=str_dtype) )
    _setData(group, node[1])

    for child in node[2]:
        nodelist_to_group(group, child)

    return group

def _setData(group, nodevalue):
    if nodevalue is not None:
        is_str_value = False
        if isinstance(nodevalue,str):
            is_str_value = True
            group.attrs.create('type', np.array('C1'.encode(encoding), dtype=cgns_dtype))
            data = np.frombuffer(nodevalue.encode(encoding), dtype='int8'.encode(encoding))

        else:
            data_type = Numpy_dtype_to_CGNS_dtype[nodevalue.dtype]
            nodevalue_shape = nodevalue.shape
            if data_type == 'C1':
                is_str_value = True
                group.attrs.create('type', np.array('C1'.encode(encoding), dtype=cgns_dtype))
                if len(nodevalue_shape) == 1:
                    for i in range(nodevalue_shape[0]):
                        nodevalue[i] = nodevalue[i].decode(encoding)
                elif len(nodevalue_shape) == 2:
                    for i in range(nodevalue_shape[0]):
                        for j in range(nodevalue_shape[1]):
                            nodevalue[i,j] = nodevalue[i,j].decode(encoding)
                elif len(nodevalue_shape) == 3:
                    for i in range(nodevalue_shape[0]):
                        for j in range(nodevalue_shape[1]):
                            for k in range(nodevalue_shape[2]):
                                nodevalue[i,j,k] = nodevalue[i,j,k].decode(encoding)
                else:
                    raise NotImplementedError("Rank of str numpy objects must be <=3")

                data = np.frombuffer(nodevalue.T, dtype='int8'.encode(encoding))
                data.shape = nodevalue_shape[::-1]

            else:
                group.attrs.create('type', np.array(data_type.encode(encoding), dtype=cgns_dtype))
                if len(nodevalue.shape) > 1: 
                    data = nodevalue.T # put it as F-contiguous compatible
                else:
                    data = nodevalue

        if ' data' not in group:
            if use_chunks and is_str_value and len(data.shape)==1:
                maxshape = [None for _ in data.shape]
                group.create_dataset(' data', data=data, maxshape=maxshape, chunks=True)
            else:
                group.create_dataset(' data', data=data, chunks=None)
        else:
            group[' data'][:] = data

    else:
        try: del group[' data']
        except KeyError: pass
        group.attrs.create('type', np.array('MT'.encode(encoding), dtype=cgns_dtype))


def build_cgns_nodelist( group, links=[], ignore_DataArray=False ):
    nodename = group.name.split('/')[-1]  
    if nodename.startswith(' '): return
    children = []
    try:
        group_type = group.attrs['type'].decode(encoding)
    except KeyError:
        raise KeyError('could not find attribute "type" in node %s'%group.name)


    if group_type != 'LK':
        for childname in group:
            childnode = build_cgns_nodelist( group[childname], links=links,
                                             ignore_DataArray=ignore_DataArray )
            if not childnode: continue
            children += [ childnode ]

        cgns_type = extract_type(group)
        if ignore_DataArray and cgns_type == 'DataArray_t' and nodename not in nodesNamesToRead:
            cgns_value = '_skeleton'
        else:
            cgns_value = extract_value(group)
        
        return [ nodename, cgns_value, children, cgns_type ]
    
    links += [ extract_link(group) ]
        


def extract_value( group ):
    if ' data' not in group: return None # faster than try+except
    data = group[' data'][()]

    if isinstance(group.attrs['type'], str):
        cgns_dtype = group.attrs['type']
    else:
        cgns_dtype = group.attrs['type'].decode(encoding)

    if cgns_dtype == 'C1': 
        nodevalue_shape = data.shape
        decoded_data = np.empty_like(data, dtype='c')
        if len(nodevalue_shape) == 1:
            for i in range(nodevalue_shape[0]):
                decoded_data[i] = np.array(data[i]).tobytes().decode(encoding)
        elif len(nodevalue_shape) == 2:
            for i in range(nodevalue_shape[0]):
                for j in range(nodevalue_shape[1]):
                    decoded_data[i,j] = np.array(data[i,j]).tobytes().decode(encoding)
        elif len(nodevalue_shape) == 3:
            for i in range(nodevalue_shape[0]):
                for j in range(nodevalue_shape[1]):
                    for k in range(nodevalue_shape[2]):
                        decoded_data[i,j,k] = np.array(data[i,j,k]).tobytes().decode(encoding)
        else:
            raise NotImplementedError("Rank of str numpy objects must be <=3")
        
        return decoded_data.T
    
    if len(data.shape) > 1: data = data.T # put in memory as in Fortran

    return data


def extract_type( group ):
    label = group.attrs['label'].decode(encoding)
    if not label: label = 'DataArray_t'
    return label

def extract_link( group ):
    file = group[' file'][()].tobytes().decode(encoding).replace('\x00','')
    path = group[' path'][()].tobytes().decode(encoding).replace('\x00','')
    link = ['', file, path, path, 5]
    
    return link

def write_link(f, link):
    file = link[1] + '\x00'
    path = link[2] + '\x00'
    group = f[path]

    del group.attrs['flags']
    del group[' data']

    group.attrs['type'] = np.array('LK'.encode(encoding), dtype=cgns_dtype)
    group.attrs['label'] = np.array(''.encode(encoding), dtype=str_dtype)

    data = np.frombuffer(file.encode(encoding), dtype='int8'.encode(encoding))
    group.create_dataset(' file', data=data)

    data = np.frombuffer(path.encode(encoding), dtype='int8'.encode(encoding))
    group.create_dataset(' path', data=data)

    group[' link'] = h5py.ExternalLink(file, path)
