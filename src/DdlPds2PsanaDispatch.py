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
from psddl.Package import Package
from psddl.Type import Type
from psddl.Template import Template as T

#----------------------------------
# Local non-exported definitions --
#----------------------------------

# list of type IDs which are not needed or handled separately,
# we add these to the switch to suppress warnings. If one of these
# types gets implemented it should be removed from the list.
_ignored_types = [
        'Any', 
        'Id_Xtc', 
        'NumberOf', 
        'Id_Epics', 
        'Reserved1',
        'Reserved2',
        'Id_Index',
        'Id_XampsConfig',
        'Id_XampsElement',
        'Id_FexampConfig',
        'Id_FexampElement',
        'Id_PhasicsConfig',
        'Id_CspadCompressedElement',
        'Id_SharedAcqADC',
        ]

# Extra headers needed for special proxy classes of similar stuff
_extra_headers = [
        "psddl_pds2psana/CsPadDataOrdered.h",
        "psddl_pds2psana/PnccdFullFrameV1Proxy.h",
        "psddl_pds2psana/TimepixDataV1ToV2.h",
        ]

# types that need special UseSize argument for proxy, 
# there should not be too many of these 
_use_size_types = [
        "Acqiris::TdcDataV1"
        ]

# some types need to substitute generated final classes with 
# hand-written stuff
def _finalClass(type, final_ns):
    typeName = type.fullName('C++')
    if typeName.startswith("CsPad::DataV"):
        # cspad need special final type
        version = typeName[12:]
        ns = final_ns + '::' if final_ns else ''
        typeName = "%sCsPadDataOrdered<%sCsPad::DataV%s, Psana::CsPad::ElementV%s>" % (ns, ns, version, version)
    elif typeName == "Timepix::DataV1":
        ns = final_ns + '::' if final_ns else ''
        typeName = ns + "TimepixDataV1ToV2"
    else:
        # for all other types use gwnwrated stuff
        typeName = type.fullName('C++', final_ns)
    return typeName

# some types convert XTC types into different (versions) of psana types
def _psanaClass(type, psana_ns):
    typeName = type.fullName('C++')
    if typeName == "Timepix::DataV1":
        ns = psana_ns + '::' if psana_ns else ''
        typeName = ns + "Timepix::DataV2"
    else:
        # for all other types use gwnwrated stuff
        typeName = type.fullName('C++', psana_ns)
    return typeName

# some types need special proxy class
def _proxyClass(type, psana_type, final_type, xtc_type, config_type=None):

    typeName = type.fullName('C++')
    if typeName == 'PNCCD::FullFrameV1':
        return 'PnccdFullFrameV1Proxy'
    elif not type.xtcConfig:
        use_size = type.fullName('C++') in _use_size_types
        if use_size:
            return 'EvtProxy<{0}, {1}, {2}, true>'.format(psana_type, final_type, xtc_type)
        else:
            return 'EvtProxy<{0}, {1}, {2}>'.format(psana_type, final_type, xtc_type)
    else:
            return 'EvtProxyCfg<{0}, {1}, {2}, {3}>'.format(psana_type, final_type, xtc_type, config_type)



# ========================================================
# == code templates, usually do not need to touch these ==
# ========================================================

_decl_template = ji.Template('''\
#ifndef {{inc_guard}}
#define {{inc_guard}} 1

// *** Do not edit this file, it is auto-generated ***

#include <boost/shared_ptr.hpp>
#include "pdsdata/xtc/Xtc.hh"
#include "PSEvt/Event.h"
#include "PSEnv/EnvObjectStore.h"

{% if namespace %}
namespace {{namespace}} {
{% endif %}

  /**
   *  Function takes xtc object, converts it into psana-type instance and stores either in 
   *  event or config-store. Pointer to even may be zero.
   */
  void xtcConvert(const boost::shared_ptr<Pds::Xtc>& xtc, PSEvt::Event* evt, PSEnv::EnvObjectStore& cfgStore);

{% if namespace %}
} // namespace {{namespace}}
{% endif %}

#endif // {{inc_guard}}
''', trim_blocks=True)

