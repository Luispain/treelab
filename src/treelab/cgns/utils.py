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

import numpy as np
from .. import misc as m

def castNode( NodeOrNodelikeList, Parent=None ):
    '''
    Transform a Node or a CGNS Python-like 4-item list into treelab objects
    (Tree, Base, Zone, Node...). 
    This function is applied recursively on children.
    '''
    from .node import Node

    if not isinstance(NodeOrNodelikeList, Node):
        node = Node(NodeOrNodelikeList, Parent=Parent)
    else:
        node = NodeOrNodelikeList
    
    for i, n in enumerate(node[2]):
        node[2][i] = castNode(n, Parent=node)

    if node[3] == 'Zone_t':
        from .zone import Zone
        if not isinstance(node, Zone):
            node = Zone(node)
        try: Kind = node.childNamed('.Component#Info').childNamed('kind').value()
        except: Kind = None
        if Kind is None:
            if node.isStructured() and node.dim() == 1:
                from .mesh.curves import Curve
                if not isinstance(node, Curve):
                    node = Curve(node)
        elif Kind == 'LiftingLine':
            try:
                from mola.LiftingLine import LiftingLine
                if not isinstance(node, LiftingLine):
                    node = LiftingLine(node)
            except:
                pass
        else:
            raise IOError('kind of zone "%s" not implemented'%Kind)

    elif node[3] == 'CGNSBase_t':
        from .base import Base
        if not isinstance(node, Base):
            node = Base(node)

    elif node[3] == 'CGNSTree_t':
        from .tree import Tree
        t = Tree(node)
        node = t

    return node

def load_workflow_parameters(filename):
    from .tree import Tree
    from .read_write import h5py2cgns as h
    wfp = h.load_from_path(filename, 'WorkflowParameters')
    wfp = castNode(wfp)
    tree = Tree()
    tree.addChild(wfp)
    wfp_dict = tree.getParameters('WorkflowParameters',transform_numpy_scalars=True)
    return wfp_dict

def load_from_path(filename, path):
    from .node import Node
    from .read_write import h5py2cgns as h
    wfp = h.load_from_path(filename, path)
    return castNode(wfp)


def readNode(filename, path, backend='h5py2cgns'):

    if path.startswith('CGNSTree/'):
        path_map = path.replace('CGNSTree','')
    else:
        path_map = path

    if backend == 'h5py2cgns':
        from .read_write import h5py2cgns as h
        if path_map.startswith('/'): path_map = path_map[1:]
        f =h.load_h5(filename)
        group = f[ path_map ]
        node = h.build_cgns_nodelist( group )
        node = castNode( node )

    elif backend == 'pycgns':
        import CGNS.MAP as CGM
        t, _, _ = CGM.load( filename, subtree=path_map )
        t = castNode(t)
        node = t.getAtPath( path )
    
    elif backend == 'cassiopee':
        import Converter.Filter as Filter
        node = Filter.readNodesFromPaths(filename, [path_map])[0]
        node = castNode( node )
    
    else:
        raise ModuleNotFoundError('%s backend not supported'%backend)

    if node is None:
        raise ValueError("node %s not found in %s"%( path, filename ))


    return node

