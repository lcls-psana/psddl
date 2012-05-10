#--------------------------------------------------------------------------
# File and Version Information:
#  $Id$
#
# Description:
#  Module DdlPsanaInterfaces...
#
#------------------------------------------------------------------------

"""DDL parser which generates psana C++ interfaces.

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
import os
import logging
import types
import string

#---------------------------------
#  Imports of base class module --
#---------------------------------

#-----------------------------
# Imports for other modules --
#-----------------------------
from psddl.CppTypeCodegen import CppTypeCodegen
from psddl.Package import Package
from psddl.Type import Type
from psddl.Template import Template as T

#----------------------------------
# Local non-exported definitions --
#----------------------------------

#------------------------
# Exported definitions --
#------------------------

#---------------------
#  Class definition --
#---------------------
class DdlPsanaInterfaces ( object ) :

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
        self.wrapper = not not backend_options.get('pywrapper')

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

        # include guard to header
        print >>self.inc, "#ifndef", self.guard 
        print >>self.inc, "#define", self.guard, "1"

        msg = "\n// *** Do not edit this file, it is auto-generated ***\n"
        print >>self.inc, msg
        print >>self.cpp, msg

        # add necessary includes
        print >>self.inc, "#include <vector>"
        print >>self.cpp, "#include <cstddef>"

        print >>self.inc, "#include \"ndarray/ndarray.h\""
        print >>self.inc, "#include \"pdsdata/xtc/TypeId.hh\""
        inc = os.path.join(self.incdirname, os.path.basename(self.incname))

        if not self.wrapper:
            print >>self.cpp, "#include \"%s\"" % inc
        else:
            inc_no_wrapper = string.replace(self.incname, ".wrapper", "")
            print >>self.cpp, "#include <boost/python/class.hpp>"
            print >>self.cpp, "#include \"psddl_psana/%s\"" % inc_no_wrapper
            print >>self.cpp, "#include \"psana/%s\"" % inc
            print >>self.cpp, ""

            print >>self.inc, "#include <boost/python.hpp>"
            print >>self.inc, "#include <numpy/arrayobject.h>"
            print >>self.inc, ""
            print >>self.inc, "namespace psana {"
            print >>self.inc, "  extern PyObject* ndConvert(void* data, const unsigned* shape, const unsigned ndim, char* ctype);"
            print >>self.inc, "}"
            print >>self.inc, "#ifndef ND_CONVERT"
            print >>self.inc, "#define ND_CONVERT(value, ctype, ndim) const ndarray<ctype, ndim>& a = value; return psana::ndConvert((void *) a.data(), a.shape(), ndim, #ctype)"
            print >>self.inc, "#endif"
            print >>self.inc, ""

        # headers for other included packages
        for use in model.use:
            path = use['file']
            headers = use['cpp_headers']
            if not headers:
                header = os.path.splitext(path)[0] + '.h'
                header = os.path.join(self.incdirname, os.path.basename(header))
                headers = [header]
            for header in headers:
                print >>self.inc, "#include \"%s\"" % header

        if self.top_pkg : 
            print >>self.inc, T("namespace $top_pkg {")[self]
            print >>self.cpp, T("namespace $top_pkg {")[self]

        if self.wrapper:
            """
            print >>self.inc, ''
            print >>self.inc, '#ifndef EVT_AND_ENV_GETTER'
            print >>self.inc, '#define EVT_AND_ENV_GETTER 1'
            print >>self.inc, 'class EvtGetter {'
            print >>self.inc, 'public:'
            print >>self.inc, 'virtual string getTypeName() = 0;'
            print >>self.inc, 'virtual object get(Event& evt, Source& src) = 0;'
            print >>self.inc, 'virtual ~EvtGetter() {}'
            print >>self.inc, '};'
            print >>self.inc, ''
            print >>self.inc, 'class EnvGetter {'
            print >>self.inc, 'public:'
            print >>self.inc, 'virtual string getTypeName() = 0;'
            print >>self.inc, 'virtual object get(EnvWrapper& env, Source& src) = 0;'
            print >>self.inc, 'virtual ~EnvGetter() {}'
            print >>self.inc, '};'
            print >>self.inc, '#endif // EVT_AND_ENV_GETTER'
            print >>self.inc, ''
            """
            pass

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


    def _parsePackage(self, pkg):

        # open namespaces
        print >>self.inc, T("namespace $name {")[pkg]
        print >>self.cpp, T("namespace $name {")[pkg]

        if not self.wrapper:
            # enums for constants
            for const in pkg.constants() :
                if not const.included :
                    self._genConst(const)

            # regular enums
            for enum in pkg.enums() :
                if not enum.included :
                    self._genEnum(enum)
        else:
            print >>self.inc, "\nextern void createWrappers();\n"
            print >>self.cpp, "using namespace boost::python;\n"
            print >>self.cpp, "void createWrappers() {"

        # loop over packages and types
        for ns in pkg.namespaces() :
            
            if isinstance(ns, Package) :
                
                self._parsePackage(ns)
            
            elif isinstance(ns, Type) :
    
                if not self.wrapper:
                    self._parseType(type = ns)
                else:
                    namespace_prefix = pkg.name + "::"
                    if self.top_pkg : 
                        namespace_prefix = self.top_pkg + "::" + namespace_prefix
                    self._parseType(type = ns, namespace_prefix = namespace_prefix)

        if self.wrapper:
            # end createWrappers()
            print >>self.cpp, "}"
            # now create EventGetter and EnvironmentGetter classes
            for ns in pkg.namespaces() :
                if isinstance(ns, Type) :
                    namespace_prefix = pkg.name + "::"
                    if self.top_pkg : 
                        namespace_prefix = self.top_pkg + "::" + namespace_prefix
                    self._parseType2(type = ns, namespace_prefix = namespace_prefix)

        # close namespaces
        print >>self.inc, T("} // namespace $name")[pkg]
        print >>self.cpp, T("} // namespace $name")[pkg]

    def _parseType(self, type, namespace_prefix = ""):

        logging.debug("_parseType: type=%s", repr(type))

        # skip included types
        if type.included : return

        # type is abstract by default but can be reset with tag "value-type"
        abstract = not type.value_type
        codegen = CppTypeCodegen(self.inc, self.cpp, type, abstract, self.wrapper, namespace_prefix)
        codegen.codegen()

    def _parseType2(self, type, namespace_prefix = ""):
        type_name = type.name
        if type_name.find('DataV') == 0 or type_name.find('DataDescV') == 0:
            print >>self.inc, "  // XXX should create EvtGetter for %s" % type_name
        elif type_name.find('ConfigV') == 0:
            print >>self.inc, "  // XXX should create EnvGetter for %s" % type_name

    def _genConst(self, const):
        
        print >>self.inc, T("  enum {\n    $name = $value /**< $comment */\n  };")[const]

    def _genEnum(self, enum):
        
        if enum.comment: print >>self.inc, T("\n  /** $comment */")[enum]
        print >>self.inc, T("  enum $name {")(name = enum.name or "")
        for const in enum.constants() :
            val = ""
            if const.value is not None : val = " = " + const.value
            doc = ""
            if const.comment: doc = T(' /**< $comment */')[const]
            print >>self.inc, T("    $name$value,$doc")(name=const.name, value=val, doc=doc)
        print >>self.inc, "  };"


#
#  In case someone decides to run this module
#
if __name__ == "__main__" :

    # In principle we can try to run test suite for this module,
    # have to think about it later. Right now just abort.
    sys.exit ( "Module is not supposed to be run as main module" )