_impl_template = ji.Template('''\
// *** Do not edit this file, it is auto-generated ***

#include "MsgLogger/MsgLogger.h"
#include "PSEvt/Exceptions.h"
#include "psddl_pds2psana/EvtProxy.h"
#include "psddl_pds2psana/EvtProxyCfg.h"

{% for header in headers %}
#include "{{header}}"
{% endfor %}

{% if namespace %}
namespace {{namespace}} {
{% endif %}
void xtcConvert(const boost::shared_ptr<Pds::Xtc>& xtc, PSEvt::Event* evt, PSEnv::EnvObjectStore& cfgStore)
try {
  const Pds::TypeId& typeId = xtc->contains;

  int version = typeId.version();
  switch(typeId.id()) {
{% for type_id in ignored_types %}
  case Pds::TypeId::{{type_id}}:
{% endfor %}
    break;
{% for type_id, block in types|dictsort  %}
  case Pds::TypeId::{{type_id}}:
    {
{{block}}
    }
    break;
{% endfor %}
  } // end switch

} catch (const PSEvt::ExceptionDuplicateKey& ex) {
  // catch exception for duplicated objects, issue warning
  MsgLog("xtcConvert", warning, ex.what());
} // end xtcConvert(...)

{% if namespace %}
} // namespace {{namespace}}
{% endif %}
''', trim_blocks=True)

_version_template = ji.Template('''\
      switch (version) {
{% for version, blocks in versions|dictsort %}
      case {{version}}:
        {
{{blocks|join('\n')}}
        }
        break;
{% endfor %}
      } // end switch (version)
''', trim_blocks=True)

_config_abs_store_template = ji.Template('''\
          // store XTC object in config store
          boost::shared_ptr<{{xtc_type}}> xptr(xtc, ({{xtc_type}}*)(xtc->payload()));
          cfgStore.put(xptr, xtc->src);
          // create and store psana object in config store
          boost::shared_ptr<{{psana_type}}> obj = boost::make_shared<{{final_type}}>(xptr);
          cfgStore.put(obj, xtc->src);
''', trim_blocks=True)

_config_value_store_template = ji.Template('''\
          // XTC data object
          {{xtc_type}}* xdata = ({{xtc_type}}*)(xtc->payload());
          // store XTC object in config store
          boost::shared_ptr<{{xtc_type}}> xptr(xtc, xdata);
          cfgStore.put(xptr, xtc->src);
          //convert XtcType to Psana type
          const {{psana_type}}& data = {{final_namespace}}::pds_to_psana(*xdata);
          // create and store psana object in config store
          cfgStore.put(boost::make_shared<{{psana_type}}>(data), xtc->src);
''', trim_blocks=True)

_event_value_store_template = ji.Template('''\
          // XTC data object
          const {{xtc_type}}& xdata = *({{xtc_type}}*)(xtc->payload());
          //convert XtcType to Psana type
          const {{psana_type}}& data = {{final_namespace}}::pds_to_psana(xdata);
          // store data
          if (evt) evt->put(boost::make_shared<{{psana_type}}>(data), xtc->src);
''', trim_blocks=True)

_event_abs_store_template = ji.Template('''\
          // store proxy
          typedef {{proxy_type}} ProxyType;
          if (evt) evt->putProxy<{{psana_type}}>(boost::make_shared<ProxyType>(xtc), xtc->src);
''', trim_blocks=True)

_event_cfg_store_template = ji.Template('''\
{% for config_type, proxy_type in config_types|dictsort %}
{% if loop.first %}
          if (boost::shared_ptr<{{config_type}}> cfgPtr = cfgStore.get(xtc->src)) {
{% else %}
          } else if (boost::shared_ptr<{{config_type}}> cfgPtr = cfgStore.get(xtc->src)) {
{% endif %}
            // store proxy
            typedef {{proxy_type}} ProxyType;
            if (evt) evt->putProxy<{{psana_type}}>(boost::make_shared<ProxyType>(xtc, cfgPtr), xtc->src);
{% endfor %}
          }
''', trim_blocks=True)