def load(filename, only_skeleton=False, backend='h5py2cgns'):
    '''
    Open a file and return a :py:class:`~treelab.cgns.tree.Tree`.

    Parameters
    ----------

        filename : str or Tree or list
            Must be either:

            * relative or absolute path of the file name in ``*.cgns`` or ``*.hdf5``
              format containing the `CGNS`_ tree.
            
            * an object :py:class:`treelab.cgns.tree.Tree`. In this case, this function does nothing.

            * a list, assumed to be a tree or a list or trees as manipulated by h5py, Cassiopee or Maia. 
              In this case, this function performs a py:fun:`add` operation on that list.

        only_skeleton : bool
            if :py:obj:`True`, then data associated to *DataArray_t* nodes is 
            not loaded.

            .. note::
                this is currently available with *h5py2cgns* backend

        backend : str
            select a backend for loading the file data

    Returns
    -------

        t : :py:class:`~treelab.cgns.tree.Tree`
            the tree node contained in file

    Examples
    --------

        Let's suppose that you want to open data contained in an existing
        file named ``myfile.cgns``:

        ::

          import treelab.cgns  as M
          t = cgns.load('myfile.cgns')

        will open the file, including :py:class:`numpy.ndarray` contained in *DataArray_t* nodes.
        If you want to open a file without loading *DataArray_t* data, then you
        can do it like this:

        ::

          import treelab.cgns  as M
          t = cgns.load('myfile.cgns', only_skeleton=True)


    '''

    from .tree import Tree

    if isinstance(filename, str):
        
        if backend == 'h5py2cgns':
            from .read_write import h5py2cgns as h

            t, f, links = h.load(filename, only_skeleton=only_skeleton)
            t = castNode(t)
            for link in links:
                t.addLink(path=link[3], target_file=link[1], target_path=link[2])

        elif backend == 'pycgns':
            import CGNS.MAP as CGM
            t, links, paths = CGM.load(filename)
            for p in paths:
                raise IOError('file %s : could not read node %s'%(filename,str(p)))
            t = castNode(t)

            for link in links:
                t.addLink(path=link[3], target_file=link[1], target_path=link[2])

        elif backend == 'cassiopee':
            import Converter.PyTree as C
            links = []
            t = C.convertFile2PyTree(filename, links=links)
            t = castNode(Tree(t))
            for link in links:
                t.addLink(path=link[3], target_file=link[1], target_path=link[2])

        elif backend == 'maia':
            import maia
            from mpi4py import MPI
            t = maia.io.file_to_dist_tree(filename, MPI.COMM_WORLD)
            t = castNode(t)
            # TODO add links
            print('Links are not handle with the maia backend for now.')

        else:
            raise ModuleNotFoundError('%s backend not supported'%backend)
        
    elif isinstance(filename, Tree):
        t = filename

    elif isinstance(filename, list):
        t = add(filename)

    else:
        raise TypeError('The first argument of function load must be either a file name (str), a Tree object, or a list')



    return castNode(t)

