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
from psddl import DdlHdf5DataHelpers as Helpers

#----------------------------------
# Local non-exported definitions --
#----------------------------------

_make_proxy_decl_template = ji.Template('''\
{% if cfgtypename %}
boost::shared_ptr<PSEvt::Proxy<{{psanatypename}}> > make_{{type.name}}(int version, hdf5pp::Group group, hsize_t idx, const boost::shared_ptr<{{cfgtypename}}>& cfg);\
{% else %}
boost::shared_ptr<PSEvt::Proxy<{{psanatypename}}> > make_{{type.name}}(int version, hdf5pp::Group group, hsize_t idx);\
{% endif %}
''', trim_blocks=True)

_make_proxy_impl_template = ji.Template('''\
{% if cfgtypename %}
boost::shared_ptr<PSEvt::Proxy<{{psanatypename}}> > make_{{type.name}}(int version, hdf5pp::Group group, hsize_t idx, const boost::shared_ptr<{{cfgtypename}}>& cfg) {
{% else %}
boost::shared_ptr<PSEvt::Proxy<{{psanatypename}}> > make_{{type.name}}(int version, hdf5pp::Group group, hsize_t idx) {
{% endif %}
  switch (version) {
{% for schema in type.h5schemas %}
  case {{schema.version}}:
{% if type.value_type %}
    return boost::make_shared<Proxy_{{type.name}}_v{{schema.version}}>(group, idx);
{% else %}
{% if cfgtypename %}
    return boost::make_shared<PSEvt::DataProxy<{{psanatypename}}> >(boost::make_shared<{{type.name}}_v{{schema.version}}<{{cfgtypename}}> >(group, idx, cfg));
{% else %}
    return boost::make_shared<PSEvt::DataProxy<{{psanatypename}}> >(boost::make_shared<{{type.name}}_v{{schema.version}}>(group, idx));
{% endif %}
{% endif %}
{% endfor %}
  default:
    return boost::make_shared<PSEvt::DataProxy<{{psanatypename}}> >(boost::shared_ptr<{{psanatypename}}>());
  }
}
''', trim_blocks=True)



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

    #----------------
    #  Constructor --
    #----------------
    def __init__(self, incname, cppname, backend_options, log):
        """Constructor
        
            @param incname  include file name
            @param cppname  source file name
        """
        self.incname = incname
        self.cppname = cppname
        self.incdirname = backend_options.get('gen-incdir', "")
        self.top_pkg = backend_options.get('top-package')
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
        
        print >>self.inc, "  enum {\n    %s = %s /**< %s */\n  };" % \
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

        self._log.debug("_parseType: type=%s", repr(type))
        self._log.trace("Processing type %s", type.name)

        # skip included types
        if type.included : return

        if not type.h5schemas:
            type.h5schemas = [H5Type.defaultSchema(type)]
            self._log.debug("_parseType: type.h5schemas=%s", repr(type.h5schemas))

        for schema in type.h5schemas:
            self._genSchema(type, schema)

        # if all schemas have skip-proxy tag stop here
        if all('skip-proxy' in schema.tags for schema in type.h5schemas): return

        psanatypename = type.fullName('C++', self.psana_ns)
        typename = type.name

        # generate all make_* methods
        configs = type.xtcConfig or [None]
        for config in configs:
            
            if config: cfgtypename = config.fullName('C++', self.psana_ns)
            psanatypename = type.fullName('C++', self.psana_ns)

            print >>self.inc, _make_proxy_decl_template.render(locals())
            print >>self.cpp, _make_proxy_impl_template.render(locals())

    def _genSchema(self, type, schema):

        self._log.debug("_genSchema: %s", repr(schema))

        if 'external' in schema.tags:
            self._log.debug("_genSchema: skip schema - external")
            return

        # wrap schema into helper class which knows how to do the reset
        hschema = Helpers.Schema(schema)

        for ds in hschema.datasets:
            # generate datasets classes
            ds.genDs(self.inc, self.cpp, self.psana_ns)

        hschema.genSchema(self.inc, self.cpp, self.psana_ns)


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

        if not type.h5schemas:
            type.h5schemas = [H5Type.defaultSchema(type)]
            
        if type.included: return
            
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
