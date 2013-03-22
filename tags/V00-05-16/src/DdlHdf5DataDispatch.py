#--------------------------------------------------------------------------
# File and Version Information:
#  $Id$
#
# Description:
#  Module DdlPds2Psana...
#
#------------------------------------------------------------------------

"""DDL parser which generates pds2psana C++ code.

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
import types

#---------------------------------
#  Imports of base class module --
#---------------------------------

#-----------------------------
# Imports for other modules --
#-----------------------------
import jinja2 as ji
from psddl.H5Type import H5Type
from psddl.Package import Package
from psddl.Type import Type
from psddl.Template import Template as T

#----------------------------------
# Local non-exported definitions --
#----------------------------------

# set of aliases, alias name (key in the dictionary) is replaced with the value 
_aliases = {
    'Bld::BldDataIpimb': 'Bld::BldDataIpimbV0',
    'Bld::BldDataEBeam': 'Bld::BldDataEBeamV1',
    }

# Extra headers needed for special proxy classes of similar stuff
_extra_headers = [
        ]


# ========================================================
# == code templates, usually do not need to touch these ==
# ========================================================

_decl_template = ji.Template('''\
#ifndef {{inc_guard}}
#define {{inc_guard}} 1

// *** Do not edit this file, it is auto-generated ***

#include <stdint.h>

#include "hdf5pp/Group.h"
#include "PSEvt/Event.h"
#include "PSEnv/EnvObjectStore.h"

{% if namespace %}
namespace {{namespace}} {
{% endif %}

  /**
   *  Function takes HDF5 group, converts its contents into psana-type instance and stores either in
   *  event or config-store. Pointer to even may be zero.
   */
  void hdfConvert(const hdf5pp::Group& group, int64_t idx, const std::string& typeName, int schema_version, 
                  const Pds::Src& src, PSEvt::Event& evt, PSEnv::EnvObjectStore& cfgStore);

{% if namespace %}
} // namespace {{namespace}}
{% endif %}

#endif // {{inc_guard}}
''', trim_blocks=True)

_impl_template = ji.Template('''\
// *** Do not edit this file, it is auto-generated ***

#include "MsgLogger/MsgLogger.h"
#include "PSEvt/Exceptions.h"

{% for header in headers %}
#include "{{header}}"
{% endfor %}

{{hash.code()}}

{% if namespace %}
namespace {{namespace}} {
{% endif %}
void hdfConvert(const hdf5pp::Group& group, int64_t idx, const std::string& typeName, int schema_version, 
                const Pds::Src& src, PSEvt::Event& evt, PSEnv::EnvObjectStore& cfgStore)
try {

  uint32_t hash = str_hash(typeName);
  switch(hash) {
{% for hash, types in hashes|dictsort %}
  case {{hash}}:
{% if types|length > 1 %}
{% for type in types %}
    if (typeName == "{{type.name}}") {{type.code}}
{% endfor %}
{% else %}
{{types[0].code}}
{% endif %}
    break;
{% endfor %}
  } // end switch

} catch (const PSEvt::ExceptionDuplicateKey& ex) {
  // catch exception for duplicated objects, issue warning
  MsgLog("hdfConvert", warning, ex.what());
} // end hdfConvert(...)

{% if namespace %}
} // namespace {{namespace}}
{% endif %}
''', trim_blocks=True)

_config_store_template = ji.Template('''\
    cfgStore.putProxy({{namespace}}::make_{{type.name}}(schema_version, group, idx), src);
''', trim_blocks=True)

_event_store_template = ji.Template('''\
    evt.putProxy({{namespace}}::make_{{type.name}}(schema_version, group, idx), src);
''', trim_blocks=True)

_event_cfg_store_template = ji.Template('''\
{% for config_type in config_types %}
{% if loop.first %}
    if (boost::shared_ptr<{{config_type}}> cfgPtr = cfgStore.get(src)) {
{% else %}
    } else if (boost::shared_ptr<{{config_type}}> cfgPtr = cfgStore.get(src)) {
{% endif %}
      evt.putProxy({{namespace}}::make_{{type.name}}(schema_version, group, idx, cfgPtr), src);
{% endfor %}
    }
''', trim_blocks=True)


class _DJB2a(object):
    
    def hash(self, string):
        hash = 5381
        for ch in string:
            hash = ((hash*33) & 0xffffffff) ^ ord(ch)
        return hash

    def code(self):

        return """