def save(data, *args, **kwargs):
    '''
    Make a merge of information contained in **data** and then save the resulting
    :py:class:`~treelab.cgns.tree.Tree`.

    Parameters
    ----------

        data : list
            heterogeneous container of nodes compatible with :py:func:`add`

        args
            mandatory comma-separated arguments of
            :py:class:`~treelab.cgns.node.Node`'s :py:meth:`~treelab.cgns.node.Node.save` method

        kwargs
            optional pair of ``keyword=value`` arguments of
            :py:class:`~treelab.cgns.node.Node`'s :py:meth:`~treelab.cgns.node.Node.save` method

    Returns
    -------

        t : :py:class:`~treelab.cgns.tree.Tree`
            a tree including all merged nodes contained in **data**

    Examples
    --------
    
    For the following examples, we only need to import main :py:mod:`treelab.cgns ` subpackage:

    ::
    
        import treelab.cgns  as M

    Let us start easy. We create a node, and write it down into a file: 

    ::

        n = cgns.Node() # create a Node
        cgns.save( n, 'out.cgns' )   # save it into a file named out.cgns

    Please note that in this case :python:`cgns.save(n, 'out.cgns')` is 
    equivalent to :python:`n.save('out.cgns')`.

    Let us make things just a little bit more complicated. We create several
    nodes and we save them into a file using an auxiliary list:

    ::

        n1 = cgns.Node()  # create first node
        n2 = cgns.Node()  # create second node  
        cgns.save( [n1, n2], 'out.cgns' ) # save all into a file using a list


    and both nodes are written, producing the following tree structure:

    .. code-block:: text

        CGNSTree
        CGNSTree/CGNSLibraryVersion
        CGNSTree/Node
        CGNSTree/Node.0    

    .. note::
        nodes at same hierarchical level with identical names are automatically
        renamed. In this example, :python:`n2` was initally named :python:`'Node'`,
        but since :python:`n1` is located at same hierarchical level and is also
        named :python:`'Node'`, then :python:`n2` has been renamed :python:`'Node.0'`

    Conveniently, this also works in combination with standard `pycgns`_ 
    lists. For example, let us slightly modify previous example by including a
    CGNS node through its pure python list definition:

    ::

        n1 = cgns.Node()  # create first node using MOLA
        n2 = ['MyNode',None,[],'DataArray_t']  # create second node using a standard pycgns list
        cgns.save( [n1, n2], 'out.cgns' ) # save all into a file using a list

    Which produces the following tree structure:

    .. code-block:: text

        CGNSTree
        CGNSTree/CGNSLibraryVersion
        CGNSTree/Node
        CGNSTree/MyNode

    Now let us make things more complicated. Suppose we have two lists of nodes
    which may possibly include children nodes. We can effectively create another 
    list whose items are the two aforementioned lists, and pass it to the save
    function:

    ::

        # create a node named 'NodeA'
        nA = cgns.Node(Name='NodeA') 

        # create 3 children nodes using unique names and attach them to nA
        for _ in range(3): cgns.Node(Parent=nA, override_sibling_by_name=False) 

        # let us make a copy of nA and rename it
        nB = nA.copy()
        nB.setName('NodeB')

        # now we have our first list of nodes (including children):
        first_list = [nA, nB]

        # We can repeat the previous operations in order to declare a second list
        nC = cgns.Node(Name='NodeC') 
        for _ in range(3): cgns.Node(Parent=nC, override_sibling_by_name=False) 

        nD = nC.copy()
        nD.setName('NodeD')
        second_list = [nC, nD]

        # Now we have two lists of nodes (which includes children), and we want
        # to save all this information into a file. Then, we can simply do:

        cgns.save( [ first_list, second_list ], 'out.cgns')

    which will produce a tree with following structure:

    .. code-block:: text

        CGNSTree
        CGNSTree/CGNSLibraryVersion
        CGNSTree/NodeA
        CGNSTree/NodeA/Node
        CGNSTree/NodeA/Node.0
        CGNSTree/NodeA/Node.1
        CGNSTree/NodeB
        CGNSTree/NodeB/Node
        CGNSTree/NodeB/Node.0
        CGNSTree/NodeC
        CGNSTree/NodeC/Node
        CGNSTree/NodeC/Node.0
        CGNSTree/NodeC/Node.1
        CGNSTree/NodeD
        CGNSTree/NodeD/Node
        CGNSTree/NodeD/Node.0
        CGNSTree/NodeD/Node.1

    One may note that nodes ``NodeA``, ``NodeB``, ``NodeC`` and ``NodeD`` are 
    all put into the same hierarchical level, but their children remains in second
    level. Actually, the hierarchical level does **not**  depend on the items'
    arrangement of the argument list given to save function, but rather on their
    own `CGNS`_ path structure.

    Indeed, the save call of previous example would be equivalent to any of these
    calls:

    ::
        
        # equivalent calls:
        cgns.save( [nA, nB, nC, nD], 'out.cgns') 
        cgns.save( [ [nA, nB], [nC, nD]], 'out.cgns') 
        cgns.save( [nA, [nB], nC, nD], 'out.cgns') 
        cgns.save( [nA, nB, nC, [[[nD]]]], 'out.cgns') 
        cgns.save( [nA, [nB], [nC, [[nD]]]], 'out.cgns') 
        ...


    '''
    from .tree import Tree
    from .base import Base
    from .zone import Zone 

    if type(data) in ( Tree, Base, Zone ):
        t = data
    elif isinstance(data, list):
        t = add( data )
    elif isinstance(data, dict):
        t = add( **data )
    else:
        raise TypeError('saving data of type %s not supported'%type(data))

    t.save(*args, **kwargs)

    return t

