#--------------------------------------------------------------------------
# File and Version Information:
#  $Id$
#
# Description:
#  Module ExprVal...
#
#------------------------------------------------------------------------

"""Class which represents compile-time expression.

This software was developed for the SIT project.  If you use all or 
part of it, please give an appropriate acknowledgment.

@see RelatedModule

@version $Id$

@author Andrei Salnikov
"""


#------------------------------
#  Module's version from CVS --
#------------------------------
__version__ = "$Revision$"
# $Source$

#--------------------------------
#  Imports of standard modules --
#--------------------------------
import sys
import types
import operator

#---------------------------------
#  Imports of base class module --
#---------------------------------

#-----------------------------
# Imports for other modules --
#-----------------------------
from psddl.TypeLib import TypeLib

#----------------------------------
# Local non-exported definitions --
#----------------------------------
def _fqn(name):
    """Returns tuple (prefix, name), prefix is everything before last dot"""
    ns = name.rsplit('.',1)
    if len(ns) > 1: return ns[0], ns[1]
    return None, ns[0]

def _constants(obj):
    """Iterate over constant names defined in the objects context"""
    for c in obj.constants:
        yield c[0]

#------------------------
# Exported definitions --
#------------------------

#---------------------
#  Class definition --
#---------------------
class ExprVal ( object ) :

    #----------------
    #  Constructor --
    #----------------
    def __init__ ( self, val = None ) :
        if type(val) == ExprVal : 
            self.value = val.value
        else:
            self.value = val

    #-------------------
    #  Public methods --
    #-------------------

    def __str__(self):
        return str(self.value)
    
    def _genop(self, other, op, strop):
        """generic operator method"""
        
        # any operation with None is None
        if self.value is None: return None
        if other.value is None: return None
        
        # if any of them is string then do string expression
        if isinstance(self.value, types.StringType) and isinstance(other.value, types.StringType):
            return "(%s)%s(%s)" % (self.value, strop, other.value)
        if isinstance(self.value, types.StringType):
            return "(%s)%s%s" % (self.value, strop, other.value)
        if isinstance(other.value, types.StringType):
            return "%s%s(%s)" % (self.value, strop, other.value)

        # otherwise do a regular operator
        return op(self.value, other.value)

    def __add__(self, other):
        newval = self._genop(other, operator.add, '+')
        return ExprVal(newval)

    def __iadd__(self, other):
        self.value = self._genop(other, operator.add, '+')
        return self

    def __mul__(self, other):
        newval = self._genop(other, operator.mul, '*')
        return ExprVal(newval)

    def __imul__(self, other):
        self.value = self._genop(other, operator.mul, '*')
        return self

    def __cmp__(self, other):
        if type(other) == ExprVal:
            return self.value == other.value
        else:
            return self.value == other


    def isconst(self, typeobj):
        """Returns true if the expression is constant"""

        # None is non-constant (or rather unknown)
        if self.value is None: return False
        
        # integer value is constant
        if type(self.value) == types.IntType: return True
        
        typelib = TypeLib()
        
        # if expression is a constant then it's fixed
        prefix, name = _fqn(self.value)
        if prefix:
            
            pkgname, typename = _fqn(prefix)
            
            if pkgname:
                
                # Try typename in a package
                atype = typelib.findType(typename, pkgname)
                if atype and name in _costants(atype) : return True

            else:
                
                # use whole prefix as a type name in the context of current packag
                atype = typelib.findType(typename, typeobj.package)
                if atype and name in _costants(atype) : return True
                 
            # try to use whole prefix as package name
            pkg = typelib.findPackage(prefix)
            if pkg and name in _costants(pkg) : return True
            
        else:
            
            # Find constant in the attribute's type
            if name in _constants(typeobj) : return True
            if name in _constants(typeobj.package) : return True
                
        return False

#
#  In case someone decides to run this module
#
if __name__ == "__main__" :

    # In principle we can try to run test suite for this module,
    # have to think about it later. Right now just abort.
    sys.exit ( "Module is not supposed to be run as main module" )