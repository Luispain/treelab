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
Implements class **Base**, which inherits from :py:class:`Node`

21/12/2021 - L. Bernardos - first creation
'''
import numpy as np
from fnmatch import fnmatch
from .. import misc as m
from .node import Node
from .zone import Zone

class Base(Node):
    """docstring for Base"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setType('CGNSBase_t')

        if self.value() is None:
            BaseValue = np.array([3,3],dtype=np.int32,order='F')
            for child in self.children():
                if isinstance(child, Zone):
                    BaseValue = np.array([child.dim(),3],dtype=np.int32,order='F')
                    break
            self.setValue(BaseValue)

        if self.name() == 'Node': self.setName( 'Base' )

    def save(self,*args,**kwargs):
        from .tree import Tree
        t = Tree()
        t.addChild( self )
        t.save(*args,**kwargs)

    def dim(self):
        return self.value()[0]

    def zones(self):
        return [c for c in self.children() if c.type()=="Zone_t"]

    def setCellDimension(self, CellDimension):
        self.value()[0] = CellDimension
    
    def setPhysicalDimension(self, PhysicalDimension):
        self.value()[1] = PhysicalDimension

    def isStructured(self):
        return all([zone.isStructured() for zone in self.zones()])
    
    def isUnstructured(self):
        return all([zone.isUnstructured() for zone in self.zones()])

    def isHybrid(self):
        return not self.isStructured() and not self.isUnstructured()
    
    def newFields(self, FieldNames, Container='FlowSolution',
                  GridLocation='auto', dtype=np.float64, return_type='dict',
                  ravel=False):

        arrays = []
        zoneNames = []
        for zone in self.zones():
            zoneNames.append( zone.name() )
            arrays.append( zone.newFields(FieldNames, Container=Container, 
                GridLocation=GridLocation,dtype=dtype, return_type=return_type,
                ravel=False))

        if return_type == 'list':
            return arrays 
        else:
            v = dict()
            for name, array in zip(zoneNames, arrays):
                v[ name ] = array
            return v

    def getFields(self, FieldNames, Container='FlowSolution',
                  BehaviorIfNotFound='create', dtype=np.float64, return_type='dict',
                  ravel=False):

        arrays = []
        zoneNames = []
        for zone in self.zones():
            zoneNames.append( zone.name() )
            arrays.append( zone.newFields(FieldNames, Container=Container, 
                BehaviorIfNotFound=BehaviorIfNotFound,dtype=dtype,
                return_type=return_type,ravel=False))

        if return_type == 'list':
            return arrays 
        else:
            v = dict()
            for name, array in zip(zoneNames, arrays):
                v[ name ] = array
            return v

    def getAllFields(self,include_coordinates=True, return_type='dict',ravel=False):

        arrays = []
        zoneNames = []
        for zone in self.zones():
            zoneNames.append( zone.name() )
            arrays.append( zone.getAllFields(
                include_coordinates=include_coordinates,
                return_type=return_type,ravel=ravel) )

        if return_type == 'list':
            return arrays 
        else:
            v = dict()
            for name, array in zip(zoneNames, arrays):
                v[ name ] = array
            return v

    def useEquation(self, *args, **kwargs):
        for zone in self.zones(): zone.useEquation(*args, **kwargs)

    def numberOfPoints(self):
        return int( np.sum( [ z.numberOfPoints() for z in self.zones() ]) )

    def numberOfCells(self):
        return int( np.sum( [ z.numberOfPoints() for z in self.zones() ]) )

    def numberOfZones(self):
        return len( self.zones() ) 

    def getElementsTypes(self):
        types = set()
        for zone in self.zones():
            types.update(zone.getElementsTypes())
        return types
    
    def renameFamily(self, current_fam_name: str, new_fam_name: str, verbose: bool=True):
        '''
        Rename a Family in the tree, or all families which match a given pattern. 

        Parameters
        ----------
        mesh : cgns.Tree
            
        current_fam_name : str
            name of the family to modify, or pattern to modify. Can begin or/and end with '*', 
            but cannot contain a '*' in the middle of the string.

        new_fam_name : str
            new name, without wildcards

        verbose : bool
            If True, print which families are renamed

        Examples
        --------

        >>> mesh.renameFamily('BLADE', 'Blade')    # Rename Family BLADE to Blade
        >>> mesh.renameFamily('BLADE*', 'Blade')   # Rename Family BLADE to Blade and BLADE_TIP to Blade_TIP
        >>> mesh.renameFamily('*BLADE', 'Blade')   # Rename Family BLADE to Blade and rotor_BLADE to rotor_Blade
        >>> mesh.renameFamily('*BLADE*', 'Blade')  # Rename Family BLADE to Blade and rotor_BLADE_TIP to rotor_Blade_TIP

        '''
        def update_new_fam_name(name, pattern, replacement):
            if '*' not in pattern:
                return replacement
            
            elif pattern.startswith('*') and pattern.endswith('*'):
                search_term = pattern[1:-1]
                new_name = name.replace(search_term, replacement)
                return new_name

            elif pattern.endswith('*'):
                search_term = pattern[:-1]
                new_name = replacement + name[len(search_term):]
                return new_name
    
            elif pattern.startswith('*'):
                search_term = pattern[1:]
                new_name = name[:-len(search_term)] + replacement
                return new_name

            else:
                raise ValueError(f"The pattern ({pattern}) cannot contain a '*' in the middle of it")
        

        if len(current_fam_name) > 2 and '*' in current_fam_name[1:-1]:
            raise Exception(f"current_fam_name ({current_fam_name}) cannot contain wildcards '*' in the middle of the string.")

        for family_node in self.group(Type='Family', Depth=1):
            family = family_node.name()
            if fnmatch(family, current_fam_name):

                updated_new_fam_name = update_new_fam_name(family, current_fam_name, new_fam_name)
                if verbose:
                    print(f'Renaming Family {family} to {updated_new_fam_name}')

                # change Family Name
                if not self.get(Type='Family', Name=updated_new_fam_name, Depth=2):
                    family_node.setName(updated_new_fam_name)  
                else:
                    family_node.remove()  # already a Family with the same name 

                # Change also the value of all nodes FamilyName_t or AdditionalFamilyName_t related to that Family                
                for node in self.group(Type='*FamilyName', Value=family):
                    node.setValue(updated_new_fam_name)    
    
    def forceShorterZoneNames(self, max_length=32, root_name='Zone', max_number_of_figures=4, verbose=True):
        # 32 is the max length for a node name as defined by the CGNS standard
        # https://cgns.org/standard/SIDS/convention.html#data-structure-notation-conventions
        assert max_length <= 32

        def create_names_generators_by_family():            

            assert len(root_name)+max_number_of_figures <= max_length

            existing_zone_names = [z.name() for z in self.zones()]

            def create_names_generator():
                for suffix in range(1, pow(10, max_number_of_figures)):
                    name = f"{root_name}{suffix}"
                    if name not in existing_zone_names:
                        yield name

            generators = dict(default=create_names_generator())

            zones_families = []
            for z in self.zones():
                FamilyName = z.get(Type='FamilyName', Depth=1)
                if FamilyName:
                    zones_families.append(FamilyName.value())

            for family in zones_families:

                assert len(root_name)+1+len(family)+max_number_of_figures <= max_length
            
                def gen(family):
                    for suffix in range(1, pow(10, max_number_of_figures)):
                        name = f"{root_name}_{family}{suffix}"
                        if name not in existing_zone_names:
                            yield name
                generators[family] = gen(family)
            
            return generators

        names_generators = create_names_generators_by_family()

        for zone in self.zones():
            if len(zone.name()) > max_length:
                try:
                    family = zone.get(Type='FamilyName', Depth=1).value()
                except:
                    family = 'default'

                new_name = next(names_generators[family])
                if verbose:
                    print(f'rename zone {zone.name()} to {new_name}')

                # First change all nodes values in the tree containing that zone name
                nodes_with_zone_name_as_value = self.group(Value=zone.name(), Type='GridConnectivity1to1_t')
                for node in nodes_with_zone_name_as_value:
                    node.setValue(new_name)

                # Finally change zone name
                zone.setName(new_name)

    def removeEmptyZones(self):
        for zone in self.zones():
            if zone.isEmpty(): 
                zone.remove()
                