def add(*data1, **data2 ):
    '''
    Add nodes into a single :py:class:`~treelab.cgns.tree.Tree` structure, by changing names
    if necessary to ensure that all nodes at the same level have different names.

    Parameters
    ----------
        
        data1
            comma-separated arguments of type :py:class:`list` containing the 
            nodes to be merged

        data2
            pair of ``keyword=value`` where each value is a :py:class:`list`
            containing the nodes to be merged and ``keyword`` is the name of the
            new :py:class:`~treelab.cgns.base.Base` container automatically created
            where nodes are being placed.

    Returns
    -------

        t : :py:class:`~treelab.cgns.tree.Tree`
            a tree including all merged nodes contained in **data1** and/or **data2**

    Examples
    --------

    Declare a :py:class:`list` of :py:class:`~treelab.cgns.tree.Tree` and get the
    :py:class:`~treelab.cgns.tree.Tree` which contains them all:

    ::

        import treelab.cgns  as M
        a = cgns.Zone(Name='A')
        b = cgns.Zone(Name='B')
        c = cgns.Zone(Name='C')

        t = cgns.add(a,b,c)

    will produce the following tree structure:

    .. code-block:: text

        CGNSTree/CGNSLibraryVersion
        CGNSTree/Base
        CGNSTree/Base/A
        CGNSTree/Base/A/ZoneType
        CGNSTree/Base/B
        CGNSTree/Base/B/ZoneType
        CGNSTree/Base/C
        CGNSTree/Base/C/ZoneType

    .. hint:: 
        you may easily print the structure of a :py:class:`~treelab.cgns.tree.Tree`
        (or any :py:class:`~treelab.cgns.node.Node`) using :py:meth:`~treelab.cgns.node.Node.printPaths()`

    Note that the function has automatically recognized that the input nodes are
    of type :py:class:`~treelab.cgns.zone.Zone` and they have been put into a 
    container of type :py:class:`~treelab.cgns.base.Base`, according to `CGNS`_ standard.
    
    You may want to put the zones in different bases. You can achieve this 
    easily using a pairs of ``keyword=value`` arguments:

    ::

        import treelab.cgns  as M
        a = cgns.Zone(Name='A')
        b = cgns.Zone(Name='B')
        c = cgns.Zone(Name='C')

        t = cgns.add( FirstBase=a, SecondBase=[b, c] )

    which will produce a :py:class:`~treelab.cgns.tree.Tree` with following structure:

    .. code-block:: text

        CGNSTree
        CGNSTree/FirstBase
        CGNSTree/FirstBase/A
        CGNSTree/FirstBase/A/ZoneType
        CGNSTree/SecondBase
        CGNSTree/SecondBase/B
        CGNSTree/SecondBase/B/ZoneType
        CGNSTree/SecondBase/C
        CGNSTree/SecondBase/C/ZoneType

    .. hint:: 
        In Python you can replace a call of pairs of ``keyword=value`` with 
        an unpacking of a :py:class:`dict`. In other terms, this:

        >>> t = cgns.add( FirstBase=a, SecondBase=[b, c] )

        is equivalent to

        >>> myDict = dict(FirstBase=a, SecondBase=[b, c])
        >>> t = cgns.add( **myDict )

        note the use of the :py:class:`dict` unpacking operator :python:`**`

    .. hint:: 
        In Python you can replace a call of comma-separated arguments with 
        an unpacking of a :py:class:`list`. In other terms, this:

        >>> t = cgns.add( a, b, c )

        is equivalent to

        >>> myList = [ a, b, c ]
        >>> t = cgns.add( *myList )

        note the use of the :py:class:`list` unpacking operator :python:`*`

    .. seealso::
        Since this function is used internally in :py:func:`save`, refer to its doc
        for more relevant examples.


    '''
    from .tree import Tree
    if isinstance(data1, dict):
        t1 = Tree( **data1 )
    else:
        t1 = Tree( )
        t1.add( data1 )

    if isinstance(data2, dict):
        t2 = Tree( **data2 )
    else:
        t2 = Tree( )
        t2.add( data2 )

    t1.add(t2)

    return t1

def merge(nodes):
    '''
    Merge nodes in a single :py:class:`~treelab.cgns.node.Node` structure. 
    If two nodes have the same name, there will be only one in the result, with merged children.

    Parameters
    ----------
    nodes : list
        List of nodes to merge.

    Returns
    -------
    Node
        merged node
    '''
    from .node import Node
    assert isinstance(nodes, list)
    assert all([isinstance(n, Node) for n in nodes])

    merged_node = nodes[0].copy()
    for node in nodes[1:]:
        merged_node.merge(node)
    return merged_node

def getZones( data ):
    '''
    Get a list of zones contained in **data**.
    
    .. note::
        this function makes literally:

        >>> zones = cgns.add(data).getZones()

    Parameters
    ----------

        data : list
            heterogeneous container of nodes compatible with :py:func:`add`

    Returns
    -------

        zones: list
            list of :py:class:`~treelab.cgns.zone.Zone` contained in **data**

    Examples
    --------

    Gather all zones of a combination of list and an existing tree both 
    containing zones:

    ::

        import treelab.cgns  as M

        # arbitrarily create an heterogeneous list containing zones
        a = cgns.Zone(Name='A')
        b = cgns.Zone(Name='B')
        c = cgns.Zone(Name='C')
        some_zones = [a, [b,c] ]

        # arbitrarily create a tree containing zones (possibly in several Bases)
        t = cgns.Tree( FirstBase=[cgns.Zone(Name='D'),cgns.Zone(Name='E')],
                   SecondBase=[cgns.Zone(Name='A'),cgns.Zone(Name='F')])

        # create a container including all data
        container = some_zones + [t]

        zones = cgns.getZones( container )
        for z in zones: print(z.name())

    This will produce:

    .. code-block:: text

        A.0
        B
        C
        D
        E
        A
        F

    .. important::
        since this function makes use of :py:func:`add`, zones with identical
        names are renamed
    

    '''
    t = add( data ) # TODO avoid add
    return t.zones()

