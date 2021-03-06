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
from __future__ import print_function


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
import types

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
from psddl.JinjaEnvironment import getJinjaEnvironment

#----------------------------------
# Local non-exported definitions --
#----------------------------------

# jinja environment
_jenv = getJinjaEnvironment()

def _TEMPL(template):
    return _jenv.get_template('cppcodegen.tmpl?'+template)

#------------------------
# Exported definitions --
#------------------------

#---------------------
#  Class definition --
#---------------------
class DdlPsanaInterfaces ( object ) :

    @staticmethod
    def backendOptions():
        """ Returns the list of options supported by this backend, returned value is 
        either None or a list of triplets (name, type, description)"""
        return None

    #----------------
    #  Constructor --
    #----------------
    def __init__ ( self, backend_options, log ) :
        '''Constructor
        
           @param backend_options  dictionary of options passed to backend
           @param log              message logger instance
        '''
        self.incname = backend_options['global:header']
        self.cppname = backend_options['global:source']
        self.incdirname = backend_options.get('global:gen-incdir', "")
        self.top_pkg = backend_options.get('global:top-package')

        self._log = log

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
        print("#ifndef", self.guard, file=self.inc) 
        print("#define", self.guard, "1", file=self.inc)

        msg = "\n// *** Do not edit this file, it is auto-generated ***\n"
        print(msg, file=self.inc)
        print(msg, file=self.cpp)

        # add necessary includes
        print("#include <vector>", file=self.inc)
        print("#include <iosfwd>", file=self.inc)
        print("#include <cstddef>", file=self.cpp)
        print("#include <cstring>", file=self.inc)

        print("#include \"ndarray/ndarray.h\"", file=self.inc)
        print("#include \"pdsdata/xtc/TypeId.hh\"", file=self.inc)
        inc = os.path.join(self.incdirname, os.path.basename(self.incname))
        print("#include \"%s\"" % inc, file=self.cpp)
        print("#include <iostream>", file=self.cpp)

#        import IPython
#        IPython.embed()
#        1/0

        # headers for other included packages
        for use in model.use:
            path = use['file']
            headers = use['cpp_headers']
            if not headers:
                header = os.path.splitext(path)[0]
                if not header.endswith('.ddl'): header += '.ddl'
                header = header + '.h'
                header = os.path.join(self.incdirname, os.path.basename(header))
                headers = [header]
            for header in headers:
                print("#include \"%s\"" % header, file=self.inc)

        if self.top_pkg : 
            print(T("namespace $top_pkg {")[self], file=self.inc)
            print(T("namespace $top_pkg {")[self], file=self.cpp)

        # enums for constants
        for const in model.constants() :
            if not const.included :
                self._genConst(const)

        # regular enums
        for enum in model.enums() :
            if not enum.included :
                self._genEnum(enum)

        # loop over packages and types in the model
        for ns in model.namespaces() :
            if isinstance(ns, Package) :
                if not ns.included :
                    self._parsePackage(ns)
            elif isinstance(ns, Type) :
                if not ns.external:
                    self._parseType(type = ns)

        if self.top_pkg : 
            print(T("} // namespace $top_pkg")[self], file=self.inc)
            print(T("} // namespace $top_pkg")[self], file=self.cpp)

        # close include guard
        print("#endif //", self.guard, file=self.inc)

        # close all files
        self.inc.close()
        self.cpp.close()


    def _parsePackage(self, pkg):

        # open namespaces
        print(T("namespace $name {")[pkg], file=self.inc)
        print(T("namespace $name {")[pkg], file=self.cpp)

        # enums for constants
        for const in pkg.constants() :
            if not const.included :
                self._genConst(const)

        # regular enums
        for enum in pkg.enums() :
            if not enum.included :
                self._genEnum(enum)

        # loop over packages and types
        for ns in pkg.namespaces() :
            
            if isinstance(ns, Package) :
                
                self._parsePackage(ns)
            
            elif isinstance(ns, Type) :
    
                self._parseType(type = ns)

        # close namespaces
        print(T("} // namespace $name")[pkg], file=self.inc)
        print(T("} // namespace $name")[pkg], file=self.cpp)

    def _parseType(self, type):

        self._log.debug("_parseType: type=%s", repr(type))

        # skip included types
        if type.included : return

        # type is abstract by default but can be reset with tag "value-type"
        abstract = not type.value_type

        codegen = CppTypeCodegen(self.inc, self.cpp, type, abstract)
        codegen.codegen()

    def _genConst(self, const):
        
        print(T("  enum {\n    $name = $value /**< $comment */\n  };")[const], file=self.inc)

    def _genEnum(self, enum):
        
        if enum.comment: print(T("\n  /** $comment */")[enum], file=self.inc)
        print(T("  enum $name {")(name = enum.name or ""), file=self.inc)
        for const in enum.constants() :
            val = ""
            if const.value is not None : val = " = " + str(const.value)
            doc = ""
            if const.comment: doc = T(' /**< $comment */')[const]
            print(T("    $name$value,$doc")(name=const.name, value=val, doc=doc), file=self.inc)
        print("  };", file=self.inc)

        if enum.name:
            print(_TEMPL('enum_print_decl').render(locals()), file=self.inc)
            print(_TEMPL('enum_print_impl').render(locals()), file=self.cpp)


#
#  In case someone decides to run this module
#
if __name__ == "__main__" :

    # In principle we can try to run test suite for this module,
    # have to think about it later. Right now just abort.
    sys.exit ( "Module is not supposed to be run as main module" )
