#--------------------------------------------------------------------------
# File and Version Information:
#  $Id$
#
# Description:
#  Module DdlHdf5Data...
#
#------------------------------------------------------------------------

"""DDL parser which generates C++ code for HDF5 data classes.

This software was developed for the SIT project.  If you use all or 
part of it, please give an appropriate acknowledgment.

@see RelatedModule

@version $Id$

@author Andy Salnikov
"""


#------------------------------
#  Module's version from CVS --
#------------------------------
__version__ = "$Revision$"

#--------------------------------
#  Imports of standard modules --
#--------------------------------
import sys
import os
import logging

#---------------------------------
#  Imports of base class module --
#---------------------------------

#-----------------------------
# Imports for other modules --
#-----------------------------
from psddl.Attribute import Attribute
from psddl.Enum import Enum
from psddl.Package import Package
from psddl.Type import Type

#----------------------------------
# Local non-exported definitions --
#----------------------------------

#------------------------
# Exported definitions --
#------------------------

#---------------------
#  Class definition --
#---------------------
class DdlHdf5Data ( object ) :

    #----------------
    #  Constructor --
    #----------------
    def __init__(self, incname, cppname, backend_options):
        """Constructor
        
            @param incname  include file name
            @param cppname  source file name
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

    def parseTree(self, model):
        
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
        print >>self.inc, "#include \"pdsdata/xtc/TypeId.hh\""
        print >>self.inc, "#include <vector>"
        print >>self.inc, "#include <cstddef>\n"

        inc = os.path.join(self.incdirname, os.path.basename(self.incname))
        print >>self.cpp, "#include \"%s\"\n" % inc

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
            ns = "namespace %s {" % self.top_pkg
            print >>self.inc, ns
            print >>self.cpp, ns

        # loop over packages in the model
        for pkg in model.packages() :
            logging.debug("parseTree: package=%s", repr(pkg))
            self._parsePackage(pkg)

        if self.top_pkg : 
            ns = "} // namespace %s" % self.top_pkg
            print >>self.inc, ns
            print >>self.cpp, ns

        # close include guard
        print >>self.inc, "#endif //", self.guard

        # close all files
        self.inc.close()
        self.cpp.close()


    def _parsePackage(self, pkg):
        
        if pkg.included: return

        # open namespaces
        print >>self.inc, "namespace %s {" % pkg.name
        print >>self.cpp, "namespace %s {" % pkg.name

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
        print >>self.inc, "} // namespace %s" % pkg.name
        print >>self.cpp, "} // namespace %s" % pkg.name


    def _genConst(self, const):
        
        print >>self._inc, "  enum {\n    %s = %s /**< %s */\n  };" % \
                (const.name, const.value, const.comment)

    def _genEnum(self, enum):
        
        if enum.comment: print >>self.inc, "\n  /** %s */" % (enum.comment)
        print >>self.inc, "  enum %s {" % (enum.name or "",)
        for const in enum.constants() :
            val = ""
            if const.value is not None : val = " = " + const.value
            doc = ""
            if const.comment: doc = ' /**< %s */' % const.comment
            print >>self.inc, "    %s%s,%s" % (const.name, val, doc)
        print >>self.inc, "  };"

    def _parseType(self, type):

        logging.debug("_parseType: type=%s", repr(type))

        # skip included types
        if type.included : return

        for schema in type.h5schemas:
            self._genSchema(type, schema)


    def _genSchema(self, type, schema):

        # find schema version
        schemaVersion = 1
        if schema: schemaVersion = schema.version
            
        className = "%s_s%s" % (type.name, schemaVersion)
            
        # class-level comment
        print >>self.inc, "\n/** @class %s\n\n  %s\n*/\n" % (className, type.comment)

        # declare config classes if needed
        for cfg in type.xtcConfig:
            print >>self.inc, "class %s;" % cfg.name

        # base class
        base = ""
        if type.base : base = ": public %s" % type.base.name


        # start class declaration
        print >>self.inc, "\nclass %s%s {" % (type.name, base)
        print >>self.inc, "public:"

        # enums for version and typeId
        if type.version is not None: 
            doc = '/**< XTC type version number */'
            print >>self.inc, "  enum {\n    Version = %s %s\n  };" % (type.version, doc)
        if type.type_id is not None: 
            doc = '/**< XTC type ID value (from Pds::TypeId class) */'
            print >>self.inc, "  enum {\n    TypeId = Pds::TypeId::%s %s\n  };" % (type.type_id, doc)

        # enums for constants
        for const in type.constants() :
            self._genConst(const)

        # regular enums
        for enum in type.enums() :
            self._genEnum(enum)

        # generate method declaration for public members without accessors
        for attr in type.attributes() :
            if attr.access == "public" and attr.accessor is None:
                self._genPubAttrMethod(attr)

        # generate declaration for public methods only
        pub_meth = [meth for meth in type.methods() if meth.access == "public"]
        for meth in pub_meth: 
            self._genMethDecl(meth)

        # generate _shape() methods for array attributes
        for attr in type.attributes() :
            self._genAttrShapeDecl(attr)

        # data members
        for attr in type.attributes() :
            self._genAttrDecl(attr)

        # close class declaration
        print >>self.inc, "};"

    #--------------------
    #  Private methods --
    #--------------------

#
#  In case someone decides to run this module
#
if __name__ == "__main__" :

    # In principle we can try to run test suite for this module,
    # have to think about it later. Right now just abort.
    sys.exit ( "Module is not supposed to be run as main module" )
