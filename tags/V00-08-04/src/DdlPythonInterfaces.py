#--------------------------------------------------------------------------
# File and Version Information:
#  $Id: DdlPythonInterfaces.py 3643 2012-05-26 04:23:12Z jbarrera@SLAC.STANFORD.EDU $
#
# Description:
#  Module DdlPythonInterfaces...
#
#------------------------------------------------------------------------

"""DDL parser which generates psana C++ interfaces.

This software was developed for the SIT project.  If you use all or 
part of it, please give an appropriate acknowledgment.

@see RelatedModule

@version $Id: DdlPythonInterfaces.py 3643 2012-05-26 04:23:12Z jbarrera@SLAC.STANFORD.EDU $

@author Andrei Salnikov, Joseph S. Barrera III
"""


#------------------------------
#  Module's version from CVS --
#------------------------------
__version__ = "$Revision: 3643 $"
# $Source$

#--------------------------------
#  Imports of standard modules --
#--------------------------------
import sys
import os
import types
import string
import re

#---------------------------------
#  Imports of base class module --
#---------------------------------

#-----------------------------
# Imports for other modules --
#-----------------------------
from psddl.Attribute import Attribute
from psddl.ExprVal import ExprVal
from psddl.Method import Method
from psddl.Package import Package
from psddl.Template import Template as T
from psddl.Enum import Enum
from psddl.Type import Type

#----------------------------------
# Local non-exported definitions --
#----------------------------------

def _interpolate(expr, typeobj):
    expr = expr.replace('{xtc-config}', 'cfg')
    expr = expr.replace('{type}.', typeobj.name+"::")
    expr = expr.replace('{self}.', "this->")
    return expr

def _typename(type, top_ns=None):
    if type is None: return 'void'
    return type.fullName('C++', top_ns)

def _typedecl(type, top_ns=None):
    typename = _typename(type, top_ns)
    if not type.basic : typename = "const "+typename+'&'
    return typename

def _argdecl(name, type):    
    return _typedecl(type) + ' ' + name

def _argdecl2(name, type):    
    return name

def _dims(dims):
    return ''.join(['[%s]'%d for d in dims])

def _dimargs(rank, type):
    int_type = type.lookup('uint32_t')
    return [('i%d'%i, int_type) for i in range(rank)]

def _dimexpr(dims):
    return ''.join(['[i%d]'%i for i in range(len(dims))])

#------------------------
# Exported definitions --
#------------------------