def getBases( data ):
    '''
    Get a list of bases contained in **data**.
    
    .. note::
        this function makes literally:

        >>> bases = cgns.add(data).getBases()

    Parameters
    ----------

        data : list
            heterogeneous container of nodes compatible with :py:func:`add`

    Returns
    -------

        bases: list
            list of :py:class:`~treelab.cgns.base.Base` contained in **data**

    Examples
    --------

    Gather all bases of a combination of list and an existing tree both 
    containing bases:

    ::

        import treelab.cgns  as M

        # arbitrarily create an heterogeneous list containing bases
        a = cgns.Base(Name='BaseA')
        b = cgns.Base(Name='BaseB')
        c = cgns.Base(Name='BaseC')
        some_bases = [a, [b,c] ]

        # arbitrarily create a tree containing bases
        t = cgns.Tree( FirstBase=[cgns.Zone(Name='D'),cgns.Zone(Name='E')],
                    SecondBase=[cgns.Zone(Name='A'),cgns.Zone(Name='F')])

        # create a container including all data
        container = some_bases + [t]

        bases = cgns.getBases( container )
        for base in bases: print(base.name())

    This will produce:

    .. code-block:: text

        BaseA
        BaseB
        BaseC
        FirstBase
        SecondBase

    .. important::
        since this function makes use of :py:func:`add`, bases with identical
        names are renamed
    
    '''
    t = add( data ) # TODO avoid add
    return t.bases()

def useEquation(data, *args, **kwargs):
    '''
    Call the :py:meth:`~treelab.cgns.zone.Zone.useEquation` method 
    for each :py:class:`~treelab.cgns.zone.Zone` contained in 
    argument **data**

    Parameters
    ----------

        data : list
            heterogeneous container of nodes compatible with :py:func:`add`

            .. note::
                :py:class:`~treelab.cgns.zone.Zone`'s are modified    

        args
            mandatory comma-separated arguments of
            :py:class:`~treelab.cgns.zone.Zone`'s :py:meth:`~treelab.cgns.zone.Zone.useEquation` method

        kwargs
            optional pair of ``keyword=value`` arguments of
            :py:class:`~treelab.cgns.zone.Zone`'s :py:meth:`~treelab.cgns.zone.Zone.useEquation` method

    Returns
    -------

        t : :py:class:`~treelab.cgns.tree.Tree`
            same result as :py:func:`add`

    Examples
    --------

    Create two :py:class:`~treelab.cgns.tree.Tree`, each containing a different 
    number of :py:class:`~treelab.cgns.zone.Zone` and create a new field named 
    ``field`` attributing a specific value:

    ::

        import treelab.cgns  as M


        zoneA = cgns.Mesh.Line( Name='zoneA', N=2 )
        zoneB = cgns.Mesh.Line( Name='zoneB', N=4 )
        zoneC = cgns.Mesh.Line( Name='zoneC', N=6 )

        tree1 = cgns.Tree(Base1=[zoneA, zoneB])
        tree2 = cgns.Tree(Base2=[zoneC])

        cgns.useEquation( [tree1, tree2], '{field} = 12.0' )

        for zone in zoneA, zoneB, zoneC:
            print(zone.name()+' has field '+str(zone.field('field')))


    this will produce: 

    .. code-block:: text

        zoneA has field [12. 12.]
        zoneB has field [12. 12. 12. 12.]
        zoneC has field [12. 12. 12. 12. 12. 12.]


    '''

    t = add( data ) # TODO avoid add
    for zone in t.zones(): zone.useEquation(*args, **kwargs)

    return t

