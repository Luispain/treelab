#    Copyright 2023 ONERA - contact luis.bernardos@onera.fr
#
#    This file is part of MOLA.
#
#    MOLA is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    MOLA is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with MOLA.  If not, see <http://www.gnu.org/licenses/>.

__version__ = '0.4.3'

try:
    import os
    __TREELAB_PATH__ = os.path.sep.join(__file__.split(os.path.sep)[:-2])
    def getSHA():
        with open('{}/../.git/HEAD'.format(__TREELAB_PATH__), 'r') as HEAD:
            line = HEAD.readlines()[0]
            ref = line.split('ref: ')[-1].rstrip('\n')
        with open('{}/../.git/{}'.format(__TREELAB_PATH__, ref), 'r') as REF:
            SHA = REF.readlines()[0].rstrip('\n')
        return SHA
    __SHA__ = getSHA()
except:
    __SHA__ = 'unknown'