#---------------------
#  Class definition --
#---------------------
class DdlPythonInterfaces ( object ) :

    #----------------
    #  Constructor --
    #----------------
    def __init__ ( self, incname, cppname, backend_options, log ) :
        """Constructor
        
            @param incname  include file name
        """
        self.incname = incname
        self.cppname = cppname
        self.incdirname = backend_options.get('gen-incdir', "")
        self.top_pkg = backend_options.get('top-package')
        self.psana_inc = backend_options.get('psana-inc', "psddl_psana")
        self.psana_ns = backend_options.get('psana-ns', "Psana")
        self.generics = {}
        
        self._log = log

    #-------------------
    #  Public methods --
    #-------------------

    def parseTree ( self, model ) :
        
        # open output files
        self.cpp = file(self.cppname, 'w')

        warning = "/* Do not edit this file, as it is auto-generated */\n"
        print >>self.cpp, warning

        # add necessary includes to include file
        print >>self.cpp, '#include <boost/python.hpp>'
        print >>self.cpp, '#include <boost/make_shared.hpp>'
        print >>self.cpp, '#include "ndarray/ndarray.h"'
        print >>self.cpp, '#include "pdsdata/xtc/TypeId.hh"'
        inc = os.path.join(self.psana_inc, os.path.basename(self.incname))
        print >>self.cpp, '#include "%s" // inc_psana' % inc
        print >>self.cpp, '#include "psddl_python/Converter.h"'
        print >>self.cpp, '#include "psddl_python/DdlWrapper.h"'
        print >>self.cpp, '#include "psddl_python/ConverterMap.h"'
        print >>self.cpp, '#include "psddl_python/ConverterBoostDef.h"'
        print >>self.cpp, '#include "psddl_python/ConverterBoostDefSharedPtr.h"'
        print >>self.cpp, ""

        if self.top_pkg : 
            print >>self.cpp, T("namespace $top_pkg {")[self]

        # loop over packages in the model
        for pkg in model.packages() :
            if not pkg.included :
                self._log.debug("parseTree: package=%s", repr(pkg))
                self._parsePackage(pkg)

        if self.top_pkg : 
            print >>self.cpp, T("} // namespace $top_pkg")[self]

        # close all files
        self.cpp.close()

    def namespace_prefix(self):
        prefix = self.pkg.name + "::"
        if self.top_pkg: prefix = self.top_pkg + "::" + prefix
        return prefix

    def qualifiedConstantValue(self,constant):
        '''constant values sometimes reference previously defined 
        constants.  If the constant value is not numeric, we search the 
        parent namespaces to see if it is defined.  If so we qualify
        with the namespace found.  If not, it may be a valid expression for 
        code generation, so we just return it (so expressions like "4*34" 
        will be returned unmodified.
        '''
        value = constant.value
        try:            
            float(value) # this will not catch expressions like 4*17 or 0xFF
            return value
        except ValueError:
            enclosing = constant.parent
            while enclosing is not None:
                if type(enclosing) in [Type, Package]:
                    for constant in enclosing.constants():
                        if constant.name == value:
                            return enclosing.fullName('C++',self.psana_ns) + '::' + value
                    for enum in enclosing.enums():
                        for enum_constant in enum.constants():
                            if enum_constant.name == value:
                                return enclosing.fullName('C++',self.psana_ns) + '::' + value
                enclosing = enclosing.parent

        self._log.debug("Coud not find parent namespace for %s", value)
        return value

    def _parseEnum(self,enum):
        print >>self.cpp
        print >>self.cpp, T('  enum_<$fullname>("$shortname")') \
                           (fullname=enum.fullName('C++',self.psana_ns),
                            shortname=enum.name)
        enclosingFullName = enum.parent.fullName('C++',self.psana_ns)
        for enum_constant in enum.constants():
            print >>self.cpp, T('    .value("$constant",$enclosingFullName::$constant)') \
                                   (constant=enum_constant.name, enclosingFullName=enclosingFullName)
        print >>self.cpp, '  ;'

    def _parsePackage(self, pkgX):
        self.pkg = pkgX

        # open namespaces
        print >>self.cpp, T("namespace $name {")[self.pkg]
        print >>self.cpp, ""
        print >>self.cpp, "using namespace boost::python;"
        print >>self.cpp, "using boost::python::object;"
        print >>self.cpp, "using boost::shared_ptr;"
        print >>self.cpp, "using std::vector;"
        print >>self.cpp, ""

        print >>self.cpp, 'namespace {'
        print >>self.cpp, 'template<typename T, std::vector<int> (T::*MF)() const>'
        print >>self.cpp, 'PyObject* method_shape(const T *x) {'
        print >>self.cpp, '  return detail::vintToList((x->*MF)());\n}'
        print >>self.cpp, '} // namespace\n'


        print >>self.cpp, "void createWrappers(PyObject* module) {"

        # create sub-module for everything inside
        print >>self.cpp, T('  PyObject* submodule = Py_InitModule3( "psana.$name", 0, "The Python wrapper module for $name types");')[self.pkg]
        print >>self.cpp, '  Py_INCREF(submodule);'
        print >>self.cpp, T('  PyModule_AddObject(module, "$name", submodule);')[self.pkg]
        print >>self.cpp, '  scope mod = object(handle<>(borrowed(submodule)));'

        # expose any package level constants
        if len(self.pkg.constants())>0:
            print >>self.cpp
        for constant in self.pkg.constants():
            print >>self.cpp, T('  mod.attr("$name")=$value;')(name=constant.name,
                                                               value=self.qualifiedConstantValue(constant))

        # expose any package level enums:
        for enum in self.pkg.enums():
            self._parseEnum(enum)

        # loop over packages and types
        ndconverters = set()
        for ns in self.pkg.namespaces() :
            if isinstance(ns, Package) :
                print "Error: nested packages not supported:", ns
                continue
            if isinstance(ns, Type) :
                self._parseType(ns, ndconverters)

        # make the unversioned objects containing versioned types
        unmap = dict()
        for type in self.pkg.namespaces() :
            if isinstance(type, Type) and type.version is not None:
                vstr = "V"+str(type.version)
                if type.name.endswith(vstr):
                    unvtype = type.name[:-len(vstr)]
                    unmap.setdefault(unvtype, []).append(type.name)
        for unvtype, types in unmap.items():
            print >>self.cpp, T('  {\n    PyObject* unvlist = PyList_New($len);')(len=len(types))
            for i, type in enumerate(types):
                print >>self.cpp, T('    PyList_SET_ITEM(unvlist, $i, PyObject_GetAttrString(submodule, "$type"));')(locals())
            print >>self.cpp, T('    PyObject_SetAttrString(submodule, "$unvtype", unvlist);')(locals())
            print >>self.cpp, T('    Py_CLEAR(unvlist);\n  }')(locals())


        for type, ndim in ndconverters:
            if ndim > 0:
                print >>self.cpp, T('  detail::register_ndarray_to_numpy_cvt<const $type, $ndim>();')(locals())
            else:
                print >>self.cpp, T('  detail::register_ndarray_to_list_cvt<const $type>();')(locals())

        # end createWrappers()
        print >>self.cpp, ""
        print >>self.cpp, "} // createWrappers()"

        # close namespaces
        print >>self.cpp, T("} // namespace $name")[self.pkg]

    def _parseType(self, type, ndconverters):

        self._log.debug("_parseType: type=%s", repr(type))

        # skip included types
        if type.included : return

        self.codegen(type, ndconverters)

    def codegen(self, type, ndconverters):

        self._log.debug("codegen: type=%s", repr(type))
        #print "codegen: type=%s" % repr(type)

        # this class (class being generated)
        wrapped = type.fullName('C++', self.psana_ns)
        name = type.name + "_Wrapper"

        prefix = self.namespace_prefix()
        cname = type.name
        
        templ_args = [wrapped]
        if type.base:
            base = T('boost::python::bases<$base>')(base=type.base.fullName('C++', self.psana_ns))
            templ_args.append(base)
        if not type.value_type:
            holder = T('boost::shared_ptr<$wrapped>')(locals())
            templ_args += [holder, "boost::noncopyable"]
        templ_args = ', '.join(templ_args)
        
        pkgname = self.pkg.name

        has_nested_enums = len(type.enums()) > 0
        has_nested_constants = len(type.constants()) > 0
        if has_nested_enums or has_nested_constants:
            print >>self.cpp, '  {'
            print >>self.cpp, '  scope outer = '

        print >>self.cpp, T('  class_<$templ_args >("$cname", no_init)')(locals())

        # generate methods (for public methods and abstract class methods only)
        for method in type.methods(): 
            if type.value_type or method.access == "public": self._genMethod(type, method, wrapped, ndconverters)

        # generate _shape() methods for array attributes
        for attr in type.attributes() :
            self._genAttrShapeAndListDecl(type, attr, wrapped)

        # close class declaration
        print >>self.cpp, '  ;'

        # write any nested enums or nested constants
        if has_nested_enums:
            for enum in type.enums():
                self._parseEnum(enum)
        if has_nested_constants:
            print >>self.cpp
            for constant in type.constants():
                print >>self.cpp, T('  scope().attr("$name")=$value;')(name=constant.name,
                                                                      value=self.qualifiedConstantValue(constant))
        if has_nested_constants or has_nested_enums:
            print >>self.cpp, '  }'

        # generates converter instance
        type_id = "Pds::TypeId::"+type.type_id if type.type_id is not None else -1
        if type.value_type:
            cvt_type = T('ConverterBoostDef<$wrapped> ')(locals()) 
        else:
            cvt_type = T('ConverterBoostDefSharedPtr<$wrapped> ')(locals()) 
        print >>self.cpp, T('  ConverterMap::instance().addConverter(boost::make_shared<$cvt_type>($type_id));')(locals())
        print >>self.cpp, ""

    def _genMethod(self, type, method, bclass, ndconverters):
        """Generate method declaration and definition"""

        self._log.debug("_genMethod: method: %s", method)
        
        method_name = method.name
        policy = None
        args = method.args
        margs = ', '.join([_argdecl2(*arg) for arg in args])
        
        if method_name == '_sizeof': 
            # not needed in Python
            return
        
        # generate code for a method
        if method.type is None:
            
            # method which does not return anything
            pass

        elif not method.rank:
            
            # attribute is a regular non-array object, it is returned by value or cref
            # non-basic types are returned by cref from wrapped method if method has 
            # corresponding attribute
            if method.attribute:
                policy = None if method.type.basic else "return_value_policy<copy_const_reference>()"

        elif method.type.name == 'char':
            
            # char array is actually a string
            pass
            
        elif method.type.value_type and method.type.basic:
            
            # should also add boost converter for this ndarray type
            ctype = method.type.fullName('C++', self.psana_ns)
            if isinstance(method.type, Enum):
                ctype = method.type.base.fullName('C++', self.psana_ns)
            ndim = method.rank
            ndconverters.add((ctype, ndim))

        elif method.type.value_type:

            # wrapped method returns ndarray and we should convert it into regular Python list
            ctype = method.type.fullName('C++', self.psana_ns)
            ndconverters.add((ctype, -1))

        else:

            # array of non-value types, method will accept a set of indices.
            # wrapped method returns a const reference to an object wholly "contained" 
            # in the wrapped object, so set policy correctly. 
            policy = "return_internal_reference<>()"

        self._genMethodDef(type, bclass, method_name, policy=policy)


    def _genMethodDef(self, type, bclass, method_name, policy=''):

        policy = ', ' + policy if policy else ''

        print >>self.cpp, T('    .def("$method_name", &$bclass::$method_name$policy)')(locals())

    def isString(self, o):
        return type(o) == type("")

    def _genAttrShapeAndListDecl(self, type, attr, bclass):
        if not attr.shape_method: return
        if not attr.accessor: return
        
        # value-type arrays return ndarrays which do not need shape method
        if attr.type.value_type and attr.type.name != 'char': return

        # generate shape method
        shape_method = attr.shape_method
        print >>self.cpp, T('    .def("$shape_method", &method_shape<$bclass, &$bclass::$shape_method>)')(locals())

#
#  In case someone decides to run this module
#
if __name__ == "__main__" :

    # In principle we can try to run test suite for this module,
    # have to think about it later. Right now just abort.
    sys.exit ( "Module is not supposed to be run as main module" )