namespace {
    uint32_t str_hash(const std::string& str)
    {
        uint32_t hash = 5381;
        for (std::string::const_iterator it = str.begin(); it != str.end(); ++it) {
            hash = ((hash << 5) + hash) ^ uint32_t(*it); /* hash * 33 + c */
        }
        return hash;
    }
}"""

class _sdbm(object):
    
    def hash(self, string):
        hash = 0
        for ch in string:
            hash = ord(c) + (hash << 6) + (hash << 16) - hash
            hash = (2^32 + hash) % 2^32
        return hash

    def code(self):

        return """
namespace {
    uint32_t str_hash(const std::string& str)
    {
        uint32_t hash = 0;
        for (std::string::const_iterator it = str.begin(); it != str.end(); ++it) {
            hash = uint32_t(c) + (hash << 6) + (hash << 16) - hash;
        }
        return hash;
    }
}"""

#------------------------
# Exported definitions --
#------------------------

#---------------------
#  Class definition --
#---------------------
class DdlHdf5DataDispatch ( object ) :

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
        self.psana_ns = backend_options.get('psana-ns', "Psana")

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

        # loop over packages in the model
        types = []
        for pkg in model.packages() :
            if not pkg.included :
                self._log.debug("parseTree: package=%s", repr(pkg))
                types += self._parsePackage(pkg)

        typenames = [type.fullName('C++') for type in types] + _aliases.keys()

        # select hash function with minimum collisions
        hash = _DJB2a()
        hashes = set([hash.hash(name) for name in typenames])
        if len(hashes) == len(typenames):
            self._log.debug("DJB2a without collisions")
        else:
            djb_coll = len(typenames) - len(hashes)
            hash2 = _sdbm()
            hashes = set([hash.hash(name) for name in typenames])
            if len(hashes) == len(typenames):
                self._log.debug("SDBM without collisions")
                hash = hash2
            else:
                sdbm_coll = len(typenames) - len(hashes)
                if sdbm_coll < djb_coll: hash = hash2


        # generate code for all collected types
        codes, headers = self._codegen(types)

        # add own header to the list
        headers = [os.path.join(self.incdirname, os.path.basename(self.incname))] + list(headers) + _extra_headers

        hashes = {}
        for type, code in codes.items():
            name = type.fullName('C++')
            hh = hash.hash(name)
            hashes.setdefault(hh, []).append(dict(name=name, code=code))

        for alias, typeName in _aliases.items():
            hh = hash.hash(alias)
            for type, code in codes.items():
                if type.fullName('C++') == typeName:
                    hashes.setdefault(hh, []).append(dict(name=alias, code=code))


        inc_guard = self.guard
        namespace = self.top_pkg
        print >>self.inc, _decl_template.render(locals())
        print >>self.cpp, _impl_template.render(locals())
        
        # close all files
        self.inc.close()
        self.cpp.close()


    def _parsePackage(self, pkg):

        # loop over packages and types
        types = []
        for ns in pkg.namespaces() :
            
            if isinstance(ns, Package) :
                
                types += self._parsePackage(ns)
            
            elif isinstance(ns, Type) :
    
                types.append(ns)
                
        return types


    def _codegen(self, types):
        
        codes = {}
        headers = set()
        
        for type in types:

            if not type.h5schemas:
                type.h5schemas = [H5Type.defaultSchema(type)]

            # if all schemas have skip-proxy tag stop here
            if all('skip-proxy' in schema.tags for schema in type.h5schemas): continue
            
            code, header = self._typecode(type)
            headers.add(header)
            codes[type] = code

        return codes, headers


    def _typecode(self, type):

        header = os.path.basename(type.location)
        header = os.path.splitext(header)[0] + '.h'
        header = os.path.join(self.incdirname, header)
        
        psana_type = type.fullName('C++', self.psana_ns)
        namespace = type.parent.fullName('C++', self.top_pkg)

        code = ""
        if 'config-type' in type.tags:
            # config types
            code = _config_store_template.render(locals())
        else:
            # non-config types
            if not type.xtcConfig:
                code = _event_store_template.render(locals())
            else:
                config_types = [t.fullName('C++', self.psana_ns) for t in type.xtcConfig]
                code = _event_cfg_store_template.render(locals())

        return code, header
    
#
#  In case someone decides to run this module
#
if __name__ == "__main__" :

    # In principle we can try to run test suite for this module,
    # have to think about it later. Right now just abort.
    sys.exit ( "Module is not supposed to be run as main module" )