#------------------------
# Exported definitions --
#------------------------

#---------------------
#  Class definition --
#---------------------
class DdlPds2PsanaDispatch ( object ) :

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
        self.pdsdata_ns = backend_options.get('pdsdata-ns', "PsddlPds")

        self._types = {}

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
        for pkg in model.packages() :
            if not pkg.included :
                self._log.debug("parseTree: package=%s", repr(pkg))
                self._parsePackage(pkg)

        # generate code for all collected types
        types, headers = self._codegen()

        # add own header to the list
        headers = [os.path.join(self.incdirname, os.path.basename(self.incname))] + list(headers) + _extra_headers

        inc_guard = self.guard
        namespace = self.top_pkg
        ignored_types = _ignored_types
        print >>self.inc, _decl_template.render(locals())
        print >>self.cpp, _impl_template.render(locals())
        
        # close all files
        self.inc.close()
        self.cpp.close()


    def _parsePackage(self, pkg):

        # loop over packages and types
        for ns in pkg.namespaces() :
            
            if isinstance(ns, Package) :
                
                self._parsePackage(ns)
            
            elif isinstance(ns, Type) :
    
                self._parseType(type = ns)


    def _parseType(self, type):

        self._log.debug("_parseType: type=%s", repr(type))

        if type.type_id is None: return
        
        self._types.setdefault(type.type_id, []).append(type)


    def _codegen(self):
        ''' 
        Retuns tuple containing two elements:
        1. Dictinary mappig TypeId type name (like 'Id_AcqConfig') to the corresponding piece of code
        2. List of heder names to be included 
        ''' 
        codes = {}
        headers = set()
        
        for type_id, types in self._types.items():
            
            versions = {}
            for type in types:
                
                code, header = self._typecode(type)
                headers.add(header)
                
                v = int(type.version)
                versions.setdefault(v, []).append(code)
                # for event-type data add compressed version as well
                if 'config-type' not in type.tags:
                    v = int(type.version) | 0x8000
                    versions.setdefault(v, []).append(code)
                
            codes[type_id] = _version_template.render(locals())

        return codes, headers


    def _typecode(self, type):
        '''
        For a given type returns tuple of two elements:
        1. Piece of code which produces final objects
        2. Name of the include file
        '''
        header = os.path.basename(type.location)
        header = os.path.splitext(header)[0] + '.h'
        header = os.path.join(self.incdirname, header)
        
        xtc_type = type.fullName('C++', self.pdsdata_ns)
        psana_type = _psanaClass(type, self.psana_ns)
        final_type = _finalClass(type, self.top_pkg)

        code = ""
        
        if 'config-type' in type.tags:
            # config types
            if type.value_type:
                final_namespace = type.parent.fullName('C++', self.top_pkg)                
                code = _config_value_store_template.render(locals())
            else:
                code = _config_abs_store_template.render(locals())
        else:
            # non-config types
            use_size = type.fullName('C++') in _use_size_types
            if type.value_type:
                final_namespace = type.parent.fullName('C++', self.top_pkg)                
                code = _event_value_store_template.render(locals())
            elif not type.xtcConfig:
                proxy_type = _proxyClass(type, psana_type, final_type, xtc_type)
                code = _event_abs_store_template.render(locals())
            else:
                config_types = {}
                for t in type.xtcConfig:
                    cfg_type = t.fullName('C++', self.pdsdata_ns)
                    config_types[cfg_type] = _proxyClass(type, psana_type, final_type, xtc_type, cfg_type)
                code = _event_cfg_store_template.render(locals())

        return code, header
    
#
#  In case someone decides to run this module
#
if __name__ == "__main__" :

    # In principle we can try to run test suite for this module,
    # have to think about it later. Right now just abort.
    sys.exit ( "Module is not supposed to be run as main module" )