def newZoneFromArrays(Name, ArraysNames, Arrays):
    '''
    This handy function easily produces a structured :py:class:`~treelab.cgns.zone.Zone`
    directly from numpy arrays.

    Parameters
    ----------

        Name : str
            The name you want to attribute to the new :py:class:`~treelab.cgns.zone.Zone`

        ArraysNames: list
            A :py:class:`list` of :py:class:`str` corresponding to the names 
            of each field (or coordinate) contained in **Arrays** (see next)

        Arrays : :py:class:`list` of :py:class:`numpy.ndarray`
            A :py:class:`list` containing each numpy array (coordinates and/or
            fields). All :py:class:`numpy.ndarray` must have identical :py:obj:`~numpy.ndarray.shape`

    Returns
    -------

        zone : :py:class:`~treelab.cgns.zone.Zone`
            the new created :py:class:`~treelab.cgns.zone.Zone`

    Examples
    --------

    Create a block including a field 

    ::

        import treelab.cgns  as M
        import numpy as np

        # create a grid
        x, y, z = np.meshgrid( np.linspace(0,1,11),
                               np.linspace(0,0.5,7),
                               np.linspace(0,0.3,4), indexing='ij')

        # create a field
        field = x*y

        # create the new zone using numpy arrays of coordinates and field
        zone = cgns.newZoneFromArrays( 'block', ['x','y','z','field'],
                                             [ x,  y,  z,  field ])

        # save result
        cgns.save(zone,'out.cgns')

    
    .. note::
        In this example we employ useful numpy functions
        :py:func:`~numpy.meshgrid` and :py:func:`~numpy.linspace`. In order to
        obtain a direct ordered mesh (following the right-hand-rule),
        we must specify :python:`indexing='ij'` option to :py:func:`~numpy.meshgrid`
        

    See also
    --------

    :py:func:`newZoneFromDict`
    '''

    from .node import Node
    from .zone import Zone
    CoordinatesNames = list(m.CoordinatesShortcuts)
    numpyarray = np.array(Arrays[0])
    dimensions = []
    for d in range(len(numpyarray.shape)):
        dimensions += [[numpyarray.shape[d], numpyarray.shape[d]-1, 0]]
    zone = Zone(Name=Name, Value=np.array(dimensions,dtype=np.int32,order='F'))

    Coordinates = Node(Name='GridCoordinates', Type='GridCoordinates_t')
    Fields = Node(Name='FlowSolution', Type='FlowSolution_t')

    for name, array in zip(ArraysNames, Arrays):
        numpyarray = np.array(array,order='F')
        if name in CoordinatesNames:
            Node(Name=m.CoordinatesShortcuts[name], Value=numpyarray,
                 Type='DataArray_t', Parent=Coordinates)
        else:
            Node(Name=name, Value=numpyarray, Type='DataArray_t', Parent=Fields)

    if Coordinates.hasChildren(): zone.addChild( Coordinates )
    if Fields.hasChildren(): zone.addChild( Fields )

    return zone

def newZoneFromDict(Name, DictWithArrays):
    '''
    This handy function easily produces a structured :py:class:`~treelab.cgns.zone.Zone`
    directly from numpy arrays.

    Parameters
    ----------

        Name : str
            The name you want to attribute to the new :py:class:`~treelab.cgns.zone.Zone`

        DictWithArrays: dict
            A :py:class:`dict` where each key corresponds to a field or coordinate 
            name and each value corresponds to the :py:class:`numpy.ndarray`.
            All :py:class:`numpy.ndarray` must have identical :py:obj:`~numpy.ndarray.shape`

    Returns
    -------

        zone : :py:class:`~treelab.cgns.zone.Zone`
            the new created :py:class:`~treelab.cgns.zone.Zone`

    Examples
    --------

    Create a block including a field 

    ::

        import treelab.cgns  as M
        import numpy as np

        # create a grid
        x, y, z = np.meshgrid( np.linspace(0,1,11),
                               np.linspace(0,0.5,7),
                               np.linspace(0,0.3,4), indexing='ij')

        # create a field
        field = x*y

        # create the new zone using numpy arrays of coordinates and field
        zone = cgns.newZoneFromDict( 'block', dict(x=x, y=y, z=z, filed=field) )

        # save result
        cgns.save(zone,'out.cgns')


    .. note::
        In this example we employ useful numpy functions
        :py:func:`~numpy.meshgrid` and :py:func:`~numpy.linspace`. In order to
        obtain a direct ordered mesh (following the right-hand-rule),
        we must specify :python:`indexing='ij'` option to :py:func:`~numpy.meshgrid`
        

    See also
    --------

    :py:func:`newZoneFromArrays`
    '''
    ArraysNames, Arrays = [], []
    for k in DictWithArrays:
        ArraysNames += [k]
        Arrays += [DictWithArrays[k]]

    return newZoneFromArrays(Name, ArraysNames, Arrays)


def check_only_contains_node_instances( node ):
    from .node import Node
    
    if not isinstance(node, Node):
        return False

    for child in node.children():
        if not check_only_contains_node_instances(child):
            return False

    return True

def assert_only_contains_node_instances( node ):
    assert check_only_contains_node_instances(node)