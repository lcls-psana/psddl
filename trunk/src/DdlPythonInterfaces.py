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
import logging
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
from psddl.Type import Type

#----------------------------------
# Local non-exported definitions --
#----------------------------------

def _interpolate(expr, typeobj):
    expr = expr.replace('{xtc-config}', 'cfg')
    expr = expr.replace('{type}.', typeobj.name+"::")
    expr = expr.replace('{self}.', "this->")
    return expr

def _typename(type):
    return type.fullName('C++')

def _typedecl(type):
    typename = _typename(type)
    if not type.basic : typename = "const "+typename+'&'
    return typename

def _argdecl(name, type):    
    return _typedecl(type) + ' ' + name

def _argdecl2(name, type):    
    return name

def _dims(dims):
    return ''.join(['[%s]'%d for d in dims])

def _dimargs(dims, type):
    int_type = type.lookup('uint32_t')
    return [('i%d'%i, int_type) for i in range(len(dims))]

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
    def __init__ ( self, incname, cppname, backend_options ) :
        """Constructor
        
            @param incname  include file name
        """
        self.incname = incname
        self.cppname = cppname
        self.incdirname = backend_options.get('gen-incdir', "")
        self.top_pkg = backend_options.get('top-package')

        #include guard
        g = os.path.split(self.incname)[1]
        if self.top_pkg: g = self.top_pkg + '_' + g
        self.guard = g.replace('.', '_').upper()

    #-------------------
    #  Public methods --
    #-------------------

    def parseTree ( self, model ) :
        
        # open output files
        self.inc = file(self.incname, 'w')
        self.cpp = file(self.cppname, 'w')

        warning = "/* Do not edit this file, as it is auto-generated */\n"
        print >>self.inc, warning
        print >>self.cpp, warning

        # include guard to header
        print >>self.inc, "#ifndef", self.guard 
        print >>self.inc, "#define", self.guard, "1"
        print >>self.inc, ""

        inc = os.path.join(self.incdirname, os.path.basename(self.incname))
        inc_base = self.incname
        index = inc_base.rfind("/")
        if index != -1:
            inc_base = inc_base[index+1:]
            print inc_base

        # add necessary includes to include file
        print >>self.inc, "#include <vector>"
        print >>self.inc, "#include <ndarray/ndarray.h>"
        print >>self.inc, "#include <pdsdata/xtc/TypeId.hh>"
        print >>self.inc, "#include <psddl_python/DdlWrapper.h>"
        print >>self.inc, ""

        # add necessary includes to source file
        print >>self.cpp, "#include <cstddef>"
        inc_psana = "psddl_psana/" + string.replace(inc_base, ".wrapper", "")
        inc_python = "psddl_python/" + inc_base
        print >>self.cpp, "#include <%s> // inc_psana" % inc_psana
        print >>self.cpp, "#include <%s> // inc_python" % inc_python
        print >>self.cpp, ""

        # headers for other included packages
        for use in model.use:
            path = use['file']
            headers = use['cpp_headers']
            if not headers:
                header = os.path.splitext(path)[0] + '.h'
                header = os.path.join(self.incdirname, os.path.basename(header))
                headers = [header]
            for header in headers:
                if "/" in header:
                    print >>self.inc, "#include <%s> // other included packages" % header
                else:
                    print >>self.inc, "#include <psddl_psana/%s> // other included packages" % header

        if self.top_pkg : 
            print >>self.cpp, T("namespace $top_pkg {")[self]
            print >>self.inc, T("namespace $top_pkg {")[self]

        # loop over packages in the model
        for pkg in model.packages() :
            if not pkg.included :
                logging.debug("parseTree: package=%s", repr(pkg))
                self._parsePackage(pkg)

        if self.top_pkg : 
            print >>self.inc, T("} // namespace $top_pkg")[self]
            print >>self.cpp, T("} // namespace $top_pkg")[self]

        # close include guard
        print >>self.inc, "#endif //", self.guard

        # close all files
        self.inc.close()
        self.cpp.close()

    def namespace_prefix(self):
        prefix = self.pkg.name + "::"
        if self.top_pkg: prefix = self.top_pkg + "::" + prefix
        return prefix

    def _parsePackage(self, pkgX):
        self.pkg = pkgX

        # open namespaces
        print >>self.inc, T("namespace $name {")[self.pkg]
        print >>self.inc, ""
        print >>self.inc, "using namespace boost::python;"
        print >>self.inc, "using boost::python::api::object;"
        print >>self.inc, "using boost::shared_ptr;"
        print >>self.inc, "using std::vector;"
        print >>self.inc, ""
        print >>self.inc, "extern void createWrappers();"

        print >>self.cpp, T("namespace $name {")[self.pkg]
        print >>self.cpp, ""
        print >>self.cpp, "void createWrappers() {"

        # loop over packages and types
        for ns in self.pkg.namespaces() :
            if isinstance(ns, Package) :
                print "Error: nested packages not supported:", ns
                continue
            if isinstance(ns, Type) :
                self._parseType(type = ns)

        # end createWrappers()
        print >>self.cpp, ""
        print >>self.cpp, "} // createWrappers()"
        # now create EventGetter and EnvironmentGetter classes
        for ns in self.pkg.namespaces() :
            if isinstance(ns, Type) :
                self._createGetterClass(type = ns)

        # close namespaces
        print >>self.inc, T("} // namespace $name")[self.pkg]
        print >>self.cpp, T("} // namespace $name")[self.pkg]

    def _parseType(self, type):

        logging.debug("_parseType: type=%s", repr(type))

        # skip included types
        if type.included : return

        self.codegen(type)

    def _getGetterClassForType(self, type):
        if re.match(r'.*(Data|DataDesc|Element)[A-Za-z]*V[1-9][0-9]*', type.name):
            return "Psana::EventGetter"
        elif re.match(r'.*(Config)[A-Za-z]*V[1-9][0-9]*', type.name):
            return "Psana::EnvGetter"
        else:
            # Guess what type of Getter to use
            return "Psana::EventGetter";

    def _createGetterClass(self, type):
        getter_class = self._getGetterClassForType(type)
        if not getter_class:
            return
        type_name = type.name
        namespace_prefix = self.namespace_prefix()
        print >>self.inc, ''
        print >> self.inc, T('  class ${type_name}_Getter : public ${getter_class} {')(locals())
        print >> self.inc, '  public:'
        print >> self.inc, T('  const char* getTypeName() { return "${namespace_prefix}${type_name}";}')(locals())
        print >> self.inc, T('  const char* getGetterClassName() { return "${getter_class}";}')(locals())
        if type.version is not None:
            print >> self.inc, '    int getVersion() {'
            print >> self.inc, T('      return ${type_name}::Version;')(locals())
            print >> self.inc, '    }'
        if getter_class == "Psana::EventGetter":
            print >> self.inc, T('    object get(PSEvt::Event& evt, PSEvt::Source& source, const std::string& key, Pds::Src* foundSrc) {')(locals())
            print >> self.inc, T('      shared_ptr<$type_name> result = evt.get(source, key, foundSrc);')(locals())
            print >> self.inc, T('      return result.get() ? object(${type_name}_Wrapper(result)) : object();')(locals())
            print >> self.inc, '    }'
        elif getter_class == "Psana::EnvGetter":
            print >> self.inc, T('    object get(PSEnv::EnvObjectStore& store, const PSEvt::Source& source, Pds::Src* foundSrc) {')(locals())
            print >> self.inc, T('      boost::shared_ptr<$type_name> result = store.get(source, foundSrc);')(locals())
            print >> self.inc, T('      return result.get() ? object(${type_name}_Wrapper(result)) : object();')(locals())
            print >> self.inc, '    }'
        print >> self.inc, '  };'

    def codegen(self, type):
        # type is abstract by default but can be reset with tag "value-type"
        abstract = not type.value_type

        self._type = type
        self._pkg_name = self.pkg.name

        logging.debug("codegen: type=%s", repr(type))
        #print "codegen: type=%s" % repr(type)

        # declare config classes if needed
        for cfg in type.xtcConfig:
            print >>self.inc, T("class $name;")[cfg]

        # base class
        base = ""

        # this class (class being generated)
        wrapped = type.name
        name = wrapped + "_Wrapper"

        # start class declaration
        print >>self.inc, T("\nclass $name$base {")(name = name, base = base)
        access = "private"

        # shared_ptr and C++ pointer to wrapped object
        print >>self.inc, T("  shared_ptr<$wrapped> _o;")(wrapped = wrapped)
        print >>self.inc, T("  $wrapped* o;")(wrapped = wrapped)

        # enums for version and typeId
        access = self._access("public", access)
        if type.type_id is not None: 
            print >>self.inc, T("  enum { TypeId = Pds::TypeId::$type_id };")(type_id=type.type_id)
        if type.version is not None: 
            print >>self.inc, T("  enum { Version = $version };")(version=type.version)

        # constructor
        access = self._access("public", access)
        print >>self.inc, T("  $name(shared_ptr<$wrapped> obj) : _o(obj), o(_o.get()) {}")(locals())
        print >>self.inc, T("  $name($wrapped* obj) : o(obj) {}")(locals())
        print >>self.cpp, T("\n#define _CLASS(n, policy) class_<n>(#n, no_init)\\")(locals())

        # generate methods (for public methods and abstract class methods only)
        for method in type.methods(): 
            access = self._access("public", access)
            if not abstract or method.access == "public": self._genMethod(type, method)

        # generate _shape() methods for array attributes
        for attr in type.attributes() :
            access = self._access("public", access)
            self._genAttrShapeAndListDecl(type, attr)

        # close class declaration
        print >>self.inc, "};"
        prefix = self.namespace_prefix()

        # export classes to Python via boost _class
        print >>self.cpp, ""
        if not abstract:
            print >>self.cpp, T('  _CLASS($prefix$wrapped, return_value_policy<copy_const_reference>());')(locals())
        print >>self.cpp, T('  _CLASS($prefix$name, return_value_policy<return_by_value>());')(locals())
        if not abstract:
            print >>self.cpp, T('  std_vector_class_($wrapped);')(locals())
        print >>self.cpp, T('  std_vector_class_($name);')(locals())
        print >>self.cpp, '#undef _CLASS';

        getter_class = self._getGetterClassForType(type)
        if getter_class == "Psana::EventGetter":
            print >>self.cpp, T('  ADD_EVENT_GETTER($wrapped);')(locals())
        elif getter_class == "Psana::EnvGetter":
            print >>self.cpp, T('  ADD_ENV_GETTER($wrapped);')(locals())
        print >>self.cpp, ""

    def _access(self, newaccess, oldaccess):
        if newaccess != oldaccess:
            print >>self.inc, newaccess+":"
        return newaccess
        
    def _genAttrDecl(self, attr):
        """Generate attribute declaration"""
        
        logging.debug("_genAttrDecl: attr: %s", attr)
        
        doc = ""
        if attr.comment : doc = T("\t/**< $comment */")(comment = attr.comment.strip())
        
        if not attr.shape :
            if attr.isfixed():
                decl = T("  $type\t$name;$doc")(type=_typename(attr.type), name=attr.name, doc=doc)
            else:
                decl = T("  //$type\t$name;")(type=_typename(attr.type), name=attr.name)
        else:
            if attr.isfixed():
                dim = _interpolate(_dims(attr.shape.dims), attr.parent)
                decl = T("  $type\t$name$shape;$doc")(type=_typename(attr.type), name=attr.name, shape=dim, doc=doc)
            else :
                dim = _interpolate(_dims(attr.shape.dims), attr.parent)
                decl = T("  //$type\t$name$shape;")(type=_typename(attr.type), name=attr.name, shape=dim)
        print >>self.inc, decl


    def _genMethod(self, type, method):
        """Generate method declaration and definition"""

        logging.debug("_genMethod: method: %s", method)
        
        if method.attribute:
            
            # generate access method for a named attribute
            
            attr = method.attribute
            args = []
                        
            if not attr.shape:
                
                # attribute is a regular non-array object, 
                # return value or reference depending on what type it is
                rettype = _typedecl(attr.type)

            elif attr.type.name == 'char':
                
                # char array is actually a string
                rettype = "const char*"
                args = _dimargs(attr.shape.dims[:-1], type)
                
            elif attr.type.value_type :
                
                # return ndarray
                rettype = "ndarray<%s, %d>" % (_typename(attr.type), len(attr.shape.dims))

            else:

                # array of any other types
                rettype = _typedecl(attr.type)
                args = _dimargs(attr.shape.dims, type)

            # guess if we need to pass cfg object to method
            cfgNeeded = False

            configs = [None]
            if cfgNeeded and not abstract: configs = attr.parent.xtcConfig
            for cfg in configs:

                cargs = []
                if cfg: cargs = [('cfg', cfg)]

                self._genMethodBody(type, method.name, rettype, cargs + args)

        elif method.bitfield:

            # generate access method for bitfield

            bf = method.bitfield
            expr = bf.expr()
            cfgNeeded = expr.find('{xtc-config}') >= 0
            expr = _interpolate(expr, method.parent)

            configs = [None]
            if cfgNeeded and not abstract: configs = method.parent.xtcConfig
            for cfg in configs:

                args = []
                if cfg: args = [('cfg', cfg)]

                self._genMethodBody(type, method.name, _typename(method.type), args=[])

        else:

            # explicitly declared method with optional expression
            
            abstract = not type.value_type
            if method.name == "_sizeof" and abstract : return
            
            # if no type given then it does not return anything
            method_type = method.type
            if method_type is None:
                method_type = "void"
            else:
                method_type = _typename(method_type)
                if method.rank > 0:
                    method_type = "ndarray<%s, %d>" % (method_type, method.rank)

            # config objects may be needed 
            cfgNeeded = False

            configs = [None]
            if cfgNeeded and not abstract: configs = method.parent.xtcConfig
            for cfg in configs:

                args = []
                if cfg: args = [('cfg', cfg)]
                args += method.args

                self._genMethodBody(type, method.name, method_type, args)

    def _genMethodBody(self, type, method_name, rettype, args=[]):
        """ Generate method, both declaration and definition, given the body of the method"""

        # make argument list
        argsspec = ', '.join([_argdecl(*arg) for arg in args])

        policy = ""
        args = ', '.join([_argdecl2(*arg) for arg in args])
        index = rettype.find("ndarray<")
        if index == 0:
            ctype_ndim = rettype[8:]
            index = ctype_ndim.rfind(">")
            if index != -1:
                ctype_ndim = ctype_ndim[:index]
            index = ctype_ndim.find(", ")
            ctype = ctype_ndim[:index]
            ndim = int(ctype_ndim[index + 2:])
            if ndim == 1 or "::" in ctype:
                if ndim > 1:
                    print "WARNING: cannot generate ndarray<%s, %d>, so generating one-dimensional vector<%s> instead" % (ctype, ndim, ctype)
                print >>self.inc, T("  vector<$ctype> $method_name($argsspec) const { VEC_CONVERT(o->$method_name($args), $ctype); }")(locals())
            else:
                print >>self.inc, T("  PyObject* $method_name($argsspec) const { ND_CONVERT(o->$method_name($args), $ctype, $ndim); }")(locals())
        elif "&" in rettype and "::" in rettype:
            if (self._pkg_name + "::") in rettype:
                method_type = rettype.replace("&", "").replace("const ", "")
                index = method_type.find("::")
                if index != -1:
                    method_type = method_type[2+index:] # remove "Namespace::"
                wrappertype = method_type + "_Wrapper"
                print >>self.inc, T("  const $wrappertype $method_name($argsspec) const { return $wrappertype(($method_type*) &o->$method_name($args)); }")(locals())
                policy = ", policy"
            else:
                method_type = rettype
                print >>self.inc, T("  $method_type $method_name($argsspec) const { return o->$method_name($args); }")(locals())
                policy = ", policy"
        else:
            print >>self.inc, T("  $rettype $method_name($argsspec) const { return o->$method_name($args); }")(locals())

        print >>self.cpp, T("    .def(\"$method_name\", &n::$method_name$policy)\\")(method_name=method_name, classname=type.name, policy=policy)

    def isString(self, o):
        return type(o) == type("")

    def _genAttrShapeAndListDecl(self, type, attr):
        if not attr.shape_method: return
        if not attr.accessor: return
        
        # value-type arrays return ndarrays which do not need shape method
        if attr.type.value_type and attr.type.name != 'char': return

        dimensions = []
        for dim in attr.shape.dims:
            if self.isString(dim) and (('{xtc-config}' in dim) or ('{self}' in dim)):
                dimensions.append(dim)

        self._genMethodBody(type, attr.shape_method, "vector<int>")

        if len(dimensions) == 0:
            return
        if len(dimensions) > 2:
            print "Error: cannot generate '%s' method: shape has more than 2 dimensions." % shape_method
            sys.exit(1)

        # now generate data_list() method if applicable.
        shape_method = attr.shape_method
        method_name = attr.accessor.name
        list_method_name = method_name + "_list"
        print >> self.inc, T("  boost::python::list ${list_method_name}() { boost::python::list l; const int n = ${shape_method}()[0]; for (int i = 0; i < n; i++) l.append(${method_name}(i)); return l; }")(locals())
        print >>self.cpp, T("    .def(\"$list_method_name\", &n::$list_method_name)\\")(locals())

#
#  In case someone decides to run this module
#
if __name__ == "__main__" :

    # In principle we can try to run test suite for this module,
    # have to think about it later. Right now just abort.
    sys.exit ( "Module is not supposed to be run as main module" )
