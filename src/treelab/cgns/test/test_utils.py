from treelab import cgns

def test_check_only_contains_node_instances_true():
    a = cgns.Node()
    b = cgns.Node(Parent=a)
    c = cgns.Node(Parent=a)

    assert cgns.check_only_contains_node_instances(a)

def test_check_only_contains_node_instances_false():
    a = cgns.Node()
    b = cgns.Node(Parent=a)
    a[2] += [["Node", None, [], "DataArray_t"]]

    assert not cgns.check_only_contains_node_instances(a)