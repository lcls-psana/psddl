#--------------------------------------------------------------------------
# File and Version Information:
#  $Id$
#
# Description:
#  Module DdlHdf5Data...
#
#------------------------------------------------------------------------

"""Backend for psddlc which generates C++ code for HDF5 I/O.

Backend-specific options:

  gen-incdir - specifies directory name for generated header files, default is empty 
  top-package - specifies top-level namespace for the generated code, default is no top-level namespace
  psana-inc - specifies include directory for psana header files
  psana-ns - specifies top-level namespace for Psana interfaces
  dump-schema - if present the auto-generated schemas will be dumped, no code generation

This software was developed for the LCLS project.  If you use all or 
part of it, please give an appropriate acknowledgment.

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

#---------------------------------
#  Imports of base class module --
#---------------------------------

#-----------------------------
# Imports for other modules --
#-----------------------------
import jinja2 as ji
from psddl.Attribute import Attribute
from psddl.Enum import Enum
from psddl.Package import Package
from psddl.Type import Type
from psddl.H5Type import H5Type
from psddl.H5Dataset import H5Dataset
from psddl.H5Attribute import H5Attribute
from psddl.Template import Template as T
from psddl.TemplateLoader import TemplateLoader
from psddl import DdlHdf5DataHelpers as Helpers

#----------------------------------
# Local non-exported definitions --
#----------------------------------

# jinja environment
_jenv = ji.Environment(loader=TemplateLoader(), trim_blocks=True,
                       line_statement_prefix='$', line_comment_prefix='$$')

def _TEMPL(template):
    return _jenv.get_template('hdf5.tmpl?'+template)

def _schemas(pkg):
    '''generator function for all schemas inside a package'''
    for ns in pkg.namespaces() :
        if isinstance(ns, Package) :
            for schema in _schemas(ns): yield schema        
        elif isinstance(ns, Type) :
            for schema in ns.h5schemas: yield schema

#------------------------
# Exported definitions --
#------------------------

#---------------------
#  Class definition --
#---------------------
class DdlHdf5Data ( object ) :

    @staticmethod
    def backendOptions():
        """ Returns the list of options supported by this backend, returned value is 
        either None or a list of triplets (name, type, description)"""
        return [
            ('psana-inc', 'PATH', "directory for Psana includes, default: psddl_psana"),
            ('psana-ns', 'STRING', "namespace for Psana types, default: Psana"),
            ('dump-schema', '', "if specified then only dump schema in XML format, including default schema"),
            ]


    #----------------
    #  Constructor --
    #----------------
    def __init__(self, backend_options, log):
        '''Constructor
        
           @param backend_options  dictionary of options passed to backend
           @param log              message logger instance
        '''
        self.incname = backend_options['global:header']
        self.cppname = backend_options['global:source']
        self.incdirname = backend_options.get('global:gen-incdir', "")
        self.top_pkg = backend_options.get('global:top-package')
        
        self.psana_inc = backend_options.get('psana-inc', "psddl_psana")
        self.psana_ns = backend_options.get('psana-ns', "Psana")
        self.dump_schema = 'dump-schema' in backend_options

        self._log = log

        #include guard
        g = os.path.split(self.incname)[1]
        if self.top_pkg: g = self.top_pkg + '_' + g
        self.guard = g.replace('.', '_').upper()

    #-------------------
    #  Public methods --
    #-------------------

    def parseTree(self, model):
        
        if self.dump_schema: return self._dumpSchema(model)
        
        # open output files
        self.inc = file(self.incname, 'w')
        self.cpp = file(self.cppname, 'w')
        
        # include guard to header
        print >>self.inc, "#ifndef", self.guard 
        print >>self.inc, "#define", self.guard, "1"

        msg = "\n// *** Do not edit this file, it is auto-generated ***\n"
        print >>self.inc, msg
        print >>self.cpp, msg

        inc = os.path.join(self.incdirname, os.path.basename(self.incname))
        print >>self.cpp, "#include \"%s\"" % inc
        inc = os.path.join(self.psana_inc, os.path.basename(self.incname))
        print >>self.inc, "#include \"%s\"" % inc

        # add necessary includes
        print >>self.inc, "#include \"hdf5pp/Group.h\""
        print >>self.inc, "#include \"hdf5pp/Type.h\""
        print >>self.inc, "#include \"PSEvt/Proxy.h\""
        print >>self.cpp, "#include \"hdf5pp/ArrayType.h\""
        print >>self.cpp, "#include \"hdf5pp/CompoundType.h\""
        print >>self.cpp, "#include \"hdf5pp/EnumType.h\""
        print >>self.cpp, "#include \"hdf5pp/VlenType.h\""
        print >>self.cpp, "#include \"hdf5pp/Utils.h\""
        print >>self.cpp, "#include \"PSEvt/DataProxy.h\""
        inc = os.path.join(self.incdirname, "Exceptions.h")
        print >>self.cpp, "#include \"%s\"" % inc
        inc = os.path.join(self.incdirname, "ChunkPolicy.h")
        print >>self.inc, "#include \"%s\"" % inc


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

        # headers for externally implemented schemas or datasets, headers for datasets are included
        # into cpp file (they are likely to be needed in inplementation of make_Class functions),
        # headers for external datasets are included into header.
        for pkg in model.packages():
            for schema in _schemas(pkg):
                if 'external' in schema.tags:
                    if schema.tags['external']: print >>self.cpp, "#include \"%s\"" % schema.tags['external']
                for ds in schema.datasets:
                    if 'external' in ds.tags:
                        if ds.tags['external']: print >>self.inc, "#include \"%s\"" % ds.tags['external']

        if self.top_pkg : 
            ns = "namespace %s {" % self.top_pkg
            print >>self.inc, ns
            print >>self.cpp, ns

        # loop over packages in the model
        for pkg in model.packages() :
            self._log.debug("parseTree: package=%s", repr(pkg))
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
        
        if pkg.included:
            # for include packages we need to make sure that types from those 
            # packages get their schemas, they may be needed by our schemas  
            for ns in pkg.namespaces() :
                if isinstance(ns, Package) :
                    self._parsePackage(ns)
                elif isinstance(ns, Type) :
                    if not ns.h5schemas:
                        ns.h5schemas = [H5Type.defaultSchema(ns)]
                        self._log.debug("_parsePackage: included type.h5schemas=%s", repr(ns.h5schemas))
            return

        self._log.info("Processing package %s", pkg.name)
        
        # open namespaces
        print >>self.inc, "namespace %s {" % pkg.name
        print >>self.cpp, "namespace %s {" % pkg.name

        # enums for constants
        for const in pkg.constants() :
            if not const.included :
                print >>self.inc, _TEMPL('const_decl').render(const=const)

        # regular enums
        for enum in pkg.enums() :
            if not enum.included :
                print >>self.inc, _TEMPL('enum_decl').render(enum=enum)

        # loop over packages and types
        for ns in pkg.namespaces() :
            
            if isinstance(ns, Package) :
                
                self._parsePackage(ns)
            
            elif isinstance(ns, Type) :
    
                self._parseType(type = ns)

        # close namespaces
        print >>self.inc, "} // namespace %s" % pkg.name
        print >>self.cpp, "} // namespace %s" % pkg.name


    def _parseType(self, type):

        self._log.debug("_parseType: type=%s", repr(type))
        self._log.trace("Processing type %s", type.name)

        # skip included types
        if type.included : return

        self._schemaFixup(type);
        self._log.debug("_parseType: type.h5schemas=%s", repr(type.h5schemas))

        for schema in type.h5schemas:
            self._genSchema(type, schema)

        # if all schemas have embedded tag stop here
        if all('embedded' in schema.tags for schema in type.h5schemas): return

        psanatypename = type.fullName('C++', self.psana_ns)

        # generate all make_* methods
        configs = type.xtcConfig or [None]
        for config in configs:
            
            if config: cfgtypename = config.fullName('C++', self.psana_ns)
            psanatypename = type.fullName('C++', self.psana_ns)

            print >>self.inc, _TEMPL('make_proxy_decl').render(locals())
            print >>self.cpp, _TEMPL('make_proxy_impl').render(locals())

        # generate store method declaration
        print >>self.inc, _TEMPL('store_decl').render(locals())
        
        versions = sorted(schema.version for schema in type.h5schemas)
        max_version = versions[-1]
        print >>self.cpp, _TEMPL('store_impl').render(locals())

    def _genSchema(self, type, schema):

        self._log.debug("_genSchema: %s", repr(schema))

        if 'external' in schema.tags:
            self._log.debug("_genSchema: skip schema - external")
            return

        # wrap schema into helper class which knows how to do the rest
        hschema = Helpers.Schema(schema, self.psana_ns)

        for ds in hschema.datasets:
            # generate datasets classes
            ds.genDs(self.inc, self.cpp)

        hschema.genSchema(self.inc, self.cpp)


    def _dumpSchema(self, model):
        '''
        Method which dumps hdf5 schema for all types in a model
        '''
        for pkg in model.packages():
            self._dumpPkgSchema(pkg)

    def _dumpPkgSchema(self, pkg, offset=1):

        if not pkg.included: print '%s<package name="%s">' % ("    "*offset, pkg.name)

        for ns in pkg.namespaces() :
            
            if isinstance(ns, Package) :
                self._dumpPkgSchema(ns, offset+1)
            elif isinstance(ns, Type) :
                self._dumpTypeSchema(ns, offset+1)


        if not pkg.included: print '%s</package>' % ("    "*offset,)

    def _dumpTypeSchema(self, type, offset=1):

        if type.included: return

        self._schemaFixup(type);
            
        for schema in type.h5schemas:
            
            print '{}<h5schema name="{}" version="{}">'.format("    "*(offset), schema.name, schema.version)
            
            for tag, val in schema.tags.items():
                print '{}<tag name="{}" value="{}">'.format("    "*(offset+1), tag, val)
            
            for ds in schema.datasets:
            
                print '{}<dataset name="{}">'.format("    "*(offset+1), ds.name)
                
                for tag, val in ds.tags.items():
                    print '{}<tag name="{}" value="{}">'.format("    "*(offset+2), tag, val)
                    
                for attr in ds.attributes:
                
                    rank = ""
                    meth = ""
                    if attr.rank: rank = ' rank="%d"' % attr.rank
                    if attr.method != attr.name: meth = ' method="%s"' % attr.method
                    if attr.tags:
                        print '{}<attribute name="{}"{}{}>'.format("    "*(offset+2), attr.name, meth, rank)
                        for tag, val in attr.tags.items():
                            print '{}<tag name="{}" value="{}"/>'.format("    "*(offset+3), tag, val)
                        print '{}</attribute>'.format("    "*(offset+2))
                    else:
                        print '{}<attribute name="{}"{}{}/>'.format("    "*(offset+2), attr.name, meth, rank)
                
                print '{}</dataset>'.format("    "*(offset+1))
            
            print '{}</h5schema>'.format("    "*(offset))
            

    def _schemaFixup(self, type):
        '''
        Make few adjustments to type schemas if necessary 
        ''' 

        # if no schemas defined at all generate default schema
        if not type.h5schemas:
            type.h5schemas = [H5Type.defaultSchema(type)]

        # fixup for individual schema
        for i, schema in enumerate(type.h5schemas):
            
            # if schema has no datasets but has 'default' tag then 
            # use default schema but merge their tags
            if not schema.datasets and 'default' in schema.tags:
                defschema = H5Type.defaultSchema(type)
                defschema.tags.update(schema.tags)
                schema = defschema
                type.h5schemas[i] = schema

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